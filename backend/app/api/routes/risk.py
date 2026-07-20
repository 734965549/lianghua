from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.schemas.strategy import EmergencyStopRequest, RiskResumeRequest, RiskSettingsUpdate
from app.services.risk_service import RiskService

router = APIRouter(tags=["risk"])


@router.get("/risk/status")
def risk_status(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = RiskService(db, correlation_id=correlation_id)
    return ok(svc.get_status(), correlation_id=correlation_id)


@router.get("/risk/checks")
def risk_checks(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    result: str | None = None,
):
    svc = RiskService(db, correlation_id=correlation_id)
    return ok(svc.list_checks(page=page, page_size=page_size, result=result), correlation_id=correlation_id)


@router.get("/risk/settings")
def risk_settings(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = RiskService(db, correlation_id=correlation_id)
    return ok(svc.get_settings(), correlation_id=correlation_id)


@router.put("/risk/settings")
def update_risk_settings(
    body: RiskSettingsUpdate,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = RiskService(db, correlation_id=correlation_id)
    data = svc.update_settings(body.model_dump(exclude_none=True))
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.post("/risk/emergency-stop")
def emergency_stop(
    body: EmergencyStopRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = RiskService(db, correlation_id=correlation_id)
    data = svc.emergency_stop(body.reason, cancel_open_orders=body.cancel_open_orders)
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.post("/risk/resume")
def risk_resume(
    body: RiskResumeRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    if not body.confirm:
        from app.api.response import BizError

        raise BizError("RISK_CONFIRM_REQUIRED", "恢复交易需要 confirm=true")
    svc = RiskService(db, correlation_id=correlation_id)
    data = svc.resume(body.reason)
    db.commit()
    return ok(data, correlation_id=correlation_id)
