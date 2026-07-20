import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.session import SessionLocal
from app.workers.breaker_monitor import check_breaker_conditions
from app.workers.sync_jobs import check_quote_stale, sync_assets, sync_orders_trades, sync_positions

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def _run_breaker_check() -> None:
    db = SessionLocal()
    try:
        check_breaker_conditions(db)
    except Exception:
        logger.exception("breaker_check 执行失败")
        db.rollback()
    finally:
        db.close()


def _run_check_quote_stale() -> None:
    db = SessionLocal()
    try:
        check_quote_stale(db)
    except Exception:
        logger.exception("check_quote_stale 执行失败")
        db.rollback()
    finally:
        db.close()


def _run_sync_positions() -> None:
    db = SessionLocal()
    try:
        sync_positions(db)
    except Exception:
        logger.exception("sync_positions 执行失败")
        db.rollback()
    finally:
        db.close()


def _run_sync_assets() -> None:
    db = SessionLocal()
    try:
        sync_assets(db)
    except Exception:
        logger.exception("sync_assets 执行失败")
        db.rollback()
    finally:
        db.close()


def _run_sync_orders_trades() -> None:
    db = SessionLocal()
    try:
        sync_orders_trades(db)
    except Exception:
        logger.exception("sync_orders_trades 执行失败")
        db.rollback()
    finally:
        db.close()


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_run_check_quote_stale, "interval", seconds=3, id="check_quote_stale")
    _scheduler.add_job(_run_sync_positions, "interval", seconds=15, id="sync_positions")
    _scheduler.add_job(_run_sync_assets, "interval", seconds=15, id="sync_assets")
    _scheduler.add_job(_run_sync_orders_trades, "interval", seconds=5, id="sync_orders_trades")
    _scheduler.add_job(_run_breaker_check, "interval", seconds=10, id="breaker_check")
    _scheduler.start()
    logger.info("AsyncIOScheduler 已启动")
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("AsyncIOScheduler 已停止")
