from sqlalchemy.orm import Session

from app.db.models.watchlist import WatchlistItem
from app.repositories.base import BaseRepository
from app.schemas.enums import Market


class WatchlistRepository(BaseRepository[WatchlistItem]):
    model = WatchlistItem

    def list_all(self, *, enabled_only: bool = False) -> list[WatchlistItem]:
        q = self.db.query(WatchlistItem).order_by(WatchlistItem.symbol)
        if enabled_only:
            q = q.filter(WatchlistItem.enabled.is_(True))
        return q.all()

    def get_by_symbol(self, market: Market, symbol: str) -> WatchlistItem | None:
        return (
            self.db.query(WatchlistItem)
            .filter(WatchlistItem.market == market, WatchlistItem.symbol == symbol)
            .first()
        )

    def delete_by_symbol(self, market: Market, symbol: str) -> bool:
        row = self.get_by_symbol(market, symbol)
        if row is None:
            return False
        self.db.delete(row)
        self.db.flush()
        return True

    def enabled_subscriptions(self) -> dict[Market, list[str]]:
        rows = self.list_all(enabled_only=True)
        result: dict[Market, list[str]] = {Market.STOCK: [], Market.FUTURES: []}
        for row in rows:
            result[row.market].append(row.symbol)
        return result
