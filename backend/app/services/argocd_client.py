# ============================================================
# app/services/argocd_client.py — 按分支(dev/test)选择 ArgoCD 并执行 CLI
# ============================================================

from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models.deployment import Deployment

logger = get_logger("argocd_client")

_token_cache: dict[str, tuple[float, str]] = {}


@dataclass
class ArgoCDProfile:
    env: str
    server: str
    username: str
    password: str
    cli_extra: list[str]


def _cli_extra() -> list[str]:
    raw = (settings.ARGOCD_CLI_EXTRA or "--plaintext --insecure --grpc-web").split()
    return [x for x in raw if x]


def resolve_profile(branch: str = "") -> ArgoCDProfile | None:
    b = (branch or "").lower()
    if b == "dev" and settings.ARGOCD_DEV_SERVER:
        return ArgoCDProfile(
            env="dev",
            server=settings.ARGOCD_DEV_SERVER,
            username=settings.ARGOCD_DEV_USERNAME or "admin",
            password=settings.ARGOCD_DEV_PASSWORD or settings.ARGOCD_DEV_TOKEN,
            cli_extra=_cli_extra(),
        )
    if b == "test" and settings.ARGOCD_TEST_SERVER:
        return ArgoCDProfile(
            env="test",
            server=settings.ARGOCD_TEST_SERVER,
            username=settings.ARGOCD_TEST_USERNAME or "admin",
            password=settings.ARGOCD_TEST_PASSWORD or settings.ARGOCD_TEST_TOKEN,
            cli_extra=_cli_extra(),
        )
    # 兼容旧单环境配置
    if settings.ARGOCD_SERVER and (settings.ARGOCD_TOKEN or settings.ARGOCD_PASSWORD):
        return ArgoCDProfile(
            env="default",
            server=settings.ARGOCD_SERVER,
            username=settings.ARGOCD_USERNAME or "admin",
            password=settings.ARGOCD_PASSWORD or settings.ARGOCD_TOKEN,
            cli_extra=_cli_extra(),
        )
    return None


def profile_from_deployment(dep: Deployment) -> ArgoCDProfile | None:
    branch = (dep.extra or {}).get("branch", "")
    return resolve_profile(branch)


def _jwt_exp(token: str) -> float | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return float(data.get("exp", 0))
    except Exception:  # noqa: BLE001
        return None


async def get_auth_token(profile: ArgoCDProfile) -> str:
    """优先用静态 Token；否则账号密码换 session token（带缓存）。"""
    static = profile.password if profile.password.startswith("eyJ") else ""
    if static:
        return static

    cache_key = f"{profile.env}:{profile.server}:{profile.username}"
    cached = _token_cache.get(cache_key)
    now = time.time()
    if cached and cached[0] > now:
        return cached[1]

    base = profile.server.strip()
    if not base.startswith("http"):
        base = f"https://{base}"
    url = f"{base.rstrip('/')}/api/v1/session"
    async with httpx.AsyncClient(timeout=15, verify=settings.ARGOCD_SSL_VERIFY) as client:
        resp = await client.post(url, json={"username": profile.username, "password": profile.password})
        resp.raise_for_status()
        token = resp.json().get("token", "")
    if not token:
        raise RuntimeError(f"ArgoCD {profile.env} 登录未返回 token")

    exp = _jwt_exp(token) or (now + 3600)
    _token_cache[cache_key] = (exp - 300, token)
    return token


async def _run(cmd: list[str]) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
        if proc.returncode != 0:
            logger.warning("argocd.cmd.failed", cmd=cmd[:4], output=(out or b"").decode()[:300])
        return proc.returncode == 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("argocd.cmd.error", error=str(exc)[:120])
        return False


async def rollback_app(dep: Deployment) -> bool:
    profile = profile_from_deployment(dep)
    if profile is None:
        logger.info("argocd.rollback.skip", reason="no profile for branch", branch=(dep.extra or {}).get("branch"))
        return False
    app = dep.argocd_app or dep.service
    try:
        token = await get_auth_token(profile)
    except Exception as exc:  # noqa: BLE001
        logger.warning("argocd.auth.failed", env=profile.env, error=str(exc)[:120])
        return False
    cmd = [
        "argocd", "app", "rollback", app,
        "--server", profile.server,
        "--auth-token", token,
        *profile.cli_extra,
    ]
    ok = await _run(cmd)
    logger.info("argocd.rollback", env=profile.env, app=app, ok=ok)
    return ok


async def deploy_app(dep: Deployment) -> bool:
    profile = profile_from_deployment(dep)
    if profile is None:
        logger.info("argocd.deploy.skip", reason="no profile", branch=(dep.extra or {}).get("branch"))
        return not settings.ARGOCD_SERVER  # 无配置时模拟成功
    app = dep.argocd_app or dep.service
    try:
        token = await get_auth_token(profile)
    except Exception as exc:  # noqa: BLE001
        logger.warning("argocd.auth.failed", env=profile.env, error=str(exc)[:120])
        return False
    extra = profile.cli_extra
    if dep.version and not dep.version.startswith("unknown"):
        # 与现有 CI 一致：Helm revision / app version
        set_ok = await _run([
            "argocd", "app", "set", app, "--revision", dep.version,
            "--server", profile.server, "--auth-token", token, *extra,
        ])
        if not set_ok:
            return False
    return await _run([
        "argocd", "app", "sync", app,
        "--server", profile.server, "--auth-token", token, *extra,
        "--prune", "--force",
    ])


async def check_profile(profile: ArgoCDProfile) -> dict[str, Any]:
    try:
        token = await get_auth_token(profile)
        return {"env": profile.env, "server": profile.server, "status": "ok", "authenticated": bool(token)}
    except Exception as exc:  # noqa: BLE001
        return {"env": profile.env, "server": profile.server, "status": "error", "detail": str(exc)[:120]}
