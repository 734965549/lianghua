from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handler import register_error_handlers
from app.api.routes import (
    ai_reports,
    ai_strategies,
    backtest,
    dashboard,
    health,
    history,
    instruments,
    klines,
    logs,
    orders,
    positions,
    quotes,
    risk,
    settings as settings_route,
    signals,
    strategies,
    strategy_runs,
    system,
    trades,
    watchlist,
    ws,
)
from app.core.config import settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.logging import setup_logging
from app.core.trading_calendar import validate_trading_calendar
from app.db.session import SessionLocal
from app.services.market_service import market_service
from app.services.instrument_catalog_service import instrument_catalog_service
from app.services.strategy_service import strategy_service
from app.workers.recovery import recover_on_startup
from app.workers.scheduler import shutdown_scheduler, start_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    calendar_status = validate_trading_calendar()
    logger.info("交易日历验证通过: %s", calendar_status)
    db = SessionLocal()
    try:
        recover_on_startup(db, correlation_id="startup")
        strategy_service.ensure_definitions(db)
        db.commit()
    finally:
        db.close()
    try:
        market_service.start()
    except Exception:
        # 实时行情源受网络、地区或授权限制时仍允许控制台启动，
        # 用户可在前端修正配置后通过 reconfigure 热恢复连接。
        logger.exception("行情源启动失败，系统以行情不可用状态继续运行")
    if market_service.started:
        instrument_catalog_service.start_background_sync()
    start_scheduler()
    yield
    shutdown_scheduler()
    market_service.stop()


app = FastAPI(title="Lianghua Quant", version="0.1.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:5174", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(health.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(instruments.router, prefix="/api")
app.include_router(settings_route.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(quotes.router, prefix="/api")
app.include_router(klines.router, prefix="/api")
app.include_router(strategies.router, prefix="/api")
app.include_router(strategy_runs.router, prefix="/api")
app.include_router(signals.router, prefix="/api")
app.include_router(risk.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(trades.router, prefix="/api")
app.include_router(positions.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(ai_reports.router, prefix="/api")
app.include_router(ai_strategies.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(watchlist.data_router, prefix="/api")
app.include_router(ws.router, prefix="/api")
