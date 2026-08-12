# ============================================================
# app/api/health.py — 健康检查 + 就绪探针
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """存活探针：进程可用即返回。"""
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    """就绪探针：校验数据库连通性。"""
    checks: dict[str, str] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
