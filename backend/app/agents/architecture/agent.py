# ============================================================
# app/agents/architecture/agent.py — 架构容量 Agent
# ============================================================

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentConfig, BaseAgent
from app.agents.llm import get_llm
from app.core.config import settings
from app.core.logging import get_logger
from app.models.infra import Node, Service, ServiceDependency
from app.services.agent_runs import finish_run, start_run
from app.services.prometheus import PrometheusClient

logger = get_logger("agent.architecture")


class ArchitectureAgent(BaseAgent):
    config = AgentConfig(name="architecture", system_prompt="架构与容量评估")

    def __init__(self, db: AsyncSession):
        self.db = db
        self.prom = PrometheusClient()

    async def analyze(self, *, triggered_by: str = "scheduler") -> dict:
        run = await start_run(
            self.db,
            agent_type="architecture",
            title="架构容量评估",
            triggered_by=triggered_by,
        )
        try:
            services = (await self.db.execute(select(Service))).scalars().all()
            deps = (await self.db.execute(select(ServiceDependency))).scalars().all()
            nodes = (await self.db.execute(select(Node))).scalars().all()

            in_degree: Counter[str] = Counter()
            out_degree: Counter[str] = Counter()
            for d in deps:
                out_degree[d.source_id] += 1
                in_degree[d.target_id] += 1

            hotspots = []
            for svc in services:
                sid = str(svc.id)
                fan_out = out_degree.get(sid, 0)
                fan_in = in_degree.get(sid, 0)
                if fan_out >= 5 or fan_in >= 5:
                    hotspots.append({
                        "service": svc.name,
                        "namespace": svc.namespace,
                        "dependenciesOut": fan_out,
                        "dependenciesIn": fan_in,
                        "risk": "high" if fan_out >= 8 else "medium",
                        "note": "依赖集中，故障易扩散" if fan_out >= 5 else "被多处依赖，变更影响面大",
                    })

            single_replica = [
                {"service": s.name, "namespace": s.namespace, "replicas": s.replicas}
                for s in services
                if (s.replicas or 0) <= 1 and s.health != "healthy"
            ]

            cluster_cpu = None
            cluster_mem = None
            if await self.prom.health():
                try:
                    cpu_rows = await self.prom.query('sum(kube_node_status_allocatable{resource="cpu"})')
                    mem_rows = await self.prom.query('sum(kube_node_status_allocatable{resource="memory"})')
                    if cpu_rows:
                        cluster_cpu = float(cpu_rows[0].get("value") or 0)
                    if mem_rows:
                        cluster_mem = float(mem_rows[0].get("value") or 0) / 1024 / 1024 / 1024
                except Exception:  # noqa: BLE001
                    pass

            findings = {
                "serviceCount": len(services),
                "dependencyEdges": len(deps),
                "nodeCount": len(nodes),
                "hotspots": hotspots[:20],
                "singleReplicaRisk": single_replica[:20],
                "clusterAllocatable": {"cpuCores": cluster_cpu, "memGb": round(cluster_mem, 1) if cluster_mem else None},
            }
            findings["summary"] = await self._llm_summary(findings)
            await finish_run(self.db, run, findings)
            return {"runId": str(run.id), **findings}
        except Exception as exc:  # noqa: BLE001
            await finish_run(self.db, run, {}, error=str(exc)[:500])
            raise

    async def _llm_summary(self, findings: dict) -> str:
        if not settings.llm_configured:
            parts = []
            if findings["hotspots"]:
                parts.append(f"发现 {len(findings['hotspots'])} 个依赖热点")
            if findings["singleReplicaRisk"]:
                parts.append(f"{len(findings['singleReplicaRisk'])} 个单副本服务需关注")
            return "；".join(parts) or "架构状态正常，无明显瓶颈"

        try:
            from langchain_core.messages import HumanMessage
            import json
            llm = get_llm(temperature=0.2)
            resp = await llm.ainvoke([HumanMessage(content=f"用 2-3 句话总结架构风险（中文）：\n{json.dumps(findings, ensure_ascii=False, default=str)[:3000]}")])
            return (resp.content or "").strip()[:800]
        except Exception:  # noqa: BLE001
            return "架构分析完成，详见热点列表"

    async def run(self, context: dict) -> dict:
        return await self.analyze(triggered_by=context.get("triggered_by", "manual"))
