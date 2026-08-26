# ============================================================
# app/models/deployment.py — 发布管理
# ============================================================

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Deployment(TimestampMixin, Base):
    __tablename__ = "deployments"

    service: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(200), default="", index=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_version: Mapped[str] = mapped_column(String(100), default="")
    docker_image: Mapped[str] = mapped_column(String(300), default="")
    argocd_app: Mapped[str] = mapped_column(String(150), default="")
    # success / failed / canceled / deploying / verifying / rolled_back
    status: Mapped[str] = mapped_column(String(30), default="success", index=True)
    build_status: Mapped[str] = mapped_column(String(20), default="")  # success | failed | canceled
    build_duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    is_latest: Mapped[bool] = mapped_column(default=True, index=True)
    triggered_by: Mapped[str] = mapped_column(String(50), default="gitlab-ci")
    triggered_by_user: Mapped[str] = mapped_column(String(50), default="")
    commit_message: Mapped[str] = mapped_column(Text, default="")
    ci_job_url: Mapped[str] = mapped_column(String(400), default="")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 流水线阶段 + 指标对比 + 失败根因分析
    stages: Mapped[list] = mapped_column(JSONB, default=list)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    ai_analysis: Mapped[str] = mapped_column(Text, default="")
    optimization_tips: Mapped[str] = mapped_column(Text, default="")
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
