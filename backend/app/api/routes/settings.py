import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.services.settings_service import SettingsService

router = APIRouter(tags=["settings"])
logger = logging.getLogger(__name__)


def _reconfigure_market_data() -> None:
    """在响应返回后热切换行情源，避免连接恢复阻塞设置保存。"""
    from app.services.instrument_catalog_service import instrument_catalog_service
    from app.services.market_service import market_service

    try:
        market_service.reconfigure()
    except Exception:
        logger.exception("行情源后台热切换失败")
        return
    instrument_catalog_service.start_background_sync()


class DatabaseTestBody(BaseModel):
    database_url: str | None = Field(default=None, alias="database_url")


class SdkTestBody(BaseModel):
    market: str


class AiTestBody(BaseModel):
    ai: dict[str, Any] | None = None


class MarketDataTestBody(BaseModel):
    market_data: dict[str, Any] | None = None


class SettingsUpdateBody(BaseModel):
    database: dict[str, Any] | None = None
    stock_sdk: dict[str, Any] | None = None
    futures_sdk: dict[str, Any] | None = None
    market_data: dict[str, Any] | None = None
    ai: dict[str, Any] | None = None
    backup_dir: str | None = None

    model_config = {"extra": "allow"}


@router.get("/settings")
def get_settings(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = SettingsService(db, correlation_id=correlation_id)
    return ok(svc.get_settings(), correlation_id=correlation_id)


@router.put("/settings")
def update_settings(
    body: SettingsUpdateBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = SettingsService(db, correlation_id=correlation_id)
    data = svc.update_settings(body.model_dump(exclude_none=True), correlation_id=correlation_id)
    db.commit()
    if body.market_data is not None:
        background_tasks.add_task(_reconfigure_market_data)
    return ok(data, correlation_id=correlation_id)


@router.post("/settings/test-database")
def test_database(
    body: DatabaseTestBody | None = None,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = SettingsService(db, correlation_id=correlation_id)
    url = body.database_url if body else None
    return ok(svc.test_database(url), correlation_id=correlation_id)


@router.post("/settings/test-sdk")
def test_sdk(
    body: SdkTestBody,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = SettingsService(db, correlation_id=correlation_id)
    return ok(svc.test_sdk(body.market), correlation_id=correlation_id)


@router.post("/settings/test-ai")
def test_ai(
    body: AiTestBody | None = None,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = SettingsService(db, correlation_id=correlation_id)
    data = svc.test_ai(body.ai if body else None)
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.post("/settings/test-market-data")
def test_market_data(
    body: MarketDataTestBody | None = None,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = SettingsService(db, correlation_id=correlation_id)
    data = svc.test_market_data(body.market_data if body else None)
    db.commit()
    return ok(data, correlation_id=correlation_id)
