# ============================================================
# app/api/deployments.py — 发布管理 API
# GitLab CI webhook 接管 → 部署 → 验证 → 回滚决策
# ============================================================

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.change.agent import ChangeAgent
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.logging import get_logger
from app.models.deployment import Deployment
from app.schemas.deployment import DeployWebhook

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


@router.post("/webhook")
async def gitlab_webhook(body: DeployWebhook, bg: BackgroundTasks,
                         db: AsyncSession = Depends(get_db),
                         x_gitlab_token: str = Header(default="")):
    """GitLab CI build 完成后回调，BestNative 接管部署。"""
    # 安全：校验 webhook token
    if settings.GITLAB_WEBHOOK_TOKEN and x_gitlab_token != settings.GITLAB_WEBHOOK_TOKEN:
        return {"error": "invalid webhook token"}

    dep = Deployment(
        service=body.service, version=body.version,
        previous_version=body.previous_version, docker_image=body.docker_image,
        argocd_app=body.argocd_app or body.service,
        triggered_by="gitlab-ci", triggered_by_user=body.triggered_by_user,
        commit_message=body.commit_message, ci_job_url=body.ci_job_url,
        status="deploying", started_at=datetime.now(timezone.utc),
    )
    db.add(dep)
    await db.flush()
    did = str(dep.id)
    await db.commit()
    bg.add_task(_run_deploy, did)
    return {"status": "accepted", "deployment_id": did}


@router.get("")
async def list_deployments(db: AsyncSession = Depends(get_db), limit: int = Query(50, le=200)):
    rows = (await db.execute(
        select(Deployment).order_by(Deployment.created_at.desc()).limit(limit)
    )).scalars().all()
    return [_dep_dict(d) for d in rows]


@router.get("/{deployment_id}")
async def get_deployment(deployment_id: str, db: AsyncSession = Depends(get_db)):
    d = (await db.execute(select(Deployment).where(Deployment.id == deployment_id))).scalar_one_or_none()
    if d is None:
        return {"error": "not found"}
    result = _dep_dict(d)
    result.update({"stages": d.stages, "metrics": d.metrics,
                   "failureReason": d.failure_reason, "aiAnalysis": d.ai_analysis})
    return result


@router.post("/{deployment_id}/rollback")
async def rollback(deployment_id: str, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
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
    return {
        "id": str(d.id), "service": d.service, "version": d.version,
        "previousVersion": d.previous_version, "status": d.status,
        "triggeredBy": d.triggered_by, "triggeredByUser": d.triggered_by_user,
        "commitMessage": d.commit_message, "ciJobUrl": d.ci_job_url,
        "startedAt": d.started_at, "completedAt": d.completed_at,
    }
