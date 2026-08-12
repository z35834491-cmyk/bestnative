# ============================================================
# app/models/schedule.py — 排班 + 电话告警（保留自旧平台，重构）
# ============================================================

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Schedule(TimestampMixin, Base):
    __tablename__ = "schedules"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    shift_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    shift_type: Mapped[str] = mapped_column(String(20), default="day")  # day / night / full
    note: Mapped[str] = mapped_column(Text, default="")


class PhoneAlert(TimestampMixin, Base):
    """电话告警记录"""
    __tablename__ = "phone_alerts"

    incident_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/called/answered/failed
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
