import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.session import SessionLocal
from app.workers.breaker_monitor import check_breaker_conditions
from app.workers.data_quality import run_quality_check
from app.workers.retention import run_retention_cleanup
from app.workers.sync_jobs import (
    check_quote_stale,
    run_daily_klines_update,
    run_intraday_klines_sync,
    sync_assets,
    sync_orders_trades,
    sync_positions,
    sync_watchlist_subscriptions,
)

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


def _run_retention_cleanup() -> None:
    db = SessionLocal()
    try:
        run_retention_cleanup(db, correlation_id="scheduler_retention")
    except Exception:
        logger.exception("retention_cleanup 执行失败")
        db.rollback()
    finally:
        db.close()


def _run_daily_klines_update() -> None:
    db = SessionLocal()
    try:
        run_daily_klines_update(db)
    except Exception:
        logger.exception("daily_klines_update 执行失败")
        db.rollback()
    finally:
        db.close()


def _run_intraday_klines_sync() -> None:
    db = SessionLocal()
    try:
        run_intraday_klines_sync(db)
    except Exception:
        logger.exception("intraday_klines_sync 执行失败")
        db.rollback()
    finally:
        db.close()


def _run_data_quality_check() -> None:
    db = SessionLocal()
    try:
        run_quality_check(db, correlation_id="scheduler_quality")
        db.commit()
    except Exception:
        logger.exception("data_quality_check 执行失败")
        db.rollback()
    finally:
        db.close()


def _run_watchlist_subscription_sync() -> None:
    db = SessionLocal()
    try:
        sync_watchlist_subscriptions(db)
        db.commit()
    except Exception:
        logger.exception("quote_subscription_sync 执行失败")
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
    _scheduler.add_job(
        _run_retention_cleanup,
        "cron",
        hour=3,
        minute=30,
        id="retention_cleanup",
    )
    _scheduler.add_job(_run_daily_klines_update, "cron", hour=15, minute=30, id="daily_klines_update")
    _scheduler.add_job(_run_intraday_klines_sync, "interval", minutes=5, id="intraday_klines_sync")
    _scheduler.add_job(_run_data_quality_check, "cron", hour=8, minute=0, id="data_quality_check")
    _scheduler.add_job(_run_watchlist_subscription_sync, "interval", seconds=60, id="quote_subscription_sync")
    _scheduler.start()
    logger.info("AsyncIOScheduler 已启动")
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("AsyncIOScheduler 已停止")
