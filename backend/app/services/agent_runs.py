# ============================================================
# app/services/agent_runs.py — AgentRun 读写辅助
# ============================================================

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun


async def start_run(
    db: AsyncSession,
    *,
    agent_type: str,
    title: str,
    triggered_by: str = "manual",
    input: dict | None = None,
) -> AgentRun:
    run = AgentRun(
        agent_type=agent_type,
        status="running",
        title=title,
        triggered_by=triggered_by,
        input=input or {},
    )
    db.add(run)
    await db.flush()
    return run


async def finish_run(db: AsyncSession, run: AgentRun, output: dict, *, error: str = "") -> AgentRun:
    run.status = "failed" if error else "done"
    run.output = output
    run.error = error
    run.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return run


async def latest_run(db: AsyncSession, agent_type: str) -> AgentRun | None:
    return (
        await db.execute(
            select(AgentRun)
            .where(AgentRun.agent_type == agent_type)
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def run_dict(r: AgentRun) -> dict:
    return {
        "id": str(r.id),
        "agentType": r.agent_type,
        "status": r.status,
        "title": r.title,
        "triggeredBy": r.triggered_by,
        "input": r.input or {},
        "output": r.output or {},
        "error": r.error or "",
        "createdAt": r.created_at,
        "completedAt": r.completed_at,
    }
