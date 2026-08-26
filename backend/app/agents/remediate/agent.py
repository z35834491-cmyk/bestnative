# ============================================================
# app/agents/remediate/agent.py — 修复 Agent（Runbook 建议与执行）
# ============================================================

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentConfig, BaseAgent
from app.agents.llm import get_llm
from app.core.config import settings
from app.core.logging import get_logger
from app.models.incident import AnalysisReport, Incident
from app.providers.kubernetes import KubernetesProvider
from app.services.agent_runs import finish_run, start_run

logger = get_logger("agent.remediate")

RUNBOOKS = {
    "restart_pod": {
        "label": "重启异常 Pod",
        "risk": "medium",
        "description": "删除 Pod 由 Deployment 重建，适用于 CrashLoop 或僵死进程",
    },
    "rollback_deploy": {
        "label": "回滚最近发布",
        "risk": "high",
        "description": "回滚到上一版本，适用于发布引入的故障",
    },
    "scale_up": {
        "label": "临时扩容",
        "risk": "low",
        "description": "增加副本应对流量尖峰或单 Pod 故障",
    },
    "manual": {
        "label": "人工介入",
        "risk": "low",
        "description": "无安全自动修复路径，需人工处理",
    },
}


class RemediateAgent(BaseAgent):
    config = AgentConfig(
        name="remediate",
        system_prompt="你是 SRE 修复专家，根据诊断结果推荐最安全的 Runbook。",
        requires_approval=True,
    )

    def __init__(self, db: AsyncSession):
        self.db = db

    async def plan(self, incident_id: str, *, triggered_by: str = "manual") -> dict:
        run = await start_run(
            self.db,
            agent_type="remediate",
            title=f"修复方案 #{incident_id[:8]}",
            triggered_by=triggered_by,
            input={"incidentId": incident_id},
        )
        inc = (await self.db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
        if inc is None:
            await finish_run(self.db, run, {}, error="incident not found")
            return {"error": "incident not found"}

        report = (
            await self.db.execute(
                select(AnalysisReport)
                .where(AnalysisReport.incident_id == incident_id)
                .order_by(AnalysisReport.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        actions = await self._suggest_actions(inc, report)
        output = {
            "incidentId": incident_id,
            "title": inc.title,
            "actions": actions,
            "requiresApproval": True,
            "autoRemediateEnabled": settings.OPS_AUTO_REMEDIATE,
        }
        await finish_run(self.db, run, output)
        return {"runId": str(run.id), **output}

    async def execute(self, incident_id: str, action_type: str, params: dict | None = None) -> dict:
        if not settings.OPS_AUTO_REMEDIATE and action_type != "manual":
            return {"error": "自动修复未开启，请在设置中启用 OPS_AUTO_REMEDIATE 或人工执行"}

        params = params or {}
        if action_type == "restart_pod":
            ns = params.get("namespace", "default")
            pod = params.get("podName", "")
            if not pod:
                return {"error": "缺少 podName"}
            provider = KubernetesProvider(settings.CLUSTER_NAME, {
                "in_cluster": settings.K8S_IN_CLUSTER,
                "kubeconfig": settings.KUBECONFIG or None,
                "context": settings.K8S_CONTEXT or None,
            })
            ok = await provider.restart_pod(namespace=ns, pod_name=pod)
            return {"action": action_type, "success": ok, "pod": pod, "namespace": ns}

        return {"error": f"不支持的操作 {action_type}，请人工执行"}

    async def _suggest_actions(self, inc: Incident, report: AnalysisReport | None) -> list[dict]:
        root = report.root_cause if report else ""
        rec = report.recommendation if report else ""
        services = inc.affected_services or []

        if settings.llm_configured:
            try:
                from langchain_core.messages import HumanMessage
                llm = get_llm(temperature=0.1)
                prompt = f"""事件：{inc.title}
根因：{root}
建议：{rec}
服务：{', '.join(services)}

可选 Runbook：{json.dumps(RUNBOOKS, ensure_ascii=False)}
返回 JSON 数组，每项 {{type, params, reason}}，type 必须是 runbook 键之一。最多 2 项。"""
                resp = await llm.ainvoke([HumanMessage(content=prompt)])
                text = resp.content.strip()
                if "```" in text:
                    text = text.split("```")[1].removeprefix("json").strip()
                data = json.loads(text)
                if isinstance(data, list):
                    return self._normalize_actions(data)
            except Exception as exc:  # noqa: BLE001
                logger.debug("remediate.llm.failed", error=str(exc)[:80])

        actions: list[dict] = []
        low = (root + rec + inc.title).lower()
        if any(k in low for k in ("crashloop", "oom", "pod", "重启", "restart")):
            actions.append({
                "type": "restart_pod",
                "params": {"namespace": services[0] if services else "default"},
                "reason": "疑似 Pod 级故障，可尝试重启",
                **RUNBOOKS["restart_pod"],
            })
        elif any(k in low for k in ("deploy", "发布", "rollback", "版本")):
            actions.append({
                "type": "rollback_deploy",
                "params": {"service": services[0] if services else ""},
                "reason": "疑似发布引入，建议回滚",
                **RUNBOOKS["rollback_deploy"],
            })
        else:
            actions.append({
                "type": "manual",
                "params": {},
                "reason": rec or "需人工确认修复步骤",
                **RUNBOOKS["manual"],
            })
        return actions

    def _normalize_actions(self, raw: list) -> list[dict]:
        out = []
        for item in raw:
            t = item.get("type", "manual")
            meta = RUNBOOKS.get(t, RUNBOOKS["manual"])
            out.append({
                "type": t,
                "params": item.get("params") or {},
                "reason": item.get("reason") or meta["description"],
                "label": meta["label"],
                "risk": meta["risk"],
                "description": meta["description"],
            })
        return out[:3]

    async def run(self, context: dict) -> dict:
        return await self.plan(context.get("incident_id", ""), triggered_by=context.get("triggered_by", "manual"))
