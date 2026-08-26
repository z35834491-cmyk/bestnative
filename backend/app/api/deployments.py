# ============================================================
# app/api/deployments.py — 发布管理 API
# CI 外挂观测：GitLab 只读扫描 或 可选 webhook
# ============================================================

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.build_failure import clean_build_log
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.deps import require_operator
from app.core.logging import get_logger
from app.models.auth import User
from app.models.deployment import Deployment
from app.schemas.deployment import DeployWebhook, DeploymentConfigUpdate
from app.services.build_ingest import ingest_build_record
from app.services.build_observer import process_build
from app.services.gitlab_ci_scanner import run_gitlab_ci_scan
from app.services.maintenance import add_window
from app.services.platform_config import get_auto_rollback, set_auto_rollback

router = APIRouter(prefix="/deployments", tags=["deployments"])
logger = get_logger("api.deployments")


async def _run_deploy(deployment_id: str):
    async with AsyncSessionLocal() as db:
        try:
            await ChangeAgent(db).execute(deployment_id)
            await db.commit()
        except Exception as e:  # noqa: BLE001
            logger.error("deploy.background.failed", id=deployment_id, error=str(e))
            await db.rollback()


async def _run_observe(deployment_id: str):
    async with AsyncSessionLocal() as db:
        try:
            await process_build(db, deployment_id)
        except Exception as e:  # noqa: BLE001
            logger.error("build.observe.failed", id=deployment_id, error=str(e))
            await db.rollback()


@router.post("/scan-gitlab")
async def scan_gitlab_ci(bg: BackgroundTasks, _user: User = Depends(require_operator)):
    """手动触发 GitLab CI 只读扫描（无需改各项目 CI 配置）。"""
    if not settings.GITLAB_URL or not settings.GITLAB_TOKEN:
        raise HTTPException(status_code=400, detail="请配置 GITLAB_URL 和 GITLAB_TOKEN")

    async def _scan():
        await run_gitlab_ci_scan()

    bg.add_task(_scan)
    return {"status": "scan_started", "interval_sec": settings.GITLAB_CI_SCAN_INTERVAL}


@router.get("/scan-gitlab/status")
async def gitlab_scan_config():
    return {
        "enabled": settings.GITLAB_CI_SCAN_ENABLED,
        "configured": bool(settings.GITLAB_URL and settings.GITLAB_TOKEN),
        "url": settings.GITLAB_URL,
        "groupId": settings.GITLAB_GROUP_ID,
        "projects": settings.gitlab_project_list(),
        "branches": settings.gitlab_ci_branches(),
        "intervalSec": settings.GITLAB_CI_SCAN_INTERVAL,
        "pipelinesPerRef": settings.GITLAB_CI_PIPELINES_PER_REF,
    }


@router.post("/webhook")
async def gitlab_webhook(body: DeployWebhook, bg: BackgroundTasks,
                         db: AsyncSession = Depends(get_db),
                         x_gitlab_token: str = Header(default="")):
    """可选：GitLab CI 主动回调（非必需，推荐用 scan-gitlab 只读扫描）。"""
    if settings.is_production and not settings.GITLAB_WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="生产环境必须配置 GITLAB_WEBHOOK_TOKEN")
    if settings.GITLAB_WEBHOOK_TOKEN and x_gitlab_token != settings.GITLAB_WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="invalid webhook token")

    takeover = body.takeover_deploy and not settings.BUILD_OBSERVE_MODE
    did, is_new = await ingest_build_record(
        db,
        service=body.service,
        project=body.project or body.service,
        status=body.status,
        version=body.version or "unknown",
        previous_version=body.previous_version,
        duration_sec=body.duration_sec,
        stages=body.stages,
        failure_log=body.failure_log,
        docker_image=body.docker_image,
        argocd_app=body.argocd_app or body.service,
        triggered_by="gitlab-ci",
        triggered_by_user=body.triggered_by_user,
        commit_message=body.commit_message,
        ci_job_url=body.ci_job_url,
        pipeline_id=body.pipeline_id,
        gitlab_project_id=body.extra.get("gitlab_project_id", "") if body.extra else "",
        branch=body.extra.get("branch", "") if body.extra else "",
        extra={**(body.extra or {}), "mode": "takeover" if takeover else "observe"},
    )
    if not is_new:
        return {"status": "duplicate", "deployment_id": did}

    if takeover:
        add_window(body.service, 30, reason=f"部署 {body.version}")
        bg.add_task(_run_deploy, did)
        return {"status": "accepted", "mode": "takeover", "deployment_id": did}

    bg.add_task(_run_observe, did)
    return {"status": "accepted", "mode": "observe", "deployment_id": did}


