from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.core.time import to_utc_iso
from app.core.text import repair_display_text
from app.repositories.signal_repo import SignalRepository

router = APIRouter(tags=["signals"])


def _signal_to_dict(row) -> dict:
    return {
        "signal_id": str(row.signal_id),
        "strategy_id": row.strategy_id,
        "symbol": row.symbol,
        "market": row.market.value,
        "side": row.side.value,
        "action": row.action.value,
        "price_type": row.price_type.value,
        "price": str(row.price),
        "quantity": str(row.quantity),
        "reason": repair_display_text(row.reason),
        "signal_time": to_utc_iso(row.signal_time),
        "metadata": row.metadata_,
    }


@router.get("/signals")
def list_signals(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    strategy_id: str | None = None,
    symbol: str | None = None,
):
    offset = (page - 1) * page_size
    repo = SignalRepository(db)
    rows, total = repo.list_signals(
        strategy_id=strategy_id,
        symbol=symbol,
        offset=offset,
        limit=page_size,
    )
    return ok(
        {
            "items": [_signal_to_dict(r) for r in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
        },
        correlation_id=correlation_id,
    )
