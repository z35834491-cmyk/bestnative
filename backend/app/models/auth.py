# ============================================================
# app/models/auth.py — 用户 / 角色
# ============================================================

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # admin / operator / viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
