from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.services.system_service import SystemStateService

router = APIRouter(tags=["system"])


@router.get("/system/status")
def system_status(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = SystemStateService(db, correlation_id=correlation_id)
    return ok(svc.get_status(), correlation_id=correlation_id)
