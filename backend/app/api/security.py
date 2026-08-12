# ============================================================
# app/api/security.py — 安全扫描 API
# ============================================================

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.security.agent import SecurityAgent
from app.core.database import AsyncSessionLocal, get_db
from app.core.logging import get_logger
from app.models.security import Asset, ScanSession, Vulnerability
from app.schemas.security import ScanRequest

router = APIRouter(prefix="/security", tags=["security"])
logger = get_logger("api.security")


async def _run_scan(session_id: str):
    """后台执行扫描（独立 DB 会话）。"""
    async with AsyncSessionLocal() as db:
        try:
            await SecurityAgent(db).scan(session_id)
            await db.commit()
        except Exception as e:  # noqa: BLE001
            logger.error("scan.background.failed", session=session_id, error=str(e))
            await db.rollback()


@router.post("/scans")
async def create_scan(req: ScanRequest, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """新建扫描任务（手动域名 或 全平台）。异步执行。"""
    session = ScanSession(
        target=req.target or "full-platform",
        scope=req.scope,
        status="init",
        triggered_by=req.triggered_by or "manual",
    )
    db.add(session)
    await db.flush()
    sid = str(session.id)
    await db.commit()
    bg.add_task(_run_scan, sid)
    return {"status": "started", "session_id": sid, "scope": req.scope}


@router.get("/scans")
async def list_scans(db: AsyncSession = Depends(get_db), limit: int = Query(50, le=200)):
    rows = (await db.execute(
        select(ScanSession).order_by(ScanSession.created_at.desc()).limit(limit)
    )).scalars().all()
    return [{
        "id": str(s.id), "target": s.target, "scope": s.scope, "status": s.status,
        "assetCount": s.asset_count, "vulnCount": s.vuln_count,
        "startedAt": s.started_at, "completedAt": s.completed_at,
    } for s in rows]


@router.get("/scans/{session_id}")
async def get_scan(session_id: str, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(ScanSession).where(ScanSession.id == session_id))).scalar_one_or_none()
    if s is None:
        return {"error": "not found"}
    vulns = (await db.execute(
        select(Vulnerability).where(Vulnerability.session_id == session_id)
    )).scalars().all()
    return {
        "id": str(s.id), "target": s.target, "scope": s.scope, "status": s.status,
        "report": s.report, "assetCount": s.asset_count, "vulnCount": s.vuln_count,
        "vulnerabilities": [_vuln_dict(v) for v in vulns],
    }


@router.get("/vulnerabilities")
async def list_vulns(db: AsyncSession = Depends(get_db),
                     severity: str | None = None, status: str | None = None,
                     limit: int = Query(100, le=500)):
    q = select(Vulnerability)
    if severity:
        q = q.where(Vulnerability.severity == severity)
    if status:
        q = q.where(Vulnerability.status == status)
    q = q.order_by(Vulnerability.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [_vuln_dict(v) for v in rows]


@router.get("/stats")
async def security_stats(db: AsyncSession = Depends(get_db)):
    """安全概览统计。"""
    by_sev = (await db.execute(
        select(Vulnerability.severity, func.count()).group_by(Vulnerability.severity)
    )).all()
    by_status = (await db.execute(
        select(Vulnerability.status, func.count()).group_by(Vulnerability.status)
    )).all()
    total_scans = (await db.execute(select(func.count()).select_from(ScanSession))).scalar()
    return {
        "bySeverity": {k: v for k, v in by_sev},
        "byStatus": {k: v for k, v in by_status},
        "totalScans": total_scans,
    }


def _vuln_dict(v: Vulnerability) -> dict:
    return {
        "id": str(v.id), "title": v.title, "severity": v.severity, "type": v.type,
        "target": v.target, "endpoint": v.endpoint, "foundBy": v.found_by,
        "cve": v.cve, "cvssScore": v.cvss_score, "description": v.description,
        "recommendation": v.recommendation, "status": v.status, "createdAt": v.created_at,
    }
