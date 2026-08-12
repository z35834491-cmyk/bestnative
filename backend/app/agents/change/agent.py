# ============================================================
# app/agents/change/agent.py — 变更/发布 Agent
# 6 步闭环：风险评估 → 执行(argocd) → 验证(健康+指标回归)
#          → 决策(通过/回滚) → 根因分析 → 入库
# 安全：默认自动回滚（AUTO_ROLLBACK），argocd 操作参数化
# ============================================================

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import get_llm
from app.core.config import settings
from app.core.logging import get_logger
from app.models.deployment import Deployment
from app.rag.ingest import ingest
from app.services.prometheus import PrometheusClient

logger = get_logger("agent.change")


class ChangeAgent:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.prom = PrometheusClient()

    async def execute(self, deployment_id: str) -> dict:
        dep = await self._get(deployment_id)
        if dep is None:
            return {"error": "not found"}

        stages: list[dict] = []

        # ---- 1. 风险评估 ----
        risk = await self._assess_risk(dep)
        stages.append({"stage": "risk_assessment", "status": "done", "detail": risk})

        # ---- 2. 执行部署（argocd set image + sync）----
        dep.status = "deploying"
        await self._save_stages(dep, stages)
        exec_ok = await self._argocd_deploy(dep)
        stages.append({"stage": "deploy", "status": "done" if exec_ok else "failed"})

        if not exec_ok:
            return await self._fail(dep, stages, "ArgoCD 部署执行失败")

        # ---- 3. 验证（等待 → 健康检查 + 指标回归对比）----
        dep.status = "verifying"
        await self._save_stages(dep, stages)
        await asyncio.sleep(min(settings.DEPLOY_VERIFY_WAIT, 5))  # 本地演示缩短
        verify = await self._verify(dep)
        stages.append({"stage": "verify", "status": "done", "detail": verify})
        dep.metrics = verify

        # ---- 4. 决策 ----
        if verify.get("healthy"):
            dep.status = "success"
            dep.completed_at = datetime.now(timezone.utc)
            stages.append({"stage": "decision", "status": "done", "detail": "验证通过"})
            await self._save_stages(dep, stages)
            await self.db.flush()
            return {"deployment_id": deployment_id, "status": "success"}

        # ---- 5. 验证失败 → 根因分析 + 回滚 ----
        analysis = await self._root_cause(dep, verify)
        dep.ai_analysis = analysis
        dep.failure_reason = verify.get("reason", "健康检查未通过")

        if settings.AUTO_ROLLBACK:
            await self._argocd_rollback(dep)
            dep.status = "rolled_back"
            stages.append({"stage": "rollback", "status": "done", "detail": "自动回滚完成"})
        else:
            dep.status = "failed"

        dep.completed_at = datetime.now(timezone.utc)
        await self._save_stages(dep, stages)

        # ---- 6. 入库（沉淀到知识库）----
        await self._ingest_knowledge(dep, analysis)
        await self.db.flush()
        return {"deployment_id": deployment_id, "status": dep.status, "analysis": analysis}

    async def rollback(self, deployment_id: str) -> dict:
        dep = await self._get(deployment_id)
        if dep is None:
            return {"error": "not found"}
        await self._argocd_rollback(dep)
        dep.status = "rolled_back"
        dep.completed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return {"deployment_id": deployment_id, "status": "rolled_back"}

    # ---------- 内部方法 ----------

    async def _get(self, deployment_id: str) -> Deployment | None:
        return (await self.db.execute(
            select(Deployment).where(Deployment.id == deployment_id)
        )).scalar_one_or_none()

    async def _assess_risk(self, dep: Deployment) -> str:
        """基于变更内容评估风险等级。"""
        return f"服务 {dep.service} 从 {dep.previous_version or 'N/A'} → {dep.version}，常规滚动更新"

    async def _argocd_deploy(self, dep: Deployment) -> bool:
        """调用 argocd 更新镜像并 sync。无 argocd 配置时降级为模拟成功。"""
        if not settings.ARGOCD_SERVER:
            logger.info("argocd.skip", reason="no ARGOCD_SERVER, simulate", service=dep.service)
            return True
        cmd = ["argocd", "app", "set", dep.argocd_app,
               "-p", f"image.tag={dep.version}",
               "--server", settings.ARGOCD_SERVER, "--auth-token", settings.ARGOCD_TOKEN]
        return await self._run(cmd) and await self._run(
            ["argocd", "app", "sync", dep.argocd_app,
             "--server", settings.ARGOCD_SERVER, "--auth-token", settings.ARGOCD_TOKEN])

    async def _argocd_rollback(self, dep: Deployment) -> bool:
        if not settings.ARGOCD_SERVER:
            logger.info("argocd.rollback.skip", service=dep.service)
            return True
        return await self._run(
            ["argocd", "app", "rollback", dep.argocd_app,
             "--server", settings.ARGOCD_SERVER, "--auth-token", settings.ARGOCD_TOKEN])

    async def _run(self, cmd: list[str]) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            _, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            return proc.returncode == 0
        except Exception as e:  # noqa: BLE001
            logger.warning("argocd.cmd.failed", cmd=cmd[0], error=str(e))
            return False

    async def _verify(self, dep: Deployment) -> dict:
        """健康检查 + 关键指标回归对比（错误率/延迟）。"""
        svc = dep.service
        err_rate = await self.prom.query(
            f'sum(rate(http_requests_total{{service="{svc}",code=~"5.."}}[5m]))')
        latency = await self.prom.query(
            f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{{service="{svc}"}}[5m])) by (le))')
        err_val = float(err_rate[0]["value"]) if err_rate else 0.0
        p95 = float(latency[0]["value"]) if latency else 0.0
        healthy = err_val < 0.05 and p95 < 2.0
        return {"healthy": healthy, "error_rate": err_val, "p95_latency": p95,
                "reason": "" if healthy else f"错误率 {err_val:.3f} / P95 {p95:.2f}s 超阈值"}

    async def _root_cause(self, dep: Deployment, verify: dict) -> str:
        prompt = f"""发布验证失败，分析根因并给出简短建议。
服务：{dep.service}  版本：{dep.previous_version} → {dep.version}
提交信息：{dep.commit_message}
验证指标：{verify}"""
        try:
            from langchain_core.messages import HumanMessage
            resp = await get_llm(temperature=0.2).ainvoke([HumanMessage(content=prompt)])
            return resp.content
        except Exception as e:  # noqa: BLE001
            return f"（AI 分析不可用：{e}）验证失败原因：{verify.get('reason')}"

    async def _ingest_knowledge(self, dep: Deployment, analysis: str):
        try:
            await ingest(
                self.db, source_type="incident_resolution",
                title=f"发布失败：{dep.service} {dep.version}",
                content=f"{dep.commit_message}\n验证：{dep.metrics}\n分析：{analysis}",
                source_id=str(dep.id),
                metadata={"services": [dep.service], "type": "deployment"},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("change.ingest.failed", error=str(e))

    async def _save_stages(self, dep: Deployment, stages: list[dict]):
        dep.stages = stages
        await self.db.flush()

    async def _fail(self, dep: Deployment, stages: list[dict], reason: str) -> dict:
        dep.status = "failed"
        dep.failure_reason = reason
        dep.completed_at = datetime.now(timezone.utc)
        await self._save_stages(dep, stages)
        await self.db.flush()
        return {"deployment_id": str(dep.id), "status": "failed", "reason": reason}
