from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.schemas.strategy import StrategyParametersUpdate, StrategyStartRequest, StrategyStopRequest
from app.services.strategy_service import strategy_service

router = APIRouter(tags=["strategies"])


@router.get("/strategies")
def list_strategies(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(strategy_service.list_strategies(db), correlation_id=correlation_id)


@router.get("/strategies/{strategy_id}")
def get_strategy(
    strategy_id: str,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(strategy_service.get_strategy(db, strategy_id), correlation_id=correlation_id)


@router.put("/strategies/{strategy_id}/parameters")
def update_parameters(
    strategy_id: str,
    body: StrategyParametersUpdate,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = strategy_service.update_parameters(
        db, strategy_id, body.parameters, correlation_id=correlation_id
    )
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.post("/strategies/{strategy_id}/start")
def start_strategy(
    strategy_id: str,
    body: StrategyStartRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = strategy_service.start(
        db,
        strategy_id,
        symbols=body.symbols or None,
        parameters=body.parameters,
        confirm=body.confirm,
        reason=body.reason,
        correlation_id=correlation_id,
    )
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.post("/strategies/{strategy_id}/stop")
def stop_strategy(
    strategy_id: str,
    body: StrategyStopRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = strategy_service.stop(db, strategy_id, reason=body.reason, correlation_id=correlation_id)
    db.commit()
    return ok(data, correlation_id=correlation_id)
