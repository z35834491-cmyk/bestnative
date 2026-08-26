# ============================================================
# scan_targets.py — 渗透/漏洞扫描目标采集
# ============================================================

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.infra import Middleware, Node

logger = get_logger("scan_targets")

_WEB_PORTS = {80, 443, 8080, 8443, 8000, 8888, 9000}


def _normalize_host_port(host: str, port: int | None) -> list[str]:
    host = (host or "").strip()
    if not host:
        return []
    out: list[str] = []
    if port and port > 0:
        out.append(f"{host}:{port}")
        if port in _WEB_PORTS:
            out.append(host)
    else:
        out.append(host)
    return out


def _k8s_exposure_targets_sync() -> list[str]:
    """从 K8s 实时拉 Ingress / LoadBalancer / NodePort 暴露面。"""
    if not (settings.KUBECONFIG or settings.K8S_IN_CLUSTER):
        return []
    try:
        from kubernetes import client, config as k8s_config

        if settings.K8S_IN_CLUSTER:
            k8s_config.load_incluster_config()
        else:
            k8s_config.load_kube_config(
                config_file=settings.KUBECONFIG or None,
                context=settings.K8S_CONTEXT or None,
            )
        core = client.CoreV1Api()
        net = client.NetworkingV1Api()
        targets: set[str] = set()

        for ing in net.list_ingress_for_all_namespaces().items:
            for rule in ing.spec.rules or []:
                if rule.host:
                    targets.add(rule.host.strip())
            for tls in ing.spec.tls or []:
                for host in tls.hosts or []:
                    if host:
                        targets.add(host.strip())

        node_ips: set[str] = set()
        for node in core.list_node().items:
            for addr in node.status.addresses or []:
                if addr.type in ("ExternalIP", "InternalIP") and addr.address:
                    node_ips.add(addr.address)

        for svc in core.list_service_for_all_namespaces().items:
            spec, status = svc.spec, svc.status
            if not spec:
                continue
            lb = status.load_balancer.ingress if status and status.load_balancer else None
            if lb:
                for ing in lb:
                    if ing.hostname:
                        targets.add(ing.hostname.strip())
                    if ing.ip:
                        targets.add(ing.ip.strip())
            if spec.type == "NodePort":
                for port in spec.ports or []:
                    if port.node_port:
                        for nip in node_ips:
                            targets.add(f"{nip}:{port.node_port}")
            if spec.cluster_ip and spec.cluster_ip not in ("None", ""):
                for port in spec.ports or []:
                    if port.port:
                        targets.update(_normalize_host_port(spec.cluster_ip, port.port))

        return sorted(targets)
    except Exception as exc:  # noqa: BLE001
        logger.warning("scan_targets.k8s.failed", error=str(exc)[:120])
        return []


async def collect_platform_targets(db: AsyncSession) -> tuple[list[str], dict]:
    """全平台渗透扫描目标：DB 发现 + K8s 暴露面 + 手动补充。"""
    targets: set[str] = set()
    sources: dict[str, list[str]] = {
        "middleware": [],
        "nodes": [],
        "k8s": [],
        "extra": [],
    }

    for m in (await db.execute(select(Middleware))).scalars().all():
        if not m.host:
            continue
        for t in _normalize_host_port(m.host, m.port or None):
            targets.add(t)
            sources["middleware"].append(t)

    for n in (await db.execute(select(Node))).scalars().all():
        if n.internal_ip:
            targets.add(n.internal_ip)
            sources["nodes"].append(n.internal_ip)

    for t in settings.security_scan_extra_targets():
        targets.add(t)
        sources["extra"].append(t)

    k8s_targets = _k8s_exposure_targets_sync()
    for t in k8s_targets:
        targets.add(t)
        sources["k8s"].append(t)

    meta = {
        "total": len(targets),
        "sources": {k: len(v) for k, v in sources.items()},
        "sample": sorted(targets)[:20],
    }
    return sorted(targets), meta
