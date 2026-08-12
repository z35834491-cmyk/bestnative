# ============================================================
# app/providers/__init__.py — Provider 工厂（可插拔）
# ============================================================

from app.providers.base import InfrastructureProvider
from app.providers.kubernetes import KubernetesProvider
from app.providers.ssh_vm import SSHVMProvider
from app.providers.aws import AWSProvider

_REGISTRY: dict[str, type[InfrastructureProvider]] = {
    "kubernetes": KubernetesProvider,
    "ssh_vm": SSHVMProvider,
    "aws_ec2": AWSProvider,
}


def create_provider(provider_type: str, name: str, config: dict | None = None) -> InfrastructureProvider:
    cls = _REGISTRY.get(provider_type)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_type}. Available: {list(_REGISTRY)}")
    return cls(name=name, config=config)


def register_provider(provider_type: str, cls: type[InfrastructureProvider]) -> None:
    """外部可注册新 Provider（如 aliyun），保持可插拔。"""
    _REGISTRY[provider_type] = cls


__all__ = ["create_provider", "register_provider", "InfrastructureProvider"]
