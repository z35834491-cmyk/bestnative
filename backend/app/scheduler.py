# ============================================================
# app/scheduler.py — 定时任务（APScheduler）
# 周期自动发现 + 每天凌晨全平台安全巡检
# ============================================================

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger

logger = get_logger("scheduler")

_scheduler = None


async def _periodic_discovery():
    """周期自动发现（K8s）。无 kubeconfig 时静默跳过。"""
    if not (settings.KUBECONFIG or settings.K8S_IN_CLUSTER):
        return
    from app.engine.discovery import DiscoveryEngine
    async with AsyncSessionLocal() as db:
        try:
            await DiscoveryEngine(db).run(
                "kubernetes", settings.CLUSTER_NAME,
                {"in_cluster": settings.K8S_IN_CLUSTER, "kubeconfig": settings.KUBECONFIG or None, "context": settings.K8S_CONTEXT or None},
            )
            await db.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("scheduler.discovery.failed", error=str(e))


async def _full_platform_scan():
    """每天凌晨全平台安全巡检。"""
    from app.agents.security.agent import SecurityAgent
    from app.models.security import ScanSession
    async with AsyncSessionLocal() as db:
        try:
            session = ScanSession(target="full-platform", scope="full_platform",
                                  status="init", triggered_by="scheduler")
            db.add(session)
            await db.flush()
            sid = str(session.id)
            await db.commit()
            await SecurityAgent(db).scan(sid)
            await db.commit()
            logger.info("scheduler.scan.done", session=sid)
        except Exception as e:  # noqa: BLE001
            logger.warning("scheduler.scan.failed", error=str(e))


def start_scheduler():
    global _scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        _scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")
        _scheduler.add_job(_periodic_discovery, IntervalTrigger(seconds=settings.DISCOVERY_INTERVAL),
                           id="discovery", replace_existing=True)
        _scheduler.add_job(_full_platform_scan, CronTrigger.from_crontab(settings.AUTO_SCAN_CRON),
                           id="full_scan", replace_existing=True)
        _scheduler.start()
        logger.info("scheduler.started", discovery_interval=settings.DISCOVERY_INTERVAL,
                    scan_cron=settings.AUTO_SCAN_CRON)
    except Exception as e:  # noqa: BLE001
        logger.warning("scheduler.start.failed", error=str(e))


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
