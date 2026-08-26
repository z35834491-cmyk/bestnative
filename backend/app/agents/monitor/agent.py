# ============================================================
# app/agents/monitor/agent.py — 监控巡检 Agent
# ============================================================

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentConfig, BaseAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.models.infra import Service
from app.services.agent_runs import finish_run, start_run
from app.services.prometheus import PrometheusClient

logger = get_logger("agent.monitor")

SYSTEM_PROMPT = """你是 SRE 监控巡检专家。根据服务状态与指标，输出简明巡检结论。"""


class MonitorAgent(BaseAgent):
    config = AgentConfig(name="monitor", system_prompt=SYSTEM_PROMPT, max_iterations=1)

    def __init__(self, db: AsyncSession):
        self.db = db
        self.prom = PrometheusClient()

    async def patrol(self, *, triggered_by: str = "scheduler") -> dict:
        run = await start_run(
            self.db,
            agent_type="monitor",
            title="全平台健康巡检",
            triggered_by=triggered_by,
        )
        try:
            services = (await self.db.execute(select(Service))).scalars().all()
            prom_ok = await self.prom.health()
            issues: list[dict] = []
            summary = {"healthy": 0, "degraded": 0, "critical": 0, "unknown": 0}

            for svc in services:
                health = svc.health or "unknown"
                summary[health if health in summary else "unknown"] = summary.get(health, 0) + 1
                problem = None
                if svc.replicas and svc.ready_replicas < svc.replicas:
                    problem = f"副本未就绪 {svc.ready_replicas}/{svc.replicas}"
                    health = "critical"
                elif health in ("critical", "degraded"):
                    problem = f"健康状态 {health}"
                if problem:
                    issues.append({
                        "service": svc.name,
                        "namespace": svc.namespace,
                        "health": health,
                        "problem": problem,
                        "replicas": f"{svc.ready_replicas}/{svc.replicas}",
                    })

            error_rates: list[dict] = []
            if prom_ok:
                try:
                    rows = await self.prom.query(
                        'topk(10, sum by (service) (rate(http_requests_total{status=~"5.."}[5m])))'
                    )
                    for row in rows[:10]:
                        svc_name = row.get("metric", {}).get("service") or row.get("metric", {}).get("job", "")
                        val = float(row.get("value") or 0)
                        if val > 0.01 and svc_name:
                            error_rates.append({"service": svc_name, "errorRate5m": round(val, 4)})
                except Exception as exc:  # noqa: BLE001
                    logger.debug("monitor.prom.errors", error=str(exc)[:80])

            output = {
                "checkedServices": len(services),
                "summary": summary,
                "issues": issues[:50],
                "prometheusConnected": prom_ok,
                "highErrorRates": error_rates,
            }
            await finish_run(self.db, run, output)
            return {"runId": str(run.id), **output}
        except Exception as exc:  # noqa: BLE001
            await finish_run(self.db, run, {}, error=str(exc)[:500])
            raise

    async def run(self, context: dict) -> dict:
        return await self.patrol(triggered_by=context.get("triggered_by", "manual"))
