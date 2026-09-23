# ============================================================
# app/core/deps.py — FastAPI 依赖（鉴权）
# ============================================================

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.auth import User
from app.services.environments import EnvironmentProfile, get_active_profile

_bearer = HTTPBearer(auto_error=False)


async def get_request_environment(
    x_shore_environment: str | None = Header(None, alias="X-Shore-Environment"),
) -> EnvironmentProfile:
    return get_active_profile(x_shore_environment)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not creds:
        return None
    payload = decode_token(creds.credentials)
    if not payload or not payload.get("sub"):
        return None
    user = (await db.execute(select(User).where(User.username == payload["sub"]))).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def require_user(user: User | None = Depends(get_current_user)) -> User:
    if not settings.AUTH_REQUIRED:
        if user:
            return user
        # 开发模式：返回虚拟 admin 权限
        dummy = User(username="dev", password_hash="", display_name="Dev", role="admin")
        return dummy
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或 token 无效")
    return user


async def require_operator(user: User = Depends(require_user)) -> User:
    if user.role not in {"admin", "operator"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要 operator 权限")
    return user


async def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要 admin 权限")
    return user
