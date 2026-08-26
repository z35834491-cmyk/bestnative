# ============================================================
# kubeconfig_store.py — K8s 凭证：从 KUBECONFIG 读取 → 入库 → 运行时从 DB 取
# 部署只需标准 KUBECONFIG 环境变量，environments.json 不写文件路径
# ============================================================

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.models.infra import Cluster
from app.services.environments import EnvironmentProfile, list_profiles

logger = get_logger("kubeconfig_store")


def _read_source_kubeconfig_dict() -> dict | None:
    """从 KUBECONFIG 环境变量指向的文件读取（标准 K8s 部署方式）。"""
    path = (settings.KUBECONFIG or "").strip()
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("kubeconfig.read.failed", path=path, error=str(exc)[:120])
        return None


def _extract_context_config(source: dict, context_name: str) -> dict | None:
    """从多 context kubeconfig 提取单集群配置（仅初始化/同步时用）。"""
    contexts = source.get("contexts") or []
    ctx_entry = next((c for c in contexts if c.get("name") == context_name), None)
    if not ctx_entry:
        return None
    ctx = ctx_entry.get("context") or {}
    cluster_name = ctx.get("cluster")
    user_name = ctx.get("user")
    if not cluster_name or not user_name:
        return None
    clusters = [c for c in (source.get("clusters") or []) if c.get("name") == cluster_name]
    users = [u for u in (source.get("users") or []) if u.get("name") == user_name]
    if not clusters or not users:
        return None
    return {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": clusters,
        "users": users,
        "contexts": [ctx_entry],
        "current-context": context_name,
    }


def materialize_kubeconfig_yaml(profile: EnvironmentProfile) -> str | None:
    """为环境生成应入库的 kubeconfig 文本（从 KUBECONFIG 源文件解析）。"""
    source = _read_source_kubeconfig_dict()
    if not source:
        return None
    contexts = source.get("contexts") or []
    for name in (profile.id, profile.cluster_name):
        extracted = _extract_context_config(source, name)
        if extracted:
            return yaml.safe_dump(extracted, default_flow_style=False)
    if len(contexts) == 1:
        only = contexts[0].get("name")
        if only:
            extracted = _extract_context_config(source, only)
            if extracted:
                return yaml.safe_dump(extracted, default_flow_style=False)
    return yaml.safe_dump(source, default_flow_style=False)


def k8s_config_from_content(content: str | None) -> dict[str, Any]:
    if settings.K8S_IN_CLUSTER:
        return {"in_cluster": True}
    if content:
        return {"kubeconfig_content": content}
    return {}


@lru_cache(maxsize=1)
def _sync_session_factory() -> sessionmaker | None:
    url = (settings.DATABASE_URL_SYNC or "").strip()
    if not url:
        return None
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_cluster_kubeconfig_sync(cluster_name: str) -> str | None:
    factory = _sync_session_factory()
    if factory is None:
        return None
    with factory() as db:
        row = db.execute(select(Cluster).where(Cluster.name == cluster_name)).scalar_one_or_none()
        return row.kubeconfig if row and row.kubeconfig else None


def resolve_k8s_config_sync(profile: EnvironmentProfile) -> dict[str, Any]:
    if settings.K8S_IN_CLUSTER:
        return {"in_cluster": True}
    content = get_cluster_kubeconfig_sync(profile.cluster_name)
    if content:
        return {"kubeconfig_content": content}
    yaml_text = materialize_kubeconfig_yaml(profile)
    return k8s_config_from_content(yaml_text)


async def _get_or_create_cluster(db: AsyncSession, cluster_name: str) -> Cluster:
    row = (await db.execute(select(Cluster).where(Cluster.name == cluster_name))).scalar_one_or_none()
    if row is None:
        row = Cluster(name=cluster_name, provider="kubernetes")
        db.add(row)
        await db.flush()
    return row


async def ensure_cluster_kubeconfig(db: AsyncSession, profile: EnvironmentProfile) -> str | None:
    """确保集群记录存在且 kubeconfig 已入库；缺失时从 KUBECONFIG 源同步。"""
    if settings.K8S_IN_CLUSTER:
        return None
    cluster = await _get_or_create_cluster(db, profile.cluster_name)
    if cluster.kubeconfig:
        return cluster.kubeconfig
    yaml_text = materialize_kubeconfig_yaml(profile)
    if not yaml_text:
        return None
    cluster.kubeconfig = yaml_text
    await db.flush()
    logger.info("kubeconfig.stored", env=profile.id, cluster=profile.cluster_name)
    return yaml_text


async def resolve_k8s_config(db: AsyncSession, profile: EnvironmentProfile) -> dict[str, Any]:
    """运行时 K8s 连接配置：优先读 DB 已入库 kubeconfig。"""
    if settings.K8S_IN_CLUSTER:
        return {"in_cluster": True}
    content = await ensure_cluster_kubeconfig(db, profile)
    return k8s_config_from_content(content)


async def sync_all_cluster_kubeconfigs(db: AsyncSession) -> int:
    """启动时：从 KUBECONFIG 源为各环境同步 kubeconfig 到 clusters 表。"""
    if settings.K8S_IN_CLUSTER:
        return 0
    updated = 0
    for profile in list_profiles():
        yaml_text = materialize_kubeconfig_yaml(profile)
        if not yaml_text:
            continue
        cluster = await _get_or_create_cluster(db, profile.cluster_name)
        if cluster.kubeconfig != yaml_text:
            cluster.kubeconfig = yaml_text
            updated += 1
    if updated:
        await db.flush()
        logger.info("kubeconfig.sync.done", updated=updated)
    return updated


async def save_cluster_kubeconfig(db: AsyncSession, profile: EnvironmentProfile, content: str) -> None:
    """平台直接粘贴 kubeconfig 入库。"""
    text = (content or "").strip()
    if not text:
        raise ValueError("kubeconfig 不能为空")
    try:
        data = yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"kubeconfig 格式无效: {exc}") from exc
    if not isinstance(data, dict) or not data.get("clusters"):
        raise ValueError("kubeconfig 缺少 clusters 配置")
    cluster = await _get_or_create_cluster(db, profile.cluster_name)
    cluster.kubeconfig = text if text.endswith("\n") else f"{text}\n"
    await db.flush()
    logger.info("kubeconfig.saved", env=profile.id, cluster=profile.cluster_name)


async def cluster_has_kubeconfig(db: AsyncSession, profile: EnvironmentProfile) -> bool:
    if settings.K8S_IN_CLUSTER:
        return True
    row = (await db.execute(select(Cluster).where(Cluster.name == profile.cluster_name))).scalar_one_or_none()
    return bool(row and row.kubeconfig)
