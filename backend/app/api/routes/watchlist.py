from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.schemas.data import DataDownloadRequest
from app.schemas.enums import Market
from app.schemas.watchlist import WatchlistCreateRequest, WatchlistUpdateRequest
from app.services.data_service import data_service
from app.services.watchlist_service import watchlist_service

router = APIRouter(tags=["watchlist"])


@router.get("/watchlist")
def list_watchlist(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(watchlist_service.list_items(db), correlation_id=correlation_id)


@router.post("/watchlist")
def add_watchlist_item(
    body: WatchlistCreateRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = watchlist_service.add_item(
        db,
        symbol=body.symbol,
        market=body.market,
        alias=body.alias,
        enabled=body.enabled,
        download_1d=body.download_1d,
        download_1m=body.download_1m,
    )
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.patch("/watchlist/{market}/{symbol}")
def update_watchlist_item(
    market: str,
    symbol: str,
    body: WatchlistUpdateRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = watchlist_service.update_item(
        db,
        market,
        symbol,
        alias=body.alias,
        enabled=body.enabled,
        download_1d=body.download_1d,
        download_1m=body.download_1m,
    )
    db.commit()
    return ok(data, correlation_id=correlation_id)


@router.delete("/watchlist/{market}/{symbol}")
def delete_watchlist_item(
    market: str,
    symbol: str,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    watchlist_service.remove_item(db, market, symbol)
    db.commit()
    return ok({"deleted": True}, correlation_id=correlation_id)


data_router = APIRouter(tags=["data"])


@data_router.post("/data/download")
def trigger_download(
    body: DataDownloadRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = data_service.trigger_download(
        db,
        symbols=body.symbols,
        intervals=body.intervals,
        start_date=body.start_date,
        end_date=body.end_date,
        use_watchlist=body.use_watchlist,
    )
    return ok(data, correlation_id=correlation_id)


@data_router.get("/data/download/status")
def download_status(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(data_service.download_status(db), correlation_id=correlation_id)


@data_router.get("/data/download/history")
def download_history(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(data_service.download_history(db, limit=limit), correlation_id=correlation_id)


@data_router.post("/data/download/{task_id}/cancel")
def cancel_download(
    task_id: str,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(
        data_service.cancel_download(db, task_id),
        correlation_id=correlation_id,
    )


@data_router.post("/data/download/{task_id}/retry")
def retry_download(
    task_id: str,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(
        data_service.retry_download(db, task_id),
        correlation_id=correlation_id,
    )


@data_router.get("/data/integrity")
def data_integrity(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(data_service.get_integrity(db), correlation_id=correlation_id)


@data_router.get("/data/quality")
def data_quality(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = data_service.get_quality(db)
    db.commit()
    return ok(data, correlation_id=correlation_id)


@data_router.get("/data/overview")
def data_overview_api(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    return ok(data_service.get_overview(db), correlation_id=correlation_id)


@data_router.get("/data/klines")
def browse_klines(
    market: str = Query(...),
    symbol: str = Query(...),
    interval: str = Query("1d"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = data_service.query_klines(
        db, market=market, symbol=symbol, interval=interval, start=start, end=end, limit=limit
    )
    return ok(data, correlation_id=correlation_id)


@data_router.delete("/data/klines")
def delete_klines(
    market: str = Query(...),
    symbol: str = Query(...),
    interval: str | None = Query(None),
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = data_service.delete_klines(db, market=market, symbol=symbol, interval=interval)
    db.commit()
    return ok(data, correlation_id=correlation_id)
