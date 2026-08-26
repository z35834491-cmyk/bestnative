# ============================================================
# app/schemas/topology.py
# ============================================================

from typing import Any

from pydantic import BaseModel, Field


class DiscoverRequest(BaseModel):
    provider_type: str = "kubernetes"
    cluster_name: str
    config: dict[str, Any] | None = None


class TopologyGraph(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    environment: str | None = None
    clusterName: str | None = None
    discoveryPending: bool = False
