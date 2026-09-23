# ============================================================
# app/api/incidents.py — 事件 API（CRUD + Alertmanager + 诊断）
# ============================================================

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.diagnosis.agent import DiagnosisAgent
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.deps import require_operator, require_user
from app.core.logging import get_logger
from app.models.deployment import Deployment
from app.models.incident import AnalysisReport, Incident, IncidentEvent
from app.models.auth import User
from app.schemas.incident import IncidentCreate, StatusUpdate
from app.services.incident_service import (
    build_postmortem,
    is_repeat_incident,
    parse_alertmanager_payload,
    upsert_incident,
)
from app.services.maintenance import is_suppressed
from app.services.notifications import notify_incident

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
                extra={"tool_calls": result.get("tool_calls", []), "similar_incidents": result.get("similar_incidents", [])},
            )
            db.add(report)
            inc.status = "analyzed"
            db.add(IncidentEvent(incident_id=incident_id, event_type="agent_action",
                                 actor="diagnosis_agent", content="根因分析完成"))
            if result.get("can_auto_fix"):
                try:
                    from app.agents.remediate.agent import RemediateAgent
                    plan = await RemediateAgent(db).plan(incident_id, triggered_by="diagnosis")
                    db.add(IncidentEvent(incident_id=incident_id, event_type="agent_action",
                                         actor="remediate_agent",
                                         content=f"已生成修复方案（{len(plan.get('actions', []))} 项）"))
                except Exception as re:  # noqa: BLE001
                    logger.debug("remediate.plan.failed", error=str(re)[:80])
            await db.commit()
            await notify_incident(inc, "analyzed")
        except Exception as e:  # noqa: BLE001
            logger.error("diagnosis.failed", incident=incident_id, error=str(e))
            await db.rollback()


async def _maybe_auto_diagnose(incident_id: str, bg: BackgroundTasks):
    if settings.AUTO_DIAGNOSE_ON_ALERT and settings.llm_configured:
        bg.add_task(_run_diagnosis, incident_id)


@router.get("")
async def list_incidents(db: AsyncSession = Depends(get_db),
                         status: str | None = None, limit: int = Query(50, le=200),
                         _user: User = Depends(require_user)):
    q = select(Incident)
    if status:
        q = q.where(Incident.status == status)
    q = q.order_by(Incident.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [_inc_dict(i) for i in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_incident(body: IncidentCreate, bg: BackgroundTasks,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_operator)):
    for svc in body.affected_services:
        if is_suppressed(svc):
            return {"status": "suppressed", "reason": f"维护窗口中：{svc}"}
    repeat = await is_repeat_incident(db, body.title, body.affected_services)
    severity = "critical" if repeat and body.severity != "info" else body.severity
    inc, is_new = await upsert_incident(
        db, title=body.title, severity=severity, source=body.source,
        affected_services=body.affected_services, detail=body.detail,
        fingerprint=body.fingerprint, actor=user.username,
    )
    if is_new:
        db.add(IncidentEvent(incident_id=str(inc.id), event_type="created",
                             actor=user.username, content="手动创建事件"))
        await notify_incident(inc, "created")
    await db.commit()
    if is_new:
        await _maybe_auto_diagnose(str(inc.id), bg)
    return {"incident": _inc_dict(inc), "created": is_new, "repeat_detected": repeat}


@router.post("/alertmanager")
async def alertmanager_webhook(
    body: dict,
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    x_alert_token: str = Header(default="", alias="X-Alert-Token"),
    authorization: str = Header(default=""),
):
    token = x_alert_token
    if not token and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if settings.ALERTMANAGER_WEBHOOK_TOKEN and token != settings.ALERTMANAGER_WEBHOOK_TOKEN:
        if settings.is_production:
            raise HTTPException(status_code=401, detail="invalid alertmanager token")
    results = []
    for alert in parse_alertmanager_payload(body):
        services = alert["affected_services"]
        if any(is_suppressed(s) for s in services):
            results.append({"title": alert["title"], "status": "suppressed"})
            continue
        repeat = await is_repeat_incident(db, alert["title"], services)
        if repeat:
            alert["severity"] = "critical"
        inc, is_new = await upsert_incident(
            db, title=alert["title"], severity=alert["severity"], source=alert["source"],
            affected_services=services, detail=alert["detail"], fingerprint=alert["fingerprint"],
            status=alert["status"], actor="alertmanager",
        )
        results.append({"incident_id": str(inc.id), "created": is_new, "title": inc.title})
        if is_new and alert["status"] == "firing":
            await notify_incident(inc, "created")
            await _maybe_auto_diagnose(str(inc.id), bg)
    await db.commit()
    return {"status": "ok", "processed": len(results), "results": results}


@router.get("/{incident_id}")
async def get_incident(incident_id: str, db: AsyncSession = Depends(get_db),
                       _user: User = Depends(require_user)):
    inc = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if inc is None:
        raise HTTPException(status_code=404, detail="not found")
    events = (await db.execute(
        select(IncidentEvent).where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.created_at)
    )).scalars().all()
    reports = (await db.execute(
        select(AnalysisReport).where(AnalysisReport.incident_id == incident_id)
    )).scalars().all()
    recent_deploys = []
    if inc.affected_services:
        svc = inc.affected_services[0]
        deps = (await db.execute(
            select(Deployment).where(Deployment.service == svc)
            .order_by(Deployment.created_at.desc()).limit(5)
        )).scalars().all()
        recent_deploys = [_dep_brief(d) for d in deps]
    d = _inc_dict(inc)
    d["detail"] = inc.extra
    d["timeline"] = [{"type": e.event_type, "actor": e.actor, "content": e.content,
                      "at": e.created_at} for e in events]
    d["reports"] = [_report_dict(r) for r in reports]
    d["recentDeployments"] = recent_deploys
    return d


