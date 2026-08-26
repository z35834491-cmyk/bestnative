# ============================================================
# app/api/settings_api.py — 集成健康检查 + 维护窗口
# ============================================================

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.deps import require_admin, require_user
from app.models.auth import User
from app.services.integration_checks import get_integration_checks
from app.services.maintenance import add_window, list_windows
from app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/settings", tags=["settings"])


class MaintenanceRequest(BaseModel):
    service: str
    minutes: int = 60
    reason: str = ""


@router.get("/integrations")
async def integration_health(
    db: AsyncSession = Depends(get_db),
    refresh: bool = Query(False),
    _user: User = Depends(require_user),
):
    return await get_integration_checks(db, refresh=refresh)


@router.get("/maintenance")
async def get_maintenance(_user: User = Depends(require_user)):
    return {"windows": list_windows()}


@router.post("/maintenance")
async def set_maintenance(body: MaintenanceRequest, _user: User = Depends(require_admin)):
    entry = add_window(body.service, body.minutes, body.reason)
    return {"status": "ok", "window": entry}
