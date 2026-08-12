# ============================================================
# app/schemas/incident.py
# ============================================================

from typing import Any

from pydantic import BaseModel, Field


class IncidentCreate(BaseModel):
    title: str
    severity: str = "warning"
    source: str = "prometheus"
    affected_services: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)


class StatusUpdate(BaseModel):
    status: str
    actor: str = ""
