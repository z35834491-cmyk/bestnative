# ============================================================
# app/api/topology.py — 拓扑与资源查询 + Pod 操作
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_operator
from app.models.auth import User
from app.core.logging import get_logger
from app.engine.discovery import DiscoveryEngine
from app.models.infra import Cluster, Middleware, Node, Service, ServiceDependency
from app.providers.kubernetes import KubernetesProvider
from app.schemas.topology import DiscoverRequest, TopologyGraph
from app.services.topology_merge import enrich_trace_graph_with_discovery
from app.services.trace_topology import get_trace_graph, get_trace_timeline

router = APIRouter(prefix="/topology", tags=["topology"])
logger = get_logger("api.topology")


@router.get("/graph", response_model=TopologyGraph)
async def get_topology(db: AsyncSession = Depends(get_db)):
    services = (await db.execute(select(Service))).scalars().all()
    middlewares = (await db.execute(select(Middleware))).scalars().all()
    deps = (await db.execute(select(ServiceDependency))).scalars().all()
    nodes = [
        {"id": str(s.id), "name": s.name, "type": "service",
         "namespace": s.namespace, "health": s.health,
         "replicas": s.replicas, "readyReplicas": s.ready_replicas, "version": s.version}
        for s in services
    ] + [
        {"id": str(m.id), "name": m.name, "type": "middleware",
         "namespace": m.type, "health": m.health, "host": m.host, "port": m.port}
        for m in middlewares
    ]
    edges = [{"source": d.source_id, "target": d.target_id, "detectedBy": d.detected_by} for d in deps]
    return {"nodes": nodes, "edges": edges}


@router.get("/trace-graph")
async def trace_graph(
    service: str = Query(""),
    hours: int = Query(1, ge=1, le=168),
    trace_limit: int = Query(80, ge=1, le=200),
    events_per_trace: int = Query(50, ge=5, le=80),
    trace_id: str = Query("", alias="trace_id"),
    db: AsyncSession = Depends(get_db),
):
    """从 ES trace_log 按 traceId 聚合真实调用链路；trace_id 精确搜索单条链路。"""
    try:
        graph = await get_trace_graph(
            service=service,
            hours=hours,
            trace_limit=trace_limit,
            events_per_trace=events_per_trace,
            trace_id=trace_id,
        )
        return await enrich_trace_graph_with_discovery(db, graph)
    except RuntimeError as exc:
        logger.warning("trace_graph.es.failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"Elasticsearch 查询失败：{exc}") from exc


@router.get("/traces/{trace_id}")
async def trace_timeline(
    trace_id: str,
    size: int = Query(150, ge=1, le=500),
    offset: int = Query(0, ge=0, le=5000),
):
    """查看单个 traceId 的完整日志时间线（分页）。"""
    try:
        return await get_trace_timeline(trace_id=trace_id, size=size, offset=offset)
    except RuntimeError as exc:
        logger.warning("trace_timeline.es.failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"Elasticsearch 查询失败：{exc}") from exc


@router.get("/clusters")
async def list_clusters(db: AsyncSession = Depends(get_db)):
    clusters = (await db.execute(select(Cluster))).scalars().all()
    result = []
    for c in clusters:
        node_count = (await db.execute(select(Node).where(Node.cluster_id == c.id))).scalars().all()
        result.append({"id": str(c.id), "name": c.name, "provider": c.provider, "health": c.health, "nodeCount": len(node_count)})
    return result


@router.post("/discover")
async def trigger_discovery(req: DiscoverRequest, db: AsyncSession = Depends(get_db),
                            _user: User = Depends(require_operator)):
    engine = DiscoveryEngine(db)
    summary = await engine.run(provider_type=req.provider_type, cluster_name=req.cluster_name, config=req.config)
    return {"status": "ok", "discovered": summary}


# ---- Pod 操作 ----


def _get_k8s_provider() -> KubernetesProvider | None:
    try:
        return KubernetesProvider(
            name="default",
            config={
                "kubeconfig": settings.KUBECONFIG or None,
                "in_cluster": settings.K8S_IN_CLUSTER,
                "context": settings.K8S_CONTEXT or None,
            },
        )
    except Exception:
        return None


@router.get("/services/{service_name}/pods")
async def get_service_pods(service_name: str, namespace: str = Query(""), db: AsyncSession = Depends(get_db)):
    """获取服务 Pod 列表（含实时指标）。"""
    svc = (await db.execute(select(Service).where(Service.name == service_name))).scalars().first()
    if svc is None:
        return {"error": "not found"}
    ns = namespace or svc.namespace
    provider = _get_k8s_provider()
    if provider is None:
        return {"error": "K8s provider not configured"}

    all_pods = await provider.list_pods(namespace=ns)
    pods = []
    for pod in all_pods:
        labels = pod.get("labels", {})
        pname = pod["name"]
        short = "-".join(pname.split("-")[:-2]) if pname.count("-") >= 2 else pname.split("-")[0] if "-" in pname else pname
        if (labels.get("app.kubernetes.io/name") == service_name
                or labels.get("app") == service_name
                or labels.get("app.kubernetes.io/instance") == service_name
                or short.startswith(service_name)):
            pods.append(pod)

    for pod in pods[:10]:
        m = await provider.get_pod_metrics(ns, pod["name"])
        if m:
            pod["metrics"] = m
    return {"service": service_name, "namespace": ns, "pods": pods, "source": "k8s"}


@router.get("/pods/{pod_name}/logs")
async def get_pod_logs(pod_name: str, namespace: str = Query(...), container: str = Query(""), tail: int = Query(200, le=2000)):
    provider = _get_k8s_provider()
    if provider is None:
        return {"error": "K8s provider not configured"}
    logs = await provider.get_pod_logs(namespace=namespace, pod_name=pod_name, container=container, tail_lines=tail)
    return {"pod": pod_name, "namespace": namespace, "logs": logs}


@router.post("/pods/{pod_name}/restart")
async def restart_pod(pod_name: str, namespace: str = Query(...),
                      _user: User = Depends(require_operator)):
    provider = _get_k8s_provider()
    if provider is None:
        return {"error": "K8s provider not configured"}
    ok = await provider.restart_pod(namespace=namespace, pod_name=pod_name)
    return {"pod": pod_name, "namespace": namespace, "restarted": ok}
