from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.schemas.strategy import (
    StrategyCloneRequest,
    StrategyCreateRequest,
    StrategyParametersUpdate,
    StrategyPublishRequest,
    StrategyStartRequest,
    StrategyStopRequest,
    StrategyUpdateRequest,
    StrategyValidateRequest,
)
from app.services.strategy_builder_service import strategy_builder_service
from app.services.strategy_service import strategy_service

router = APIRouter(tags=["strategies"])


@router.get("/indicator-catalog")
def get_indicator_catalog(
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(strategy_builder_service.get_indicator_catalog(), correlation_id=correlation_id)


@router.get("/strategies")
def list_strategies(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(strategy_service.list_strategies(db), correlation_id=correlation_id)


@router.post("/strategies")
def create_strategy(
    body: StrategyCreateRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = strategy_builder_service.create_strategy(
        db,
        name=body.name,
        description=body.description,
        definition=body.definition,
        parameters=body.parameters,
        correlation_id=correlation_id,
    )
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.get("/strategies/{strategy_id}")
def get_strategy(
    strategy_id: str,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(strategy_service.get_strategy(db, strategy_id), correlation_id=correlation_id)


@router.put("/strategies/{strategy_id}")
def update_strategy(
    strategy_id: str,
    body: StrategyUpdateRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = strategy_builder_service.update_strategy(
        db,
        strategy_id,
        name=body.name,
        description=body.description,
        definition=body.definition,
        parameters=body.parameters,
        correlation_id=correlation_id,
    )
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.post("/strategies/{strategy_id}/validate")
def validate_strategy(
    strategy_id: str,
    body: StrategyValidateRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    _ = db  # 预留：未来可校验策略归属
    result = strategy_builder_service.validate_definition(body.definition)
    return ok(result, correlation_id=correlation_id)


@router.post("/strategies/{strategy_id}/publish")
def publish_strategy(
    strategy_id: str,
    body: StrategyPublishRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = strategy_builder_service.publish_strategy(
        db, strategy_id, change_note=body.change_note, correlation_id=correlation_id
    )
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.post("/strategies/{strategy_id}/clone")
def clone_strategy(
    strategy_id: str,
    body: StrategyCloneRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = strategy_builder_service.clone_strategy(
        db, strategy_id, name=body.name, correlation_id=correlation_id
    )
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.post("/strategies/{strategy_id}/archive")
def archive_strategy(
    strategy_id: str,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = strategy_builder_service.archive_strategy(db, strategy_id, correlation_id=correlation_id)
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.get("/strategies/{strategy_id}/versions")
def list_strategy_versions(
    strategy_id: str,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(strategy_builder_service.list_versions(db, strategy_id), correlation_id=correlation_id)


@router.get("/strategies/{strategy_id}/versions/{version}")
def get_strategy_version(
    strategy_id: str,
    version: int,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(
        strategy_builder_service.get_version(db, strategy_id, version),
        correlation_id=correlation_id,
    )


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
        strategy_version=body.strategy_version,
        run_mode=body.run_mode,
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
