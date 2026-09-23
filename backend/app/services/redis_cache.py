# ============================================================
# app/services/redis_cache.py — Redis 缓存（topology 等热数据）
# ============================================================

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("redis_cache")

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        import redis
        _client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        _client.ping()
        return _client
    except Exception as exc:  # noqa: BLE001
        logger.debug("redis.unavailable", error=str(exc)[:80])
        return None


async def cache_get(key: str) -> Any | None:
    client = _get_client()
    if not client:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


async def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    client = _get_client()
    if not client:
        return
    try:
        client.setex(key, ttl, json.dumps(value, default=str))
    except Exception as exc:  # noqa: BLE001
        logger.debug("redis.set.failed", error=str(exc)[:80])
