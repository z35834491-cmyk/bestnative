# ============================================================
# app/api/home.py — 首页轻量总览（无 ES / 无拓扑重计算）
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_request_environment, require_user
from app.models.auth import User
from app.services.architecture_overview import build_home_overview
from app.services.environments import EnvironmentProfile

router = APIRouter(prefix="/home", tags=["home"])


@router.get("/overview")
async def home_overview(
    db: AsyncSession = Depends(get_db),
    env: EnvironmentProfile = Depends(get_request_environment),
    _user: User = Depends(require_user),
):
    return await build_home_overview(db, env)
