# ============================================================
# app/models/incident.py — 告警事件全生命周期 + 告警策略
# ============================================================

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"

    # 指纹去重：相同告警在活跃窗口内不重复建单
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="warning")  # critical/warning/info
    # firing → acknowledged → analyzing → analyzed → resolved
    status: Mapped[str] = mapped_column(String(20), default="firing", index=True)
    source: Mapped[str] = mapped_column(String(40), default="prometheus")  # prometheus/log_pattern/blackbox
    affected_services: Mapped[list] = mapped_column(JSONB, default=list)
    assignee: Mapped[str] = mapped_column(String(50), default="")
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class IncidentEvent(TimestampMixin, Base):
    """事件时间线（状态变更 / Agent 动作 / 人工操作）"""
    __tablename__ = "incident_events"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))  # status_change/agent_action/comment
    actor: Mapped[str] = mapped_column(String(50), default="system")
    content: Mapped[str] = mapped_column(Text, default="")
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class AnalysisReport(TimestampMixin, Base):
    """诊断 Agent 输出的根因分析报告"""
    __tablename__ = "analysis_reports"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(20), default="medium")  # high/medium/low
    can_auto_fix: Mapped[bool] = mapped_column(default=False)
    llm_tokens: Mapped[int] = mapped_column(Integer, default=0)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class AlertRule(TimestampMixin, Base):
    """告警策略（含 AI 自动生成的规则）"""
    __tablename__ = "alert_rules"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    expr: Mapped[str] = mapped_column(Text, nullable=False)  # PromQL
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    duration: Mapped[str] = mapped_column(String(20), default="5m")
    # active / proposed(AI提议待确认) / rejected
    status: Mapped[str] = mapped_column(String(20), default="proposed", index=True)
    auto_generated: Mapped[bool] = mapped_column(default=False)
    generated_from_incident_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
