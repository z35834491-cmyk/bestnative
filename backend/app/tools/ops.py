# ============================================================
# app/tools/ops.py — T1/T3 运维操作工具
# ============================================================

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.incident import Incident
from app.providers.kubernetes import KubernetesProvider
from app.tools.registry import ToolTier, register_tool


def _k8s_provider() -> KubernetesProvider:
    return KubernetesProvider(settings.CLUSTER_NAME, {
        "in_cluster": settings.K8S_IN_CLUSTER,
        "kubeconfig": settings.KUBECONFIG or None,
        "context": settings.K8S_CONTEXT or None,
    })


@register_tool(
    name="list_recent_incidents", tier=ToolTier.T1_PLAN,
    description="列出最近的事件/告警",
    schema={
        "name": "list_recent_incidents",
        "description": "获取最近 N 条事件",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}},
        },
    },
)
async def list_recent_incidents(limit: int = 10) -> list[dict]:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Incident).order_by(Incident.created_at.desc()).limit(min(limit, 30))
        )).scalars().all()
        return [{
            "id": str(i.id), "title": i.title, "severity": i.severity,
            "status": i.status, "services": i.affected_services,
        } for i in rows]


@register_tool(
    name="search_knowledge", tier=ToolTier.T1_PLAN,
    description="搜索知识库",
    schema={
        "name": "search_knowledge",
        "description": "按关键词搜索知识库条目",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}},
            "required": ["query"],
        },
    },
)
async def search_knowledge(query: str, limit: int = 5) -> list[dict]:
    from app.rag.retriever import hybrid_search
    async with AsyncSessionLocal() as db:
        hits = await hybrid_search(db, query, top_k=min(limit, 10))
        return [{"title": h.get("title"), "content": (h.get("content") or "")[:300], "score": h.get("score")} for h in hits]


@register_tool(
    name="restart_pod", tier=ToolTier.T3_ACTION,
    description="重启指定 Pod（删除后由 Deployment 重建）",
    schema={
        "name": "restart_pod",
        "description": "重启 Pod，需 namespace 和 pod 名",
        "parameters": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string"},
                "pod_name": {"type": "string"},
            },
            "required": ["namespace", "pod_name"],
        },
    },
)
async def restart_pod(namespace: str, pod_name: str) -> dict:
    if not settings.OPS_AUTO_REMEDIATE:
        return {"error": "自动修复未启用，请在平台设置开启 OPS_AUTO_REMEDIATE"}
    ok = await _k8s_provider().restart_pod(namespace=namespace, pod_name=pod_name)
    return {"restarted": ok, "namespace": namespace, "pod": pod_name}
