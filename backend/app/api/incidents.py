# ============================================================
# app/api/incidents.py — 事件 API（列表/详情/触发诊断/状态流转）
# ============================================================

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.diagnosis.agent import DiagnosisAgent
from app.core.database import AsyncSessionLocal, get_db
from app.core.logging import get_logger
from app.models.incident import AnalysisReport, Incident, IncidentEvent
from app.schemas.incident import IncidentCreate, StatusUpdate

router = APIRouter(prefix="/incidents", tags=["incidents"])
logger = get_logger("api.incidents")

VALID_TRANSITIONS = {
    "firing": {"acknowledged", "resolved"},
    "acknowledged": {"analyzing", "resolved"},
    "analyzing": {"analyzed", "resolved"},
    "analyzed": {"resolved"},
    "resolved": set(),
}


async def _run_diagnosis(incident_id: str):
    async with AsyncSessionLocal() as db:
        inc = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
        if inc is None:
            return
        inc.status = "analyzing"
        await db.flush()
        try:
            result = await DiagnosisAgent(db).run({
                "title": inc.title, "severity": inc.severity,
                "affected_services": inc.affected_services or [],
                "alert_detail": inc.extra,
            })
            report = AnalysisReport(
                incident_id=incident_id,
                root_cause=result.get("root_cause", ""),
                evidence=result.get("evidence", []),
                recommendation=result.get("recommendation", ""),
                confidence=result.get("confidence", "medium"),
                can_auto_fix=result.get("can_auto_fix", False),
                llm_tokens=result.get("tokens", 0),
            )
            db.add(report)
            inc.status = "analyzed"
            db.add(IncidentEvent(incident_id=incident_id, event_type="agent_action",
                                 actor="diagnosis_agent", content="根因分析完成"))
            await db.commit()
        except Exception as e:  # noqa: BLE001
            logger.error("diagnosis.failed", incident=incident_id, error=str(e))
            await db.rollback()


@router.get("")
async def list_incidents(db: AsyncSession = Depends(get_db),
                         status: str | None = None, limit: int = Query(50, le=200)):
    q = select(Incident)
    if status:
        q = q.where(Incident.status == status)
    q = q.order_by(Incident.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [_inc_dict(i) for i in rows]


@router.get("/{incident_id}")
async def get_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    inc = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if inc is None:
        return {"error": "not found"}
    events = (await db.execute(
        select(IncidentEvent).where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.created_at)
    )).scalars().all()
    reports = (await db.execute(
        select(AnalysisReport).where(AnalysisReport.incident_id == incident_id)
    )).scalars().all()
    d = _inc_dict(inc)
    d["timeline"] = [{"type": e.event_type, "actor": e.actor, "content": e.content,
                      "at": e.created_at} for e in events]
    d["reports"] = [{"rootCause": r.root_cause, "evidence": r.evidence,
                     "recommendation": r.recommendation, "confidence": r.confidence,
                     "canAutoFix": r.can_auto_fix, "tokens": r.llm_tokens} for r in reports]
    return d


@router.post("/{incident_id}/diagnose")
async def diagnose(incident_id: str, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """触发诊断 Agent 分析（异步）。"""
    inc = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if inc is None:
        return {"error": "not found"}
    bg.add_task(_run_diagnosis, incident_id)
    return {"status": "diagnosis_started", "incident_id": incident_id}


@router.patch("/{incident_id}/status")
async def update_status(incident_id: str, body: StatusUpdate, db: AsyncSession = Depends(get_db)):
    inc = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if inc is None:
        return {"error": "not found"}
    if body.status not in VALID_TRANSITIONS.get(inc.status, set()):
        return {"error": f"invalid transition {inc.status} → {body.status}"}
    inc.status = body.status
    if body.status == "resolved":
        inc.resolved_at = datetime.now(timezone.utc)
    db.add(IncidentEvent(incident_id=incident_id, event_type="status_change",
                         actor=body.actor or "user", content=f"状态 → {body.status}"))
    await db.commit()
    return {"status": "ok", "new_status": body.status}


def _inc_dict(i: Incident) -> dict:
    return {
        "id": str(i.id), "title": i.title, "severity": i.severity, "status": i.status,
        "source": i.source, "affectedServices": i.affected_services,
        "assignee": i.assignee, "createdAt": i.created_at, "resolvedAt": i.resolved_at,
    }
