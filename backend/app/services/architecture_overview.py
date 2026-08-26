# ============================================================
# architecture_overview.py — 业务架构蓝图（配置 + 实时健康）
# ============================================================

from __future__ import annotations

import json
import os
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.environments import EnvironmentProfile, ensure_cluster_discovered, get_active_profile, get_cluster_id
from app.models.incident import Incident
from app.models.infra import Cluster, Middleware, Service


def _config_path() -> str:
    custom = os.environ.get("ARCHITECTURE_CONFIG_PATH", "").strip()
    if custom and os.path.isfile(custom):
        return custom
    return os.path.join(os.path.dirname(__file__), "..", "..", "config", "environment-architecture.json")


@lru_cache
def load_architecture_blueprint() -> dict:
    path = _config_path()
    if not os.path.isfile(path):
        return {"title": "业务环境", "tagline": "", "layers": [], "flows": [], "infra": [], "namespaces": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _match_health(name: str, svc_map: dict, mw_map: dict) -> dict:
    key = name.lower()
    for k, s in svc_map.items():
        if key in k or k in key:
            return {"health": s["health"], "replicas": s.get("replicas"), "readyReplicas": s.get("readyReplicas"), "found": True}
    for k, m in mw_map.items():
        if key in k or k in key:
            return {"health": m["health"], "host": m.get("host"), "found": True}
    return {"health": "unknown", "found": False}


async def build_home_overview(db: AsyncSession, profile: EnvironmentProfile | None = None) -> dict:
    profile = profile or get_active_profile()
    cluster_id = await ensure_cluster_discovered(db, profile)
    blueprint = load_architecture_blueprint()

    svc_q = select(Service)
    if cluster_id:
        svc_q = svc_q.where(Service.cluster_id == cluster_id)
        services = (await db.execute(svc_q)).scalars().all()
    else:
        services = []
    middlewares = (await db.execute(select(Middleware))).scalars().all()
    clusters = (await db.execute(select(Cluster).where(Cluster.name == profile.cluster_name))).scalars().all()

    svc_map = {s.name.lower(): {
        "health": s.health, "replicas": s.replicas, "readyReplicas": s.ready_replicas, "namespace": s.namespace,
    } for s in services}
    mw_map = {m.name.lower(): {"health": m.health, "host": m.host, "type": m.type} for m in middlewares}

    layers_out = []
    for layer in blueprint.get("layers", []):
        comps = []
        for c in layer.get("components", []):
            live = _match_health(c.get("name", ""), svc_map, mw_map)
            comps.append({**c, **live})
        layers_out.append({**layer, "components": comps})

    active_incidents = (
        await db.execute(
            select(func.count()).select_from(Incident).where(Incident.status != "resolved")
        )
    ).scalar() or 0

    recent = (
        await db.execute(
            select(Incident).order_by(Incident.created_at.desc()).limit(10)
        )
    ).scalars().all()

    healthy = sum(1 for s in services if s.health == "healthy")
    degraded = sum(1 for s in services if s.health == "degraded")
    critical = sum(1 for s in services if s.health == "critical")

    return {
        "environment": profile.id,
        "environmentLabel": profile.label,
        "clusterName": profile.cluster_name,
        "discoveryPending": cluster_id is None,
        "stats": {
            "services": len(services),
            "middlewares": len(middlewares),
            "clusters": len(clusters),
            "nodes": sum(c.node_count or 0 for c in clusters),
            "healthy": healthy,
            "degraded": degraded,
            "critical": critical,
            "activeIncidents": active_incidents,
        },
        "architecture": {
            "title": blueprint.get("title", ""),
            "tagline": blueprint.get("tagline", ""),
            "layers": layers_out,
            "flows": blueprint.get("flows", []),
            "infra": blueprint.get("infra", []),
            "namespaces": blueprint.get("namespaces", []),
        },
        "incidents": [{
            "id": str(i.id),
            "title": i.title,
            "severity": i.severity,
            "status": i.status,
            "affectedServices": i.affected_services or [],
            "createdAt": i.created_at,
        } for i in recent],
    }
