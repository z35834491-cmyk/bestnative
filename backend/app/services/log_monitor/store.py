# ============================================================
# app/services/log_monitor/store.py — 监控引擎同步 DB 访问
# ============================================================

from __future__ import annotations

from typing import Iterable
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.monitor import MonitorTask

_sync_engine = None
_SessionLocal = None


def _ensure_engine():
    global _sync_engine, _SessionLocal
    if _sync_engine is None:
        _sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_sync_engine, expire_on_commit=False)


def get_session() -> Session:
    _ensure_engine()
    return _SessionLocal()


def get_enabled_tasks() -> list[MonitorTask]:
    with get_session() as db:
        return list(db.scalars(select(MonitorTask).where(MonitorTask.enabled.is_(True))).all())


def get_task(task_id: UUID | str) -> MonitorTask | None:
    with get_session() as db:
        return db.get(MonitorTask, task_id)


def refresh_task(task: MonitorTask, fields: Iterable[str] | None = None) -> MonitorTask:
    with get_session() as db:
        merged = db.merge(task)
        if fields:
            db.refresh(merged, attribute_names=list(fields))
        else:
            db.refresh(merged)
        db.expunge(merged)
        return merged


def save_task(task: MonitorTask, fields: Iterable[str] | None = None) -> None:
    with get_session() as db:
        merged = db.merge(task)
        db.commit()
        if fields:
            for f in fields:
                if hasattr(merged, f):
                    setattr(task, f, getattr(merged, f))
