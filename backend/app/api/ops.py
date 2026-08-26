# ============================================================
# app/api/ops.py — 运维 Agent API（监控/成本/排班/助手/编排）
# ============================================================

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.architecture.agent import ArchitectureAgent
from app.agents.coordinator.agent import CoordinatorAgent
from app.agents.copilot.agent import CopilotAgent
from app.agents.cost.agent import CostAgent
from app.agents.knowledge.agent import KnowledgeAgent
from app.agents.monitor.agent import MonitorAgent
from app.agents.remediate.agent import RemediateAgent
from app.core.database import get_db
from app.core.deps import require_operator, require_user
from app.models.agent_run import AgentRun
from app.models.auth import User
from app.models.infra import Service
from app.models.schedule import Schedule
from app.services.agent_runs import latest_run, run_dict

router = APIRouter(prefix="/ops", tags=["ops"])


class CopilotChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict] = Field(default_factory=list)


class RemediateExecuteRequest(BaseModel):
    actionType: str
    params: dict = Field(default_factory=dict)


class CoordinatorRequest(BaseModel):
    pipeline: str = "daily_ops"
    context: dict = Field(default_factory=dict)


class ScheduleCreate(BaseModel):
    userId: str
    shiftDate: datetime
    shiftType: str = "day"
    note: str = ""


@router.get("/runs")
async def list_runs(
    agent: str | None = None,
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_user),
):
    q = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
    if agent:
        q = q.where(AgentRun.agent_type == agent)
    rows = (await db.execute(q)).scalars().all()
    return [run_dict(r) for r in rows]


# ---- 监控巡检 ----

@router.get("/monitor/summary")
async def monitor_summary(db: AsyncSession = Depends(get_db), _user: User = Depends(require_user)):
    services = (await db.execute(select(Service))).scalars().all()
    summary = {"healthy": 0, "degraded": 0, "critical": 0, "unknown": 0}
    for s in services:
        h = s.health or "unknown"
        summary[h if h in summary else "unknown"] = summary.get(h, 0) + 1
    latest = await latest_run(db, "monitor")
    return {
        "serviceCount": len(services),
        "healthSummary": summary,
        "latestPatrol": run_dict(latest) if latest else None,
    }


@router.post("/monitor/patrol")
async def trigger_patrol(db: AsyncSession = Depends(get_db), user: User = Depends(require_operator)):
    result = await MonitorAgent(db).patrol(triggered_by=user.username)
    await db.commit()
    return result


# ---- 成本 ----

@router.get("/cost/summary")
async def cost_summary(db: AsyncSession = Depends(get_db), _user: User = Depends(require_user)):
    latest = await latest_run(db, "cost")
    if latest and latest.status == "done" and latest.output:
        return {"cached": True, **latest.output, "run": run_dict(latest)}
    result = await CostAgent(db).analyze(triggered_by="api")
    await db.commit()
    return {"cached": False, **result}


@router.post("/cost/analyze")
async def trigger_cost(db: AsyncSession = Depends(get_db), user: User = Depends(require_operator)):
    result = await CostAgent(db).analyze(triggered_by=user.username)
    await db.commit()
    return result


# ---- 架构 ----

@router.get("/architecture/latest")
async def architecture_latest(db: AsyncSession = Depends(get_db), _user: User = Depends(require_user)):
    latest = await latest_run(db, "architecture")
    if latest and latest.status == "done":
        return {"run": run_dict(latest), **(latest.output or {})}
    return {"run": run_dict(latest) if latest else None, "summary": "尚未运行架构分析"}


@router.post("/architecture/analyze")
async def trigger_architecture(db: AsyncSession = Depends(get_db), user: User = Depends(require_operator)):
    result = await ArchitectureAgent(db).analyze(triggered_by=user.username)
    await db.commit()
    return result


# ---- 知识 ----

@router.get("/knowledge/stats")
async def knowledge_stats(db: AsyncSession = Depends(get_db), _user: User = Depends(require_user)):
    return await KnowledgeAgent(db).stats()


