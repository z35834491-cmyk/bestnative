# ============================================================
# app/services/maintenance.py — 维护窗口（抑制告警）
# ============================================================

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.services.redis_cache import _get_client

_KEY = "maintenance:windows"


def _load() -> list[dict]:
    client = _get_client()
    if not client:
        return []
    try:
        raw = client.get(_KEY)
        return json.loads(raw) if raw else []
    except Exception:  # noqa: BLE001
        return []


def _save(windows: list[dict]) -> None:
    client = _get_client()
    if not client:
        return
    try:
        client.set(_KEY, json.dumps(windows))
    except Exception:  # noqa: BLE001
        pass


def add_window(service: str, minutes: int, reason: str = "") -> dict:
    now = datetime.now(timezone.utc)
    windows = _load()
    entry = {
        "service": service,
        "reason": reason,
        "until": (now.timestamp() + minutes * 60),
        "created_at": now.isoformat(),
    }
    windows = [w for w in windows if w.get("service") != service]
    windows.append(entry)
    _save(windows)
    return entry


def is_suppressed(service: str) -> bool:
    now = datetime.now(timezone.utc).timestamp()
    for w in _load():
        if w.get("service") == service and float(w.get("until", 0)) > now:
            return True
    return False


def list_windows() -> list[dict]:
    now = datetime.now(timezone.utc).timestamp()
    active = [w for w in _load() if float(w.get("until", 0)) > now]
    _save(active)
    return active
