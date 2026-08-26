# ============================================================
# app/agents/cost/agent.py — 成本分析 Agent
# ============================================================

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentConfig, BaseAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.models.infra import Node, Service
from app.services.agent_runs import finish_run, start_run

logger = get_logger("agent.cost")

HOURS_PER_MONTH = 730


class CostAgent(BaseAgent):
    config = AgentConfig(name="cost", system_prompt="成本分析")

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze(self, *, triggered_by: str = "scheduler") -> dict:
        run = await start_run(
            self.db,
            agent_type="cost",
            title="资源成本分析",
            triggered_by=triggered_by,
        )
        try:
            services = (await self.db.execute(select(Service))).scalars().all()
            nodes = (await self.db.execute(select(Node))).scalars().all()

            cpu_price = settings.COST_CPU_CORE_HOUR_USD
            mem_price = settings.COST_MEM_GB_HOUR_USD

            service_rows: list[dict] = []
            total_monthly = 0.0

            for svc in services:
                replicas = max(svc.replicas or svc.ready_replicas or 1, 1)
                cpu = (svc.cpu_usage or 0.5) * replicas
                mem = (svc.mem_usage or 1.0) * replicas
                monthly = cpu * cpu_price * HOURS_PER_MONTH + mem * mem_price * HOURS_PER_MONTH
                total_monthly += monthly
                idle = replicas > 1 and (svc.cpu_usage or 0) < 0.15
                service_rows.append({
                    "service": svc.name,
                    "namespace": svc.namespace,
                    "replicas": replicas,
                    "cpuCoresEst": round(cpu, 2),
                    "memGbEst": round(mem, 2),
                    "monthlyUsd": round(monthly, 2),
                    "health": svc.health,
                    "idleCandidate": idle,
                })

            service_rows.sort(key=lambda x: x["monthlyUsd"], reverse=True)

            node_capacity_cpu = sum(n.cpu_capacity or 0 for n in nodes)
            node_capacity_mem = sum(n.mem_capacity_gb or 0 for n in nodes)

            recommendations: list[dict] = []
            for row in service_rows:
                if row["idleCandidate"]:
                    save = round(row["monthlyUsd"] * 0.3, 2)
                    recommendations.append({
                        "type": "scale_down",
                        "service": row["service"],
                        "suggestion": f"副本偏多且 CPU 低，可考虑缩容 1 副本，约省 ${save}/月",
                        "priority": "medium",
                    })
                if row["health"] == "critical" and row["monthlyUsd"] > 50:
                    recommendations.append({
                        "type": "investigate",
                        "service": row["service"],
                        "suggestion": "服务异常但成本较高，优先修复避免浪费",
                        "priority": "high",
                    })

            if node_capacity_cpu and sum(r["cpuCoresEst"] for r in service_rows) < node_capacity_cpu * 0.3:
                recommendations.append({
                    "type": "cluster",
                    "service": "*",
                    "suggestion": "集群 CPU 利用率偏低，检查是否可合并节点或降配",
                    "priority": "low",
                })

            output = {
                "totalMonthlyUsd": round(total_monthly, 2),
                "serviceCount": len(service_rows),
                "nodeCount": len(nodes),
                "nodeCapacity": {"cpuCores": node_capacity_cpu, "memGb": node_capacity_mem},
                "services": service_rows[:100],
                "recommendations": recommendations[:20],
                "pricing": {"cpuCoreHourUsd": cpu_price, "memGbHourUsd": mem_price},
            }
            await finish_run(self.db, run, output)
            return {"runId": str(run.id), **output}
        except Exception as exc:  # noqa: BLE001
            await finish_run(self.db, run, {}, error=str(exc)[:500])
            raise

    async def run(self, context: dict) -> dict:
        return await self.analyze(triggered_by=context.get("triggered_by", "manual"))
