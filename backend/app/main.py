# ============================================================
# app/main.py — FastAPI 应用入口
# ============================================================

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import deployments, health, incidents, security, topology
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.scheduler import start_scheduler, stop_scheduler

# 触发工具注册（import 副作用）
import app.tools.observability  # noqa: F401

setup_logging()
logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("bestnative.startup", environment=settings.ENVIRONMENT, version=settings.APP_VERSION)
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("bestnative.shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Native 运维指挥中心",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Routers ----
app.include_router(health.router, prefix="/api")
app.include_router(topology.router, prefix="/api")
app.include_router(incidents.router, prefix="/api")
app.include_router(security.router, prefix="/api")
app.include_router(deployments.router, prefix="/api")


@app.get("/")
async def root():
    return {"app": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs"}
