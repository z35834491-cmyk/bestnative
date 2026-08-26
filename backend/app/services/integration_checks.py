# ============================================================
# app/services/integration_checks.py — 集成健康检查（并行 + 短超时）
# ============================================================

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.prometheus import PrometheusClient

_CHECK_TIMEOUT = 6.0
_cache: tuple[float, dict[str, Any]] | None = None
_CACHE_TTL = 45.0


async def _check_database(db: AsyncSession) -> dict[str, Any]:
    try:
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=3.0)
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": str(exc)[:100]}


async def _check_prometheus() -> dict[str, Any]:
    url = (settings.PROMETHEUS_URL or "").strip()
    if not url:
        return {"status": "not_configured", "url": ""}

    prom = PrometheusClient()
    try:
        ok, detail = await asyncio.wait_for(prom.probe(), timeout=_CHECK_TIMEOUT)
        if ok:
            return {"status": "ok", "url": url, "detail": detail}
        if "401" in detail:
            return {"status": "error", "url": url, "detail": detail}
        return {"status": "degraded" if detail else "error", "url": url, "detail": detail}
    except asyncio.TimeoutError:
        return {"status": "error", "url": url, "detail": "探测超时"}


async def _check_elasticsearch() -> dict[str, Any]:
    if not settings.ES_HOST:
        return {"status": "not_configured"}
    try:
        from app.services.trace_topology import _es_hosts, _get_client
        client = _get_client()
        host = _es_hosts()[0]

        async def _ping() -> int:
            resp = await client.get(f"{host}/_cluster/health")
            return resp.status_code

        code = await asyncio.wait_for(_ping(), timeout=_CHECK_TIMEOUT)
        return {"status": "ok" if code == 200 else "error", "host": settings.ES_HOST}
    except asyncio.TimeoutError:
        return {"status": "error", "host": settings.ES_HOST, "detail": "连接超时"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "host": settings.ES_HOST, "detail": str(exc)[:80]}


async def _check_redis() -> dict[str, Any]:
    try:
        def _ping() -> bool:
            from app.services.redis_cache import _get_client
            return _get_client() is not None

        ok = await asyncio.wait_for(asyncio.to_thread(_ping), timeout=3.0)
        return {"status": "ok" if ok else "unavailable"}
    except Exception:  # noqa: BLE001
        return {"status": "unavailable"}


async def _check_gitlab() -> dict[str, Any]:
    if not settings.GITLAB_URL or not settings.GITLAB_TOKEN:
        return {"status": "not_configured", "scanEnabled": settings.GITLAB_CI_SCAN_ENABLED}
    try:
        base = settings.GITLAB_URL.strip().rstrip("/")
        if not base.startswith("http"):
            base = f"https://{base}"

        async def _user() -> int:
            async with httpx.AsyncClient(timeout=5.0, verify=settings.GITLAB_SSL_VERIFY) as client:
                resp = await client.get(
                    f"{base}/api/v4/user",
                    headers={"PRIVATE-TOKEN": settings.GITLAB_TOKEN},
                )
                return resp.status_code

        code = await asyncio.wait_for(_user(), timeout=_CHECK_TIMEOUT)
        return {
            "status": "ok" if code == 200 else "error",
            "url": settings.GITLAB_URL,
            "scanEnabled": settings.GITLAB_CI_SCAN_ENABLED,
            "detail": None if code == 200 else f"HTTP {code}",
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "url": settings.GITLAB_URL, "detail": str(exc)[:80]}


async def _check_argocd() -> dict[str, Any]:
    from app.services.argocd_client import check_profile, resolve_profile

    async def _one(branch: str) -> dict[str, Any]:
        p = resolve_profile(branch)
        if not p:
            return {}
        try:
            return await asyncio.wait_for(check_profile(p), timeout=_CHECK_TIMEOUT)
        except asyncio.TimeoutError:
            return {"env": p.env, "server": p.server, "status": "error", "detail": "登录超时"}
        except Exception as exc:  # noqa: BLE001
            return {"env": p.env, "server": p.server, "status": "error", "detail": str(exc)[:80]}

    dev, test = await asyncio.gather(_one("dev"), _one("test"))
    envs = [e for e in (dev, test) if e]
    if not envs:
        legacy = resolve_profile("")
        if legacy and legacy.env == "default":
            envs = [await _one("")]
    out: dict[str, Any] = {"environments": envs}
    if not envs:
        out["status"] = "not_configured"
    else:
        out["status"] = "ok" if all(e.get("status") == "ok" for e in envs) else "degraded"
    return out


async def run_integration_checks(db: AsyncSession) -> dict[str, Any]:
    db_r, prom_r, es_r, redis_r, gitlab_r, argocd_r = await asyncio.gather(
        _check_database(db),
        _check_prometheus(),
        _check_elasticsearch(),
        _check_redis(),
        _check_gitlab(),
        _check_argocd(),
    )
    return {
        "database": db_r,
        "prometheus": prom_r,
        "elasticsearch": es_r,
        "llm": {
            "status": "ok" if settings.llm_configured else "not_configured",
            "model": settings.llm_model,
            "base_url": settings.llm_base_url,
        },
        "redis": redis_r,
        "gitlab": gitlab_r,
        "argocd": argocd_r,
        "alertmanager": {
            "webhook": "/api/incidents/alertmanager",
            "token_required": bool(settings.ALERTMANAGER_WEBHOOK_TOKEN),
        },
        "environment": settings.ENVIRONMENT,
    }


async def get_integration_checks(db: AsyncSession, *, refresh: bool = False) -> dict[str, Any]:
    global _cache
    now = time.time()
    if not refresh and _cache and now - _cache[0] < _CACHE_TTL:
        return _cache[1]
    result = await run_integration_checks(db)
    _cache = (now, result)
    return result
