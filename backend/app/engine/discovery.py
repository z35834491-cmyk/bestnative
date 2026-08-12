# ============================================================
# app/engine/discovery.py — Discovery Engine
# 调度 Provider 发现资源 → upsert 到数据库（幂等）
# ============================================================

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.infra import Cluster, Middleware, Node, Service, ServiceDependency
from app.providers import create_provider
from app.providers.base import DiscoveryResult

logger = get_logger("engine.discovery")


class DiscoveryEngine:
    """自动发现引擎：运行 Provider，将结果幂等写入数据库。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run(self, provider_type: str, cluster_name: str, config: dict | None = None) -> dict:
        provider = create_provider(provider_type, cluster_name, config)
        result = await provider.discover()
        await self._persist(result)
        return {
            "cluster": cluster_name,
            "provider": provider_type,
            "nodes": len(result.nodes),
            "services": len(result.services),
            "middlewares": len(result.middlewares),
            "bridges": len(result.bridges),
        }

    async def _persist(self, result: DiscoveryResult) -> None:
        # ---- Cluster upsert ----
        cluster = (await self.db.execute(
            select(Cluster).where(Cluster.name == result.cluster_name)
        )).scalar_one_or_none()
        if cluster is None:
            cluster = Cluster(name=result.cluster_name, provider=result.provider)
            self.db.add(cluster)
            await self.db.flush()
        cluster.node_count = len(result.nodes)
        cluster.health = "healthy" if result.nodes else "unknown"

        # ---- Nodes ----
        for dn in result.nodes:
            node = (await self.db.execute(
                select(Node).where(Node.cluster_id == cluster.id, Node.name == dn.name)
            )).scalar_one_or_none()
            if node is None:
                node = Node(cluster_id=cluster.id, name=dn.name)
                self.db.add(node)
            node.internal_ip = dn.internal_ip
            node.role = dn.role
            node.cpu_capacity = dn.cpu_capacity
            node.mem_capacity_gb = dn.mem_capacity_gb
            node.health = dn.health

        # ---- Services ----
        for ds in result.services:
            svc = (await self.db.execute(
                select(Service).where(
                    Service.cluster_id == cluster.id,
                    Service.namespace == ds.namespace,
                    Service.name == ds.name,
                )
            )).scalar_one_or_none()
            if svc is None:
                svc = Service(cluster_id=cluster.id, name=ds.name, namespace=ds.namespace)
                self.db.add(svc)
            svc.kind = ds.kind
            svc.replicas = ds.replicas
            svc.ready_replicas = ds.ready_replicas
            svc.image = ds.image
            svc.version = ds.version
            svc.health = ds.health
            svc.extra = {"labels": ds.labels, "ports": ds.ports}

        # ---- Middlewares (去重 host:port) ----
        seen: set[tuple] = set()
        for dm in result.middlewares:
            key = (dm.host, dm.port)
            if key in seen:
                continue
            seen.add(key)
            mw = (await self.db.execute(
                select(Middleware).where(Middleware.host == dm.host, Middleware.port == dm.port)
            )).scalar_one_or_none()
            if mw is None:
                mw = Middleware(name=dm.name, type=dm.type, host=dm.host, port=dm.port)
                self.db.add(mw)
            mw.discovered_from = dm.discovered_from

        await self.db.flush()
        logger.info("discovery.persisted", cluster=result.cluster_name)
