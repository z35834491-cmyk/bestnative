# ============================================================
# app/services/notifications.py — Slack 通知（事件生命周期）
# ============================================================

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models.incident import Incident

logger = get_logger("notifications")


async def notify_slack(text: str, webhook_url: str | None = None) -> bool:
    url = webhook_url or settings.SLACK_WEBHOOK_URL
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"text": text})
            resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("slack.notify.failed", error=str(exc)[:120])
        return False


async def notify_incident(incident: Incident, event: str) -> bool:
    emoji = {"created": "🚨", "analyzed": "🧠", "resolved": "✅"}.get(event, "📢")
    link = f"{settings.PUBLIC_URL.rstrip('/')}/incidents"
    text = (
        f"{emoji} *Shore 事件 {event}*\n"
        f"*{incident.title}* ({incident.severity})\n"
        f"服务: {', '.join(incident.affected_services or ['未知'])}\n"
        f"状态: {incident.status}\n"
        f"查看: {link}"
    )
    return await notify_slack(text)
