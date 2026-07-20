from datetime import datetime
from decimal import Decimal

from sqlalchemy import desc, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models.kline_bar import KlineBar as KlineBarModel
from app.db.models.market_snapshot import MarketSnapshot
from app.repositories.base import BaseRepository
from app.schemas.enums import Market
from app.sdk.models import KlineBar, QuoteSnapshot


class MarketRepository(BaseRepository[MarketSnapshot]):
    model = MarketSnapshot

    def insert_snapshot(self, quote: QuoteSnapshot) -> MarketSnapshot:
        row = MarketSnapshot(
            symbol=quote.symbol,
            market=quote.market,
            quote_time=quote.quote_time,
            last_price=quote.last_price,
            change_rate=quote.change_rate,
            volume=quote.volume,
            bid_price=quote.bid_price,
            ask_price=quote.ask_price,
            bid_volume=quote.bid_volume,
            ask_volume=quote.ask_volume,
            raw_payload=quote.raw_payload,
        )
        return self.add(row)

    def get_latest_quote(self, market: Market, symbol: str) -> MarketSnapshot | None:
        return (
            self.db.query(MarketSnapshot)
            .filter(MarketSnapshot.market == market, MarketSnapshot.symbol == symbol)
            .order_by(desc(MarketSnapshot.quote_time))
            .first()
        )

    def list_latest_quotes(
        self,
        *,
        market: Market | None = None,
        symbols: list[str] | None = None,
    ) -> list[MarketSnapshot]:
        if symbols:
            results: list[MarketSnapshot] = []
            for symbol in symbols:
                q = self.db.query(MarketSnapshot).filter(MarketSnapshot.symbol == symbol)
                if market is not None:
                    q = q.filter(MarketSnapshot.market == market)
                row = q.order_by(desc(MarketSnapshot.quote_time)).first()
                if row:
                    results.append(row)
            return results

        subq = (
            self.db.query(
                MarketSnapshot.market,
                MarketSnapshot.symbol,
                func.max(MarketSnapshot.quote_time).label("max_time"),
            )
            .group_by(MarketSnapshot.market, MarketSnapshot.symbol)
        )
        if market is not None:
            subq = subq.filter(MarketSnapshot.market == market)
        subq = subq.subquery()

        return (
            self.db.query(MarketSnapshot)
            .join(
                subq,
                (MarketSnapshot.market == subq.c.market)
                & (MarketSnapshot.symbol == subq.c.symbol)
                & (MarketSnapshot.quote_time == subq.c.max_time),
            )
            .order_by(MarketSnapshot.symbol)
            .all()
        )

    def upsert_klines(self, bars: list[KlineBar]) -> None:
        if not bars:
            return
        for bar in bars:
            stmt = insert(KlineBarModel).values(
                symbol=bar.symbol,
                market=bar.market,
                interval=bar.interval,
                bar_time=bar.bar_time,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                raw_payload=bar.raw_payload,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uk_kline_bars",
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                    "raw_payload": stmt.excluded.raw_payload,
                },
            )
            self.db.execute(stmt)
        self.db.flush()

    def query_klines(
        self,
        *,
        market: Market,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> list[KlineBarModel]:
        q = (
            self.db.query(KlineBarModel)
            .filter(
                KlineBarModel.market == market,
                KlineBarModel.symbol == symbol,
                KlineBarModel.interval == interval,
            )
        )
        if start:
            q = q.filter(KlineBarModel.bar_time >= start)
        if end:
            q = q.filter(KlineBarModel.bar_time <= end)
        return q.order_by(desc(KlineBarModel.bar_time)).limit(limit).all()
