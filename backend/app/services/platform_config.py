# ============================================================
# platform_config.py — 平台运行时配置（Redis 持久化）
# ============================================================

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.services.redis_cache import _get_client

logger = get_logger("platform_config")

KEY_AUTO_ROLLBACK = "platform:auto_rollback"


def get_auto_rollback() -> bool:
    client = _get_client()
    if client:
        try:
            val = client.get(KEY_AUTO_ROLLBACK)
            if val is not None:
                return val in ("1", "true", "True")
        except Exception as exc:  # noqa: BLE001
            logger.debug("platform_config.get.failed", error=str(exc)[:80])
    return settings.AUTO_ROLLBACK


def set_auto_rollback(enabled: bool) -> bool:
    client = _get_client()
    if not client:
        return get_auto_rollback()
    try:
        client.set(KEY_AUTO_ROLLBACK, "1" if enabled else "0")
        return enabled
    except Exception as exc:  # noqa: BLE001
        logger.warning("platform_config.set.failed", error=str(exc)[:80])
        return get_auto_rollback()
