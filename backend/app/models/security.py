# ============================================================
# app/models/security.py — 安全扫描（合并自 PentestAgent）
# scan_sessions / assets / vulnerabilities
# ============================================================

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class ScanSession(TimestampMixin, Base):
    __tablename__ = "scan_sessions"

    target: Mapped[str] = mapped_column(String(300), nullable=False)
    scope: Mapped[str] = mapped_column(String(50), default="manual")  # manual / full_platform
    # init/recon/discovery/vuln_scan/analyzing/reporting/completed/failed
    status: Mapped[str] = mapped_column(String(30), default="init", index=True)
    triggered_by: Mapped[str] = mapped_column(String(50), default="")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    asset_count: Mapped[int] = mapped_column(Integer, default=0)
    vuln_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_results: Mapped[dict] = mapped_column(JSONB, default=dict)
    report: Mapped[str] = mapped_column(Text, default="")


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    session_id: Mapped[str] = mapped_column(ForeignKey("scan_sessions.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(30))  # ip/domain/subdomain/url/port/service
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    service: Mapped[str] = mapped_column(String(100), default="")
    version: Mapped[str] = mapped_column(String(100), default="")
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class Vulnerability(TimestampMixin, Base):
    __tablename__ = "vulnerabilities"

    session_id: Mapped[str] = mapped_column(ForeignKey("scan_sessions.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="info", index=True)  # critical/high/medium/low/info
    type: Mapped[str] = mapped_column(String(60), default="")
    target: Mapped[str] = mapped_column(String(300), default="")
    endpoint: Mapped[str] = mapped_column(String(500), default="")
    found_by: Mapped[str] = mapped_column(String(30), default="")  # nmap/nuclei/httpx/AI
    cve: Mapped[str] = mapped_column(String(40), default="")
    cvss_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    # new / confirmed / fixed / false_positive
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
