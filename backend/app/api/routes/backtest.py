from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import BizError, ok
from app.backtest.models import BacktestCreateRequest, BacktestResult
from app.schemas.error_codes import ErrorCode
from app.services.backtest_service import backtest_service

router = APIRouter(tags=["backtest"])


@router.post("/backtests")
def create_backtest(
    body: BacktestCreateRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    result = backtest_service.run_backtest(db, body)
    return ok(result.model_dump(mode="json"), correlation_id=correlation_id)


@router.get("/backtests")
def list_backtests(
    offset: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    items, total = backtest_service.list_backtests(db, offset=offset, limit=limit)
    return ok(
        {"items": [item.model_dump(mode="json") for item in items], "total": total},
        correlation_id=correlation_id,
    )


@router.get("/backtests/{backtest_id}")
def get_backtest(
    backtest_id: UUID,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    item = backtest_service.get_backtest(db, backtest_id)
    if item is None:
        raise BizError(ErrorCode.SYS_NOT_FOUND, f"回测记录不存在: {backtest_id}")
    return ok(item.model_dump(mode="json"), correlation_id=correlation_id)


@router.delete("/backtests/{backtest_id}")
def delete_backtest(
    backtest_id: UUID,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    deleted = backtest_service.delete_backtest(db, backtest_id)
    if not deleted:
        raise BizError(ErrorCode.SYS_NOT_FOUND, f"回测记录不存在: {backtest_id}")
    return ok({"deleted": True}, correlation_id=correlation_id)
