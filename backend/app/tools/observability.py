# ============================================================
# app/tools/observability.py — T0 常驻工具（可观测性核心）
# query_prometheus / search_es_logs /
# get_k8s_resource_status / get_k8s_topology
# ============================================================

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.infra import Service
from app.services.elasticsearch import search_logs
from app.services.prometheus import PrometheusClient
from app.tools.registry import ToolTier, register_tool

_prom = PrometheusClient()


@register_tool(
    name="query_prometheus", tier=ToolTier.T0_ALWAYS,
    description="执行 PromQL 查询获取实时指标（CPU/内存/延迟/错误率）",
    schema={
        "name": "query_prometheus",
        "description": "执行 PromQL 即时查询，返回指标值",
        "parameters": {
            "type": "object",
            "properties": {"promql": {"type": "string", "description": "PromQL 表达式"}},
            "required": ["promql"],
        },
    },
)
async def query_prometheus(promql: str) -> list[dict]:
    return await _prom.query(promql)


@register_tool(
    name="search_es_logs", tier=ToolTier.T0_ALWAYS,
    description="查询指定服务近 N 分钟的 ES 日志",
    schema={
        "name": "search_es_logs",
        "description": "按服务查询 Elasticsearch 日志",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "query": {"type": "string", "description": "关键词（默认 ERROR）"},
                "since_minutes": {"type": "integer", "default": 60},
            },
            "required": ["service"],
        },
    },
)
async def search_es_logs(service: str, query: str = "ERROR", since_minutes: int = 60) -> list[dict]:
    return await search_logs(
        query=f"service:{service} AND level:{query}",
        index="logs-*",
        size=50,
        hours_back=max(1, since_minutes // 60),
    )


@register_tool(
    name="get_k8s_resource_status", tier=ToolTier.T0_ALWAYS,
    description="获取指定服务的副本/健康/镜像状态",
    schema={
        "name": "get_k8s_resource_status",
        "description": "查询服务的部署状态",
        "parameters": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
)
async def get_k8s_resource_status(service: str) -> dict:
    async with AsyncSessionLocal() as db:
        svc = (await db.execute(select(Service).where(Service.name == service))).scalars().first()
        if svc is None:
            return {"error": f"service {service} not found"}
        return {
            "name": svc.name, "namespace": svc.namespace, "health": svc.health,
            "replicas": svc.replicas, "ready_replicas": svc.ready_replicas,
            "image": svc.image, "version": svc.version,
        }


@register_tool(
    name="get_k8s_topology", tier=ToolTier.T0_ALWAYS,
    description="获取故障服务及其上下游 ±2 层依赖拓扑",
    schema={
        "name": "get_k8s_topology",
        "description": "获取服务依赖拓扑（仅故障服务邻域，节约 token）",
        "parameters": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
)
async def get_k8s_topology(service: str) -> dict:
    from app.models.infra import ServiceDependency
    async with AsyncSessionLocal() as db:
        svc = (await db.execute(select(Service).where(Service.name == service))).scalars().first()
        if svc is None:
            return {"error": f"service {service} not found"}
        deps = (await db.execute(
            select(ServiceDependency).where(ServiceDependency.source_id == str(svc.id))
        )).scalars().all()
        return {
            "service": service,
            "dependencies": [{"target": d.target_id, "detected_by": d.detected_by} for d in deps],
        }
