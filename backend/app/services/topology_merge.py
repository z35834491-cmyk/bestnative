# ============================================================
# app/services/topology_merge.py — 合并 K8s 发现的中间件到 Trace 拓扑
# ============================================================

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.infra import Middleware, Service, ServiceDependency
from app.services.trace_topology import _node_label


def _mw_node_id(mw_type: str) -> str:
    return f"middleware:{mw_type}"


async def enrich_trace_graph_with_discovery(db: AsyncSession, graph: dict[str, Any]) -> dict[str, Any]:
    """把 DB 中 K8s/桥接发现的中间件与依赖边补进 Trace 图（Trace 未命中时仍可见 MySQL/Redis 等）。"""
    middlewares = (await db.execute(select(Middleware))).scalars().all()
    if not middlewares:
        return graph

    services = (await db.execute(select(Service))).scalars().all()
    deps = (await db.execute(select(ServiceDependency))).scalars().all()
    svc_by_id = {str(s.id): s for s in services}
    mw_by_id = {str(m.id): m for m in middlewares}

    nodes: list[dict[str, Any]] = list(graph.get("nodes") or [])
    edges: list[dict[str, Any]] = list(graph.get("edges") or [])
    node_index = {n["id"]: n for n in nodes}
    node_index.update({n["name"]: n for n in nodes})
    edge_keys = {(e.get("from") or e.get("source"), e.get("to") or e.get("target")) for e in edges}

    # 按类型聚合：Trace 图用 middleware:mysql 这类 id
    by_type: dict[str, Middleware] = {}
    for mw in middlewares:
        if mw.type and mw.type not in by_type:
            by_type[mw.type] = mw

    for mw_type, mw in by_type.items():
        mid_id = _mw_node_id(mw_type)
        if mid_id not in node_index:
            node = {
                "id": mid_id,
                "name": _node_label(mw_type),
                "type": "middleware",
                "namespace": "discovered",
                "health": mw.health or "unknown",
                "component": mw_type,
                "host": mw.host,
                "port": mw.port,
                "traceCount": 0,
                "errorCount": 0,
                "lastSeen": "",
            }
            nodes.append(node)
            node_index[mid_id] = node
            node_index[node["name"]] = node
        else:
            existing = node_index[mid_id]
            if not existing.get("host") and mw.host:
                existing["host"] = mw.host
                existing["port"] = mw.port

    for dep in deps:
        if dep.target_type != "middleware" or dep.source_type != "service":
            continue
        svc = svc_by_id.get(dep.source_id)
        mw = mw_by_id.get(dep.target_id)
        if not svc or not mw or not mw.type:
            continue
        src_id = svc.name
        tgt_id = _mw_node_id(mw.type)
        if (src_id, tgt_id) in edge_keys:
            continue
        edges.append({
            "from": src_id,
            "to": tgt_id,
            "source": src_id,
            "target": tgt_id,
            "detectedBy": dep.detected_by or "discovered",
            "traceCount": 0,
            "errorCount": 0,
            "health": "healthy",
        })
        edge_keys.add((src_id, tgt_id))

    graph["nodes"] = nodes
    graph["edges"] = edges
    return graph
