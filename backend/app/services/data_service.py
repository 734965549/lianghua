from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.repositories.data_sync_log_repo import DataSyncLogRepository
from app.repositories.market_repo import MarketRepository
from app.schemas.enums import Market
from app.schemas.error_codes import ErrorCode
from app.services.watchlist_service import watchlist_service
from app.workers.data_downloader import data_downloader
from app.workers.data_quality import data_overview, integrity_report, run_quality_check


def _sync_log_to_dict(row) -> dict:
    return {
        "id": str(row.id),
        "task_type": row.task_type,
        "status": row.status,
        "symbols": row.symbols,
        "intervals": row.intervals,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "progress": row.progress,
        "error_message": row.error_message,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "created_at": row.created_at.isoformat(),
    }


class DataService:
    def trigger_download(
        self,
        db: Session,
        *,
        symbols: list[str] | None,
        intervals: list[str],
        start_date: str,
        end_date: str | None,
        use_watchlist: bool,
    ) -> dict:
        if data_downloader.is_running:
            raise BizError(ErrorCode.SYS_VALIDATION_ERROR, "已有下载任务正在运行", status=409)

        targets: list[tuple[Market, str]] = []
        if symbols:
            for sym in symbols:
                market = Market.FUTURES if sym.startswith(("IF", "IC", "IH", "IM")) else Market.STOCK
                targets.append((market, sym))
        elif use_watchlist:
            for market, sym, _ in watchlist_service.get_download_targets(db):
                targets.append((market, sym))
        else:
            raise BizError(ErrorCode.SYS_VALIDATION_ERROR, "请指定 symbols 或启用 use_watchlist")

        if not targets:
            raise BizError(ErrorCode.SYS_VALIDATION_ERROR, "没有可下载的标的")

        if not intervals:
            intervals = ["1d"]

        task_id = data_downloader.start_download(
            symbols=targets,
            intervals=intervals,
            start_date=start_date,
            end_date=end_date or datetime.now(timezone.utc).strftime("%Y%m%d"),
        )
        return {"task_id": task_id, "status": "started"}

    def download_status(self, db: Session) -> dict:
        progress = data_downloader.get_progress()
        if progress:
            return progress
        repo = DataSyncLogRepository(db)
        latest = repo.get_latest_running()
        if latest:
            return {"task_id": str(latest.id), **latest.progress, "status": latest.status}
        recent = repo.list_recent(limit=1)
        if recent:
            row = recent[0]
            return {"task_id": str(row.id), **row.progress, "status": row.status}
        return {"status": "idle", "done": 0, "total": 0, "items": {}}

    def download_history(self, db: Session, limit: int = 20) -> list[dict]:
        repo = DataSyncLogRepository(db)
        return [_sync_log_to_dict(r) for r in repo.list_recent(limit=limit)]

    def get_integrity(self, db: Session) -> dict:
        return integrity_report(db)

    def get_quality(self, db: Session) -> dict:
        return run_quality_check(db)

    def get_overview(self, db: Session) -> dict:
        return data_overview(db)

    def query_klines(
        self,
        db: Session,
        *,
        market: str,
        symbol: str,
        interval: str,
        start: str | None,
        end: str | None,
        limit: int = 500,
    ) -> list[dict]:
        from app.services.market_service import kline_to_dict, market_service

        start_dt = datetime.fromisoformat(start) if start else None
        end_dt = datetime.fromisoformat(end) if end else None
        return market_service.get_klines(
            db,
            market=market,
            symbol=symbol,
            interval=interval,
            start=start_dt,
            end=end_dt,
            limit=limit,
        )

    def delete_klines(
        self,
        db: Session,
        *,
        market: str,
        symbol: str,
        interval: str | None,
    ) -> dict:
        mkt = Market(market)
        repo = MarketRepository(db)
        deleted = repo.delete_klines(market=mkt, symbol=symbol, interval=interval)
        return {"deleted": deleted}


data_service = DataService()
