# ============================================================
# app/bootstrap.py — 初始化数据库（建 pgvector 扩展 + 建表）
# 供 docker compose 启动时执行：python -m app.bootstrap
# ============================================================

import asyncio

from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal, Base, engine
from app.core.logging import get_logger, setup_logging
from app.core.security import hash_password
import app.models  # noqa: F401  注册所有表
from app.models.auth import User

logger = get_logger("bootstrap")


async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("bootstrap.tables.created")


async def seed():
    """仅创建初始管理员用户（幂等）。不含任何示例数据。"""
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if existing:
            logger.info("bootstrap.seed.skip", reason="already seeded")
            return
        db.add(User(username="admin", password_hash=hash_password("admin123"),
                    display_name="管理员", role="admin"))
        await db.commit()
        logger.info("bootstrap.seed.done")


async def main():
    setup_logging()
    await init_db()
    await seed()


if __name__ == "__main__":
    asyncio.run(main())
