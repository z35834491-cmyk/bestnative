# ============================================================
# app/models/agent_run.py — Agent 执行记录（巡检/成本/架构等）
# ============================================================

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    agent_type: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    title: Mapped[str] = mapped_column(String(300), default="")
    triggered_by: Mapped[str] = mapped_column(String(40), default="manual")
    input: Mapped[dict] = mapped_column(JSONB, default=dict)
    output: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