@router.get("/config")
async def get_deployment_config():
    """发布管理运行时配置（自动回滚开关等）。"""
    return {
        "autoRollback": get_auto_rollback(),
        "defaultAutoRollback": settings.AUTO_ROLLBACK,
    }


@router.patch("/config")
async def update_deployment_config(
    body: DeploymentConfigUpdate,
    _user: User = Depends(require_operator),
):
    if body.auto_rollback is None:
        raise HTTPException(status_code=400, detail="auto_rollback required")
    enabled = set_auto_rollback(body.auto_rollback)
    return {"autoRollback": enabled}


@router.get("")
async def list_deployments(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
):
    """每服务最新一条构建，不含历史。"""
    rows = (await db.execute(
        select(Deployment)
        .where(Deployment.is_latest.is_(True))
        .order_by(Deployment.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [_dep_dict(d) for d in rows]


@router.get("/{deployment_id}")
async def get_deployment(deployment_id: str, db: AsyncSession = Depends(get_db)):
    d = (await db.execute(select(Deployment).where(Deployment.id == deployment_id))).scalar_one_or_none()
    if d is None:
        return {"error": "not found"}
    result = _dep_dict(d)
    result.update({
        "stages": d.stages,
        "failureReason": clean_build_log(d.failure_reason or ""),
        "extra": {
            k: v for k, v in (d.extra or {}).items()
            if k in ("branch", "failure_kind", "pipeline_updated_at", "scan_source")
        },
    })
    return result


@router.post("/{deployment_id}/rollback")
async def rollback(deployment_id: str, bg: BackgroundTasks, db: AsyncSession = Depends(get_db),
                   _user: User = Depends(require_operator)):
    d = (await db.execute(select(Deployment).where(Deployment.id == deployment_id))).scalar_one_or_none()
    if d is None:
        return {"error": "not found"}
    bg.add_task(_run_rollback, deployment_id)
    return {"status": "rollback_started", "deployment_id": deployment_id}


async def _run_rollback(deployment_id: str):
    async with AsyncSessionLocal() as db:
        try:
            await ChangeAgent(db).rollback(deployment_id)
            await db.commit()
        except Exception as e:  # noqa: BLE001
            logger.error("rollback.failed", id=deployment_id, error=str(e))
            await db.rollback()


def _dep_dict(d: Deployment) -> dict:
    extra = d.extra or {}
    return {
        "id": str(d.id),
        "service": d.service,
        "project": d.project or d.service,
        "version": d.version,
        "previousVersion": d.previous_version,
        "status": d.status,
        "buildStatus": d.build_status or d.status,
        "buildDurationSec": d.build_duration_sec,
        "isLatest": d.is_latest,
        "triggeredBy": d.triggered_by,
        "triggeredByUser": d.triggered_by_user,
        "commitMessage": d.commit_message,
        "ciJobUrl": d.ci_job_url,
        "startedAt": d.started_at,
        "completedAt": d.completed_at,
        "branch": extra.get("branch", ""),
        "scanSource": extra.get("scan_source", d.triggered_by),
        "failureKind": extra.get("failure_kind", "build"),
        "pipelineUpdatedAt": extra.get("pipeline_updated_at", ""),
    }
