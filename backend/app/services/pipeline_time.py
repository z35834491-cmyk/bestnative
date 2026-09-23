# ============================================================
# pipeline_time.py — GitLab pipeline 时间窗口判断
# ============================================================

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import settings


def parse_gitlab_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def pipeline_updated_at(pl: dict) -> datetime | None:
    return parse_gitlab_ts(pl.get("updated_at") or pl.get("created_at"))


def is_pipeline_fresh(pl: dict, *, max_hours: int | None = None) -> bool:
    ts = pipeline_updated_at(pl)
    if ts is None:
        return False
    limit = max_hours if max_hours is not None else settings.GITLAB_CI_MAX_PIPELINE_AGE_HOURS
    return datetime.now(timezone.utc) - ts <= timedelta(hours=limit)


def is_deployment_fresh(dep, *, max_hours: int | None = None) -> bool:
    extra = dep.extra or {}
    ts = parse_gitlab_ts(extra.get("pipeline_updated_at"))
    if ts is None:
        return False
    limit = max_hours if max_hours is not None else settings.GITLAB_CI_MAX_PIPELINE_AGE_HOURS
    return datetime.now(timezone.utc) - ts <= timedelta(hours=limit)


def gitlab_updated_after_param(*, max_hours: int | None = None) -> str:
    limit = max_hours if max_hours is not None else settings.GITLAB_CI_MAX_PIPELINE_AGE_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=limit)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
