# ============================================================
# app/services/build_ingest.py — 构建记录入库（webhook / GitLab 扫描共用）
# ============================================================

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment import Deployment
from app.services.build_failure import clean_build_log
from app.services.build_observer import _norm_status, _stage_dicts, mark_latest


async def clear_service_deployments(db: AsyncSession, service: str) -> int:
    rows = (await db.execute(select(Deployment).where(Deployment.service == service))).scalars().all()
    for row in rows:
        await db.delete(row)
    if rows:
        await db.commit()
    return len(rows)


async def get_latest_deployment(db: AsyncSession, service: str) -> Deployment | None:
    return (await db.execute(
        select(Deployment)
        .where(Deployment.service == service, Deployment.is_latest.is_(True))
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def pipeline_already_ingested(db: AsyncSession, project_id: int, pipeline_id: int) -> bool:
    pid, plid = str(project_id), str(pipeline_id)
    row = (await db.execute(
        select(Deployment.id).where(
            Deployment.extra["pipeline_id"].astext == plid,
            Deployment.extra["gitlab_project_id"].astext == pid,
        ).limit(1)
    )).scalar_one_or_none()
    return row is not None


async def ingest_build_record(
    db: AsyncSession,
    *,
    service: str,
    project: str,
    status: str,
    version: str = "",
    previous_version: str = "",
    duration_sec: int = 0,
    stages: list[Any] | None = None,
    failure_log: str = "",
    docker_image: str = "",
    argocd_app: str = "",
    triggered_by: str = "gitlab-ci",
    triggered_by_user: str = "",
    commit_message: str = "",
    ci_job_url: str = "",
    pipeline_id: str = "",
    gitlab_project_id: str = "",
    branch: str = "",
    extra: dict[str, Any] | None = None,
    pipeline_updated_at: str = "",
) -> tuple[str, bool]:
    """写入构建记录并标记为服务最新。返回 (deployment_id, is_new)。"""
    if pipeline_id and gitlab_project_id:
        if await pipeline_already_ingested(db, int(gitlab_project_id), int(pipeline_id)):
            return "", False

    build_status = _norm_status(status)
    stage_rows = _stage_dicts(stages or [])

    clean_log = clean_build_log(failure_log or "")[:8000]
    dep = Deployment(
        service=service,
        project=project or service,
        version=version or "unknown",
        previous_version=previous_version,
        docker_image=docker_image,
        argocd_app=argocd_app or service,
        status=build_status,
        build_status=build_status,
        build_duration_sec=max(0, duration_sec),
        is_latest=True,
        triggered_by=triggered_by,
        triggered_by_user=triggered_by_user,
        commit_message=commit_message,
        ci_job_url=ci_job_url,
        started_at=datetime.now(timezone.utc),
        stages=stage_rows,
        failure_reason=clean_log,
        extra={
            "pipeline_id": pipeline_id,
            "gitlab_project_id": gitlab_project_id,
            "branch": branch,
            "pipeline_updated_at": pipeline_updated_at,
            "failure_log": clean_log,
            "mode": "observe",
            **(extra or {}),
        },
    )
    db.add(dep)
    await db.flush()
    did = str(dep.id)
    await mark_latest(db, service, did)
    await db.commit()
    return did, True
