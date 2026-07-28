from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.db.models.watchlist import WatchlistItem
from app.repositories.watchlist_repo import WatchlistRepository
from app.schemas.enums import Market
from app.schemas.error_codes import ErrorCode

DEFAULT_WATCHLIST: list[dict] = [
    {"symbol": "600000.SH", "market": Market.STOCK, "alias": "浦发银行"},
    {"symbol": "IF2509", "market": Market.FUTURES, "alias": "沪深300主连"},
]


def _item_to_dict(row: WatchlistItem) -> dict:
    return {
        "id": str(row.id),
        "symbol": row.symbol,
        "market": row.market.value if isinstance(row.market, Market) else row.market,
        "alias": row.alias,
        "enabled": row.enabled,
        "download_1d": row.download_1d,
        "download_1m": row.download_1m,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


class WatchlistService:
    def ensure_defaults(self, db: Session) -> None:
        repo = WatchlistRepository(db)
        if repo.list_all():
            return
        for item in DEFAULT_WATCHLIST:
            repo.add(
                WatchlistItem(
                    symbol=item["symbol"],
                    market=item["market"],
                    alias=item["alias"],
                    enabled=True,
                    download_1d=True,
                    download_1m=False,
                )
            )
        db.flush()

    def list_items(self, db: Session) -> list[dict]:
        repo = WatchlistRepository(db)
        return [_item_to_dict(r) for r in repo.list_all()]

    def add_item(
        self,
        db: Session,
        *,
        symbol: str,
        market: Market | str,
        alias: str = "",
        enabled: bool = True,
        download_1d: bool = True,
        download_1m: bool = False,
    ) -> dict:
        if isinstance(market, str):
            market = Market(market)
        repo = WatchlistRepository(db)
        if repo.get_by_symbol(market, symbol):
            raise BizError(ErrorCode.SYS_VALIDATION_ERROR, f"标的已存在: {symbol}")
        row = repo.add(
            WatchlistItem(
                symbol=symbol.upper(),
                market=market,
                alias=alias,
                enabled=enabled,
                download_1d=download_1d,
                download_1m=download_1m,
            )
        )
        return _item_to_dict(row)

    def update_item(
        self,
        db: Session,
        market: Market | str,
        symbol: str,
        *,
        alias: str | None = None,
        enabled: bool | None = None,
        download_1d: bool | None = None,
        download_1m: bool | None = None,
    ) -> dict:
        if isinstance(market, str):
            market = Market(market)
        repo = WatchlistRepository(db)
        row = repo.get_by_symbol(market, symbol)
        if row is None:
            raise BizError(ErrorCode.SYS_NOT_FOUND, f"标的不存在: {symbol}", status=404)
        if alias is not None:
            row.alias = alias
        if enabled is not None:
            row.enabled = enabled
        if download_1d is not None:
            row.download_1d = download_1d
        if download_1m is not None:
            row.download_1m = download_1m
        row.updated_at = datetime.now(timezone.utc)
        db.flush()
        return _item_to_dict(row)

    def remove_item(self, db: Session, market: Market | str, symbol: str) -> None:
        if isinstance(market, str):
            market = Market(market)
        repo = WatchlistRepository(db)
        if not repo.delete_by_symbol(market, symbol):
            raise BizError(ErrorCode.SYS_NOT_FOUND, f"标的不存在: {symbol}", status=404)

    def get_enabled_subscriptions(self, db: Session) -> dict[Market, list[str]]:
        repo = WatchlistRepository(db)
        return repo.enabled_subscriptions()

    def get_download_targets(self, db: Session) -> list[tuple[Market, str, list[str]]]:
        """返回 (market, symbol, intervals) 列表。"""
        repo = WatchlistRepository(db)
        targets: list[tuple[Market, str, list[str]]] = []
        for row in repo.list_all(enabled_only=True):
            intervals: list[str] = []
            if row.download_1d:
                intervals.append("1d")
            if row.download_1m:
                intervals.append("1m")
            if intervals:
                targets.append((row.market, row.symbol, intervals))
        return targets


watchlist_service = WatchlistService()
