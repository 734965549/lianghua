from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handler import register_error_handlers
from app.api.routes import (
    ai_reports,
    dashboard,
    health,
    history,
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
    ws,
)
from app.core.config import settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.services.market_service import market_service
from app.services.strategy_service import strategy_service
from app.workers.recovery import recover_on_startup
from app.workers.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    db = SessionLocal()
    try:
        recover_on_startup(db, correlation_id="startup")
        strategy_service.ensure_definitions(db)
        db.commit()
    finally:
        db.close()
    market_service.start()
    start_scheduler()
    yield
    shutdown_scheduler()
    market_service.stop()


app = FastAPI(title="Lianghua Quant", version="0.1.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(health.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(system.router, prefix="/api")
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
app.include_router(ws.router, prefix="/api")
