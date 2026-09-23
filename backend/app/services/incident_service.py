# ============================================================
# app/services/incident_service.py — 事件创建、去重、Alertmanager 解析
# ============================================================

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.incident import Incident, IncidentEvent
from app.rag.ingest import ingest

logger = get_logger("incident_service")

_SEVERITY_MAP = {
    "critical": "critical",
    "error": "critical",
    "warning": "warning",
    "warn": "warning",
    "info": "info",
    "none": "info",
}


def compute_fingerprint(source: str, title: str, labels: dict[str, Any] | None = None) -> str:
    payload = f"{source}|{title}|{json.dumps(labels or {}, sort_keys=True, ensure_ascii=False)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:64]


def map_severity(raw: str) -> str:
    return _SEVERITY_MAP.get((raw or "warning").lower(), "warning")


def extract_services(labels: dict[str, Any]) -> list[str]:
    for key in ("service", "serviceName", "job", "app", "instance"):
        val = labels.get(key)
        if val and isinstance(val, str):
            return [val.split(":")[0]]
    return []


def parse_alertmanager_payload(body: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = body.get("alerts") or []
    parsed: list[dict[str, Any]] = []
    for alert in alerts:
        labels = alert.get("labels") or {}
        annotations = alert.get("annotations") or {}
        title = annotations.get("summary") or annotations.get("title") or labels.get("alertname") or "Unknown alert"
        status = alert.get("status", "firing")
        parsed.append({
            "title": title,
            "severity": map_severity(labels.get("severity") or labels.get("level") or "warning"),
            "source": "prometheus",
            "affected_services": extract_services(labels),
            "detail": {"labels": labels, "annotations": annotations, "startsAt": alert.get("startsAt"), "endsAt": alert.get("endsAt"), "generatorURL": alert.get("generatorURL")},
            "fingerprint": alert.get("fingerprint") or compute_fingerprint("prometheus", title, labels),
            "status": "resolved" if status == "resolved" else "firing",
        })
    return parsed


async def upsert_incident(
    db: AsyncSession,
    *,
    title: str,
    severity: str = "warning",
    source: str = "prometheus",
    affected_services: list[str] | None = None,
    detail: dict[str, Any] | None = None,
    fingerprint: str = "",
    status: str = "firing",
    actor: str = "system",
) -> tuple[Incident, bool]:
    """创建或更新事件。返回 (incident, is_new)。"""
    fp = fingerprint or compute_fingerprint(source, title, detail or {})
    existing = (await db.execute(select(Incident).where(Incident.fingerprint == fp))).scalar_one_or_none()

    if existing:
        if status == "resolved" and existing.status != "resolved":
            existing.status = "resolved"
            existing.resolved_at = datetime.now(timezone.utc)
            db.add(IncidentEvent(incident_id=str(existing.id), event_type="status_change",
                                 actor=actor, content="告警已恢复"))
        existing.extra = {**(existing.extra or {}), **(detail or {})}
        existing.severity = severity or existing.severity
        if affected_services:
            existing.affected_services = affected_services
        await db.flush()
        return existing, False

    inc = Incident(
        fingerprint=fp,
        title=title,
        severity=map_severity(severity),
        status=status if status in {"firing", "resolved"} else "firing",
        source=source,
        affected_services=affected_services or [],
        extra=detail or {},
    )
    if status == "resolved":
        inc.resolved_at = datetime.now(timezone.utc)
    db.add(inc)
    await db.flush()
    db.add(IncidentEvent(incident_id=str(inc.id), event_type="created", actor=actor, content=f"事件创建：{title}"))
    await db.flush()
    return inc, True


async def is_repeat_incident(db: AsyncSession, title: str, services: list[str], days: int = 7) -> bool:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await db.execute(
        select(Incident).where(Incident.created_at >= since).order_by(Incident.created_at.desc()).limit(200)
    )).scalars().all()
    title_lower = title.lower()
    for row in rows:
        if title_lower in row.title.lower() or row.title.lower() in title_lower:
            if not services or any(s in (row.affected_services or []) for s in services):
                return True
    return False


async def ingest_incident_knowledge(db: AsyncSession, incident: Incident, report: dict | None = None) -> int:
    content_parts = [f"事件：{incident.title}", f"严重程度：{incident.severity}", f"服务：{', '.join(incident.affected_services or [])}"]
    if report:
        content_parts.extend([
            f"根因：{report.get('root_cause', '')}",
            f"建议：{report.get('recommendation', '')}",
            f"证据：{json.dumps(report.get('evidence', []), ensure_ascii=False)}",
        ])
    return await ingest(
        db,
        source_type="incident_resolution",
        title=incident.title,
        content="\n".join(content_parts),
        source_id=str(incident.id),
        metadata={"services": incident.affected_services or [], "severity": incident.severity},
    )


def build_postmortem(incident: Incident, events: list, reports: list) -> str:
    lines = [
        f"# Postmortem: {incident.title}",
        "",
        f"- **ID**: {incident.id}",
        f"- **Severity**: {incident.severity}",
        f"- **Status**: {incident.status}",
        f"- **Services**: {', '.join(incident.affected_services or [])}",
        f"- **Created**: {incident.created_at}",
        f"- **Resolved**: {incident.resolved_at or 'N/A'}",
        "",
        "## Timeline",
    ]
    for ev in events:
        lines.append(f"- [{ev.created_at}] {ev.actor}: {ev.content}")
    if reports:
        lines.extend(["", "## AI Analysis"])
        for r in reports:
            lines.extend([
                f"**Root cause**: {r.root_cause}",
                f"**Recommendation**: {r.recommendation}",
                f"**Confidence**: {r.confidence}",
                "",
            ])
    return "\n".join(lines)
