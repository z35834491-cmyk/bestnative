# ============================================================
# app/models/infra.py — 环境资源与拓扑（自动发现写入）
# clusters / nodes / services / middlewares / dependencies / bridges
# ============================================================

from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Cluster(TimestampMixin, Base):
    """K8s 集群 / VM 节点组"""
    __tablename__ = "clusters"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(30))  # kubernetes / aws_ec2 / ssh_vm / aliyun
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    health: Mapped[str] = mapped_column(String(20), default="unknown")
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class Node(TimestampMixin, Base):
    """集群节点"""
    __tablename__ = "nodes"

    cluster_id: Mapped[str] = mapped_column(ForeignKey("clusters.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    internal_ip: Mapped[str] = mapped_column(String(45), default="")
    role: Mapped[str] = mapped_column(String(30), default="worker")  # control-plane / worker
    cpu_capacity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mem_capacity_gb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    health: Mapped[str] = mapped_column(String(20), default="unknown")
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class Service(TimestampMixin, Base):
    """业务服务（K8s Deployment/Service 自动发现）"""
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("cluster_id", "namespace", "name", name="uq_service"),)

    cluster_id: Mapped[str] = mapped_column(ForeignKey("clusters.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(100), default="default")
    kind: Mapped[str] = mapped_column(String(30), default="Deployment")
    replicas: Mapped[int] = mapped_column(Integer, default=0)
    ready_replicas: Mapped[int] = mapped_column(Integer, default=0)
    image: Mapped[str] = mapped_column(String(300), default="")
    version: Mapped[str] = mapped_column(String(100), default="")
    health: Mapped[str] = mapped_column(String(20), default="unknown")  # healthy/degraded/critical/unknown
    cpu_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mem_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)  # labels/ports/endpoints


class Middleware(TimestampMixin, Base):
    """中间件（VM 上的 MySQL/Redis/RabbitMQ 等，桥接发现）"""
    __tablename__ = "middlewares"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    type: Mapped[str] = mapped_column(String(30))  # mysql/redis/rabbitmq/mongodb/postgresql
    host: Mapped[str] = mapped_column(String(120), default="")
    port: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[str] = mapped_column(String(50), default="")
    health: Mapped[str] = mapped_column(String(20), default="unknown")
    discovered_from: Mapped[str] = mapped_column(String(30), default="manual")  # endpoints/configmap/env/manual
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class ServiceDependency(TimestampMixin, Base):
    """服务依赖关系（拓扑边）"""
    __tablename__ = "service_dependencies"
    __table_args__ = (UniqueConstraint("source_id", "target_id", name="uq_dependency"),)

    source_id: Mapped[str] = mapped_column(String(64), index=True)  # service/middleware id
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(20), default="service")
    target_type: Mapped[str] = mapped_column(String(20), default="service")
    protocol: Mapped[str] = mapped_column(String(20), default="")
    detected_by: Mapped[str] = mapped_column(String(30), default="static")  # endpoints/env/trace/static
