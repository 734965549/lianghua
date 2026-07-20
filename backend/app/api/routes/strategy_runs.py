from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.repositories.strategy_repo import StrategyRunRepository
from app.schemas.enums import StrategyRunStatus

router = APIRouter(tags=["strategy-runs"])


def _run_to_dict(row) -> dict:
    return {
        "run_id": str(row.id),
        "strategy_id": row.strategy_id,
        "status": row.status.value,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "stopped_at": row.stopped_at.isoformat() if row.stopped_at else None,
        "stop_reason": row.stop_reason,
        "parameters": row.parameters,
        "metrics": row.metrics,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/strategy-runs")
def list_strategy_runs(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    strategy_id: str | None = None,
    status: str | None = None,
):
    offset = (page - 1) * page_size
    st = StrategyRunStatus(status) if status else None
    rows, total = StrategyRunRepository(db).list_runs(
        strategy_id=strategy_id,
        status=st,
        offset=offset,
        limit=page_size,
    )
    return ok(
        {
            "items": [_run_to_dict(r) for r in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
        },
        correlation_id=correlation_id,
    )
