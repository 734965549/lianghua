from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.services.settings_service import SettingsService

router = APIRouter(tags=["settings"])


class DatabaseTestBody(BaseModel):
    database_url: str | None = Field(default=None, alias="database_url")


class SdkTestBody(BaseModel):
    market: str


class SettingsUpdateBody(BaseModel):
    database: dict[str, Any] | None = None
    stock_sdk: dict[str, Any] | None = None
    futures_sdk: dict[str, Any] | None = None
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
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = SettingsService(db, correlation_id=correlation_id)
    data = svc.update_settings(body.model_dump(exclude_none=True), correlation_id=correlation_id)
    db.commit()
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
