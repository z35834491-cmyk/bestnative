# ============================================================
# app/api/auth.py — 登录 / 当前用户
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models.auth import User
from app.core.deps import require_user

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    token = create_access_token(user.username, extra={"role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"username": user.username, "displayName": user.display_name, "role": user.role},
    }


@router.get("/me")
async def me(user: User = Depends(require_user)):
    return {"username": user.username, "displayName": user.display_name, "role": user.role}