@router.post("/{incident_id}/diagnose")
async def diagnose(incident_id: str, bg: BackgroundTasks, db: AsyncSession = Depends(get_db),
                   user: User = Depends(require_operator)):
    inc = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if inc is None:
        raise HTTPException(status_code=404, detail="not found")
    bg.add_task(_run_diagnosis, incident_id)
    db.add(IncidentEvent(incident_id=incident_id, event_type="agent_action",
                         actor=user.username, content="触发 AI 诊断"))
    await db.commit()
    return {"status": "diagnosis_started", "incident_id": incident_id}


@router.patch("/{incident_id}/status")
async def update_status(incident_id: str, body: StatusUpdate, bg: BackgroundTasks,
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_operator)):
    inc = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if inc is None:
        raise HTTPException(status_code=404, detail="not found")
    if body.status not in VALID_TRANSITIONS.get(inc.status, set()):
        raise HTTPException(status_code=400, detail=f"invalid transition {inc.status} → {body.status}")
    inc.status = body.status
    if body.status == "resolved":
        inc.resolved_at = datetime.now(timezone.utc)
        try:
            from app.agents.knowledge.agent import KnowledgeAgent
            await KnowledgeAgent(db).archive_incident(incident_id, triggered_by=user.username)
        except Exception as e:  # noqa: BLE001
            logger.warning("incident.knowledge.ingest.failed", error=str(e))
        await notify_incident(inc, "resolved")
    db.add(IncidentEvent(incident_id=incident_id, event_type="status_change",
                         actor=body.actor or user.username, content=f"状态 → {body.status}"))
    await db.commit()
    return {"status": "ok", "new_status": body.status}


@router.get("/{incident_id}/postmortem")
async def postmortem(incident_id: str, db: AsyncSession = Depends(get_db),
                     _user: User = Depends(require_user)):
    inc = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if inc is None:
        raise HTTPException(status_code=404, detail="not found")
    events = (await db.execute(
        select(IncidentEvent).where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.created_at)
    )).scalars().all()
    reports = (await db.execute(
        select(AnalysisReport).where(AnalysisReport.incident_id == incident_id)
    )).scalars().all()
    md = build_postmortem(inc, events, reports)
    return {"markdown": md, "incidentId": str(inc.id)}


def _inc_dict(i: Incident) -> dict:
    return {
        "id": str(i.id), "title": i.title, "severity": i.severity, "status": i.status,
        "source": i.source, "affectedServices": i.affected_services,
        "assignee": i.assignee, "createdAt": i.created_at, "resolvedAt": i.resolved_at,
    }


def _report_dict(r: AnalysisReport) -> dict:
    extra = r.extra or {}
    return {
        "rootCause": r.root_cause, "evidence": r.evidence,
        "recommendation": r.recommendation, "confidence": r.confidence,
        "canAutoFix": r.can_auto_fix, "tokens": r.llm_tokens,
        "toolCalls": extra.get("tool_calls", []),
    }


def _dep_brief(d: Deployment) -> dict:
    return {
        "id": str(d.id), "service": d.service, "version": d.version,
        "status": d.status, "startedAt": d.started_at, "commitMessage": d.commit_message,
    }
