# ============================================================
# app/services/prometheus.py — Prometheus 查询封装
# ============================================================

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("obs.prometheus")


class PrometheusClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.PROMETHEUS_URL).rstrip("/")

    async def query(self, promql: str) -> list[dict]:
        """即时查询。返回 [{metric, value}]。"""
        async with httpx.AsyncClient(timeout=15) as client:
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
        """区间查询（用于发布前后指标对比）。"""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{self.base_url}/api/v1/query_range",
                                 params={"query": promql, "start": start, "end": end, "step": step})
            r.raise_for_status()
            data = r.json()
        if data.get("status") != "success":
            return []
        return data["data"]["result"]

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.base_url}/-/healthy")
                return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False
