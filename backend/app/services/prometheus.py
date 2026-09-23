# ============================================================
# app/services/prometheus.py — Prometheus 查询封装（支持多环境）
# ============================================================

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.environments import EnvironmentProfile, get_active_profile

logger = get_logger("obs.prometheus")


def prometheus_auth(profile: EnvironmentProfile | None = None) -> httpx.BasicAuth | None:
    user = (profile.prometheus_username if profile else settings.PROMETHEUS_USERNAME) or ""
    user = user.strip()
    password = settings.PROMETHEUS_PASSWORD or ""
    if user and password:
        return httpx.BasicAuth(user, password)
    return None


def prometheus_http_client(
    timeout: float = 15.0,
    profile: EnvironmentProfile | None = None,
) -> httpx.AsyncClient:
    profile = profile or get_active_profile()
    verify = profile.prometheus_ssl_verify if profile.prometheus_url else settings.PROMETHEUS_SSL_VERIFY
    return httpx.AsyncClient(timeout=timeout, verify=verify, auth=prometheus_auth(profile))


class PrometheusClient:
    def __init__(self, base_url: str | None = None, profile: EnvironmentProfile | None = None):
        self.profile = profile or get_active_profile()
        default_url = self.profile.prometheus_url or settings.PROMETHEUS_URL
        self.base_url = (base_url or default_url).rstrip("/")

    async def query(self, promql: str) -> list[dict]:
        """即时查询。返回 [{metric, value}]。"""
        if not self.base_url:
            return []
        async with prometheus_http_client(timeout=15, profile=self.profile) as client:
            r = await client.get(f"{self.base_url}/api/v1/query", params={"query": promql})
            r.raise_for_status()
            data = r.json()
        if data.get("status") != "success":
            logger.warning("prom.query.failed", promql=promql, resp=data)
            return []
        results = []
        for item in data["data"]["result"]:
            results.append({
                "metric": item.get("metric", {}),
                "value": item["value"][1] if "value" in item else None,
            })
        return results

    async def query_range(self, promql: str, start: str, end: str, step: str = "60s") -> list[dict]:
        if not self.base_url:
            return []
        async with prometheus_http_client(timeout=30, profile=self.profile) as client:
            r = await client.get(
                f"{self.base_url}/api/v1/query_range",
                params={"query": promql, "start": start, "end": end, "step": step},
            )
            r.raise_for_status()
            data = r.json()
        if data.get("status") != "success":
            return []
        return data["data"]["result"]

    async def health(self) -> bool:
        if not self.base_url:
            return False
        try:
            async with prometheus_http_client(timeout=5, profile=self.profile) as client:
                r = await client.get(f"{self.base_url}/-/healthy")
                return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def probe(self) -> tuple[bool, str]:
        if not self.base_url:
            return False, "未配置 Prometheus URL"
        try:
            results = await self.query("up")
            return True, f"{len(results)} targets"
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                return False, "HTTP 401，请配置 PROMETHEUS_USERNAME / PROMETHEUS_PASSWORD"
            return False, f"HTTP {exc.response.status_code}"
        except httpx.ConnectError:
            return False, "连接失败"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)[:100]
