# ============================================================
# app/services/build_observer.py — CI 构建外挂观测
# 构建完成后：记录 → 失败回滚+分析 → 慢构建优化建议 → 通知
# ============================================================

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.change.agent import ChangeAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.models.deployment import Deployment
from app.services.platform_config import get_auto_rollback

logger = get_logger("build_observer")

_FAIL = {"failed", "failure", "error"}
_SUCCESS = {"success", "passed", "ok"}


def _norm_status(raw: str) -> str:
    s = (raw or "success").lower()
    if s in _FAIL:
        return "failed"
    if s in {"canceled", "cancelled", "skipped"}:
        return "canceled"
    return "success"


async def mark_latest(db: AsyncSession, service: str, deployment_id: str) -> None:
    await db.execute(
        update(Deployment)
        .where(Deployment.service == service, Deployment.id != deployment_id)
        .values(is_latest=False)
    )
    await db.execute(
        update(Deployment).where(Deployment.id == deployment_id).values(is_latest=True)
    )


async def prune_history(db: AsyncSession, service: str) -> None:
    limit = max(1, settings.BUILD_HISTORY_PER_SERVICE)
    subq = (
        select(Deployment.id)
        .where(Deployment.service == service)
        .order_by(Deployment.created_at.desc())
        .offset(limit)
    )
    await db.execute(delete(Deployment).where(Deployment.id.in_(subq)))


async def historical_avg_duration(db: AsyncSession, service: str, exclude_id: str = "") -> float | None:
    q = (
        select(Deployment.build_duration_sec)
        .where(
            Deployment.service == service,
            Deployment.build_status == "success",
            Deployment.build_duration_sec > 0,
        )
        .order_by(Deployment.created_at.desc())
        .limit(10)
    )
    if exclude_id:
        q = q.where(Deployment.id != exclude_id)
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return None
    return float(mean(rows))


def is_slow_build(duration_sec: int, baseline: float | None) -> bool:
    if duration_sec <= 0:
        return False
    if duration_sec >= settings.BUILD_SLOW_THRESHOLD_SEC:
        return True
    if baseline and duration_sec >= baseline * settings.BUILD_SLOW_RATIO:
        return True
    return False


def _stage_dicts(stages: list) -> list[dict]:
    out = []
    for s in stages or []:
        if hasattr(s, "model_dump"):
            d = s.model_dump()
        elif isinstance(s, dict):
            d = s
        else:
            continue
        out.append({
            "stage": d.get("name", "unknown"),
            "status": d.get("status", "success"),
            "detail": f"{d.get('duration_sec', 0):.0f}s",
            "duration_sec": d.get("duration_sec", 0),
            "log_excerpt": (d.get("log_excerpt") or "")[:500],
        })
    return out


async def _ai_analyze_failure(dep: Deployment) -> str:
    stages_text = "\n".join(
        f"- {s.get('stage')}: {s.get('status')} ({s.get('duration_sec', 0)}s)"
        for s in (dep.stages or [])
    )
    log_tail = (dep.failure_reason or "")[:6000]
    prompt = f"""你是 CI/CD 专家。以下构建失败，请用中文简要说明：
1. 最可能的失败原因（1-2 句）
2. 建议修复步骤（3-5 条 bullet）
3. 是否需要回滚线上版本（是/否 + 理由）

项目：{dep.project or dep.service}
服务：{dep.service}
版本：{dep.version}
提交：{dep.commit_message}
阶段耗时：
{stages_text or '（未提供）'}

失败日志（末尾）：
{log_tail or '（无日志）'}"""
    return await _llm(prompt)


async def _ai_analyze_slow_build(dep: Deployment, baseline: float | None) -> str:
    stages = sorted(dep.stages or [], key=lambda x: x.get("duration_sec", 0), reverse=True)
    stages_text = "\n".join(
        f"- {s.get('stage')}: {s.get('duration_sec', 0):.0f}s ({s.get('status')})"
        for s in stages
    )
    prompt = f"""你是 CI/CD 性能优化专家。以下构建偏慢，请用中文给出可落地的优化建议：
1. 瓶颈阶段判断（哪个 stage 最慢、占多少比例）
2. 具体优化措施（缓存、并行、镜像分层、依赖下载、Maven/Gradle 调优等）
3. 流程是否合理（有无冗余 stage、可合并步骤）
4. 预期可节省的时间（估算）

项目：{dep.project or dep.service}
服务：{dep.service}
本次耗时：{dep.build_duration_sec}s
历史均值：{f'{baseline:.0f}s' if baseline else '无历史数据'}
阈值：{settings.BUILD_SLOW_THRESHOLD_SEC}s

各阶段：
{stages_text or '（未提供阶段明细，请给出通用 Maven/Docker CI 优化建议）'}"""
    return await _llm(prompt)


async def _llm(prompt: str) -> str:
    try:
        from langchain_core.messages import HumanMessage
        from app.agents.llm import get_llm
        resp = await get_llm(temperature=0.2).ainvoke([HumanMessage(content=prompt)])
        return str(resp.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_observer.llm.failed", error=str(exc)[:120])
        return f"（AI 分析暂不可用：{exc}）"


async def finalize_success_build(db: AsyncSession, deployment_id: str, service: str) -> None:
    """成功构建：仅入库标记完成，不通知、不 LLM。"""
    dep = (await db.execute(select(Deployment).where(Deployment.id == deployment_id))).scalar_one_or_none()
    if dep:
        dep.status = "success"
        dep.build_status = "success"
        dep.completed_at = datetime.now(timezone.utc)
    await prune_history(db, service)
    await db.commit()


async def process_build(db: AsyncSession, deployment_id: str) -> dict:
    dep = (await db.execute(select(Deployment).where(Deployment.id == deployment_id))).scalar_one_or_none()
    if dep is None:
        return {"error": "not found"}

    build_status = _norm_status(dep.build_status or dep.status)
    dep.build_status = build_status
    dep.status = build_status
    baseline = await historical_avg_duration(db, dep.service, str(dep.id))
    slow = build_status == "success" and is_slow_build(dep.build_duration_sec, baseline)

    dep.extra = {
        **(dep.extra or {}),
        "slow_build": slow,
        "baseline_duration_sec": baseline,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    if build_status == "failed":
        extra = dep.extra or {}
        failure_kind = extra.get("failure_kind", "build")
        from app.services.build_failure import clean_build_log, fetch_pod_startup_logs
        if not dep.failure_reason and extra.get("failure_log"):
            dep.failure_reason = clean_build_log(str(extra["failure_log"]))[:8000]
        if failure_kind == "startup" and not (dep.failure_reason or "").strip():
            branch = extra.get("branch", "")
            pod_log = fetch_pod_startup_logs(dep.service, branch)
            if pod_log:
                dep.failure_reason = clean_build_log(pod_log)[:8000]
                dep.extra = {**extra, "failure_log": dep.failure_reason}
        rolled = False
        if get_auto_rollback() and dep.argocd_app:
            from app.services.argocd_client import rollback_app
            rolled = await rollback_app(dep)
            if rolled:
                dep.status = "rolled_back"
    elif slow and settings.BUILD_NOTIFY_SLOW:
        dep.optimization_tips = await _ai_analyze_slow_build(dep, baseline)
        dep.extra["slow_build"] = True
    else:
        dep.status = "success"
        # 成功构建不发送 Slack

    dep.completed_at = datetime.now(timezone.utc)
    await db.flush()
    await prune_history(db, dep.service)
    await db.commit()
    return {
        "deployment_id": deployment_id,
        "status": dep.status,
        "slow_build": slow,
        "baseline_sec": baseline,
    }
