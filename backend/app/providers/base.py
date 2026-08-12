# ============================================================
# app/providers/base.py — 基础设施 Provider 抽象基类
# 各环境实现可插拔：kubernetes / aws_ec2 / ssh_vm / aliyun
# ============================================================

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DiscoveredService:
    name: str
    namespace: str = "default"
    kind: str = "Deployment"
    replicas: int = 0
    ready_replicas: int = 0
    image: str = ""
    version: str = ""
    health: str = "unknown"
    labels: dict = field(default_factory=dict)
    ports: list = field(default_factory=list)
    endpoints: list = field(default_factory=list)  # 用于桥接发现外部依赖


@dataclass
class DiscoveredNode:
    name: str
    internal_ip: str = ""
    role: str = "worker"
    cpu_capacity: float | None = None
    mem_capacity_gb: float | None = None
    health: str = "unknown"


@dataclass
class DiscoveredMiddleware:
    name: str
    type: str
    host: str = ""
    port: int = 0
    discovered_from: str = "manual"


@dataclass
class DiscoveryResult:
    cluster_name: str
    provider: str
    nodes: list[DiscoveredNode] = field(default_factory=list)
    services: list[DiscoveredService] = field(default_factory=list)
    middlewares: list[DiscoveredMiddleware] = field(default_factory=list)
    # 桥接边：(source_service, target_host, target_port, detected_by)
    bridges: list[tuple] = field(default_factory=list)


class InfrastructureProvider(ABC):
    """基础设施 Provider 抽象基类。每个环境实现自己的发现与健康检查。"""

    provider_type: str = "base"

    def __init__(self, name: str, config: dict | None = None):
        self.name = name
        self.config = config or {}

    @abstractmethod
    async def discover(self) -> DiscoveryResult:
        """自动发现资源与拓扑。"""
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """检查 Provider 自身连通性。"""
        ...