@router.post("/knowledge/archive/{incident_id}")
async def archive_knowledge(incident_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_operator)):
    result = await KnowledgeAgent(db).archive_incident(incident_id, triggered_by=user.username)
    await db.commit()
    return result


# ---- 修复 ----

@router.get("/remediate/{incident_id}/plan")
async def remediate_plan(incident_id: str, db: AsyncSession = Depends(get_db), _user: User = Depends(require_user)):
    return await RemediateAgent(db).plan(incident_id)


@router.post("/remediate/{incident_id}/plan")
async def create_remediate_plan(incident_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_operator)):
    result = await RemediateAgent(db).plan(incident_id, triggered_by=user.username)
    await db.commit()
    return result


@router.post("/remediate/{incident_id}/execute")
async def execute_remediate(
    incident_id: str,
    body: RemediateExecuteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_operator),
):
    result = await RemediateAgent(db).execute(incident_id, body.actionType, body.params)
    await db.commit()
    return result


# ---- 助手 ----

@router.post("/copilot/chat")
async def copilot_chat(body: CopilotChatRequest, db: AsyncSession = Depends(get_db), _user: User = Depends(require_user)):
    return await CopilotAgent(db).chat(body.message, body.history)


# ---- 编排 ----

@router.post("/coordinator/run")
async def coordinator_run(body: CoordinatorRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_operator)):
    ctx = {**(body.context or {}), "triggered_by": user.username}
    result = await CoordinatorAgent(db).run_pipeline(body.pipeline, ctx)
    await db.commit()
    return result


# ---- 排班 ----

@router.get("/users")
async def list_users_simple(db: AsyncSession = Depends(get_db), _user: User = Depends(require_user)):
    rows = (await db.execute(select(User).where(User.is_active == True))).scalars().all()  # noqa: E712
    return [{"id": str(u.id), "username": u.username, "displayName": u.display_name or u.username} for u in rows]


@router.get("/schedules")
async def list_schedules(db: AsyncSession = Depends(get_db), _user: User = Depends(require_user)):
    rows = (await db.execute(select(Schedule).order_by(Schedule.shift_date.desc()).limit(100))).scalars().all()
    users = {}
    for u in (await db.execute(select(User))).scalars().all():
        users[str(u.id)] = u.display_name or u.username
    return [{
        "id": str(s.id),
        "userId": str(s.user_id),
        "userName": users.get(str(s.user_id), str(s.user_id)[:8]),
        "shiftDate": s.shift_date,
        "shiftType": s.shift_type,
        "note": s.note,
    } for s in rows]


@router.post("/schedules")
async def create_schedule(body: ScheduleCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_operator)):
    user_row = (await db.execute(select(User).where(User.id == body.userId))).scalar_one_or_none()
    if user_row is None:
        raise HTTPException(404, "user not found")
    shift_date = body.shiftDate
    if shift_date.tzinfo is None:
        shift_date = shift_date.replace(tzinfo=timezone.utc)
    row = Schedule(user_id=str(user_row.id), shift_date=shift_date, shift_type=body.shiftType, note=body.note)
    db.add(row)
    await db.flush()
    await db.commit()
    return {"id": str(row.id), "status": "created"}


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_operator)):
    row = (await db.execute(select(Schedule).where(Schedule.id == schedule_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "not found")
    await db.delete(row)
    await db.commit()
    return {"status": "deleted"}


@router.get("/schedules/on-call")
async def on_call_now(db: AsyncSession = Depends(get_db), _user: User = Depends(require_user)):
    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(Schedule).order_by(Schedule.shift_date.desc()).limit(20))).scalars().all()
    users = {str(u.id): u.display_name or u.username for u in (await db.execute(select(User))).scalars().all()}
    current = []
    for s in rows:
        delta = abs((s.shift_date - now).total_seconds())
        if delta < 86400 * 2:
            current.append({
                "userId": str(s.user_id),
                "userName": users.get(str(s.user_id), "?"),
                "shiftDate": s.shift_date,
                "shiftType": s.shift_type,
            })
    return {"now": now, "shifts": current[:5]}
