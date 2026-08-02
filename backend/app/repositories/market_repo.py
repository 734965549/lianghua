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
from app.sdk.normalization import is_plausible_change_rate
from app.services.kline_quality import (
    is_trusted_kline,
    kline_identity,
    kline_source,
    prepare_kline,
)


class MarketRepository(BaseRepository[MarketSnapshot]):
    model = MarketSnapshot

    def insert_snapshot(self, quote: QuoteSnapshot) -> MarketSnapshot:
        stmt = insert(MarketSnapshot).values(
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
        stmt = stmt.on_conflict_do_update(
            constraint="uq_market_snapshots_identity",
            set_={
                "last_price": stmt.excluded.last_price,
                "change_rate": stmt.excluded.change_rate,
                "volume": stmt.excluded.volume,
                "bid_price": stmt.excluded.bid_price,
                "ask_price": stmt.excluded.ask_price,
                "bid_volume": stmt.excluded.bid_volume,
                "ask_volume": stmt.excluded.ask_volume,
                "raw_payload": stmt.excluded.raw_payload,
            },
        ).returning(MarketSnapshot)
        return self.db.execute(
            stmt,
            execution_options={"populate_existing": True},
        ).scalar_one()

    def get_latest_quote(self, market: Market, symbol: str) -> MarketSnapshot | None:
        row = (
            self.db.query(MarketSnapshot)
            .filter(MarketSnapshot.market == market, MarketSnapshot.symbol == symbol)
            .order_by(
                desc(MarketSnapshot.quote_time),
                desc(MarketSnapshot.created_at),
                desc(MarketSnapshot.id),
            )
            .first()
        )
        if row is None:
            return None
        change_rate = Decimal(str(row.change_rate))
        last_price = Decimal(str(row.last_price))
        if (
            not last_price.is_finite()
            or last_price <= 0
            or not is_plausible_change_rate(market, symbol, change_rate)
        ):
            return None
        return row

    def list_latest_quotes(
        self,
        *,
        market: Market | None = None,
        symbols: list[str] | None = None,
    ) -> list[MarketSnapshot]:
        if symbols:
            results: list[MarketSnapshot] = []
            for symbol in symbols:
                if market is not None:
                    row = self.get_latest_quote(market, symbol)
                    if row:
                        results.append(row)
                    continue
                q = self.db.query(MarketSnapshot).filter(MarketSnapshot.symbol == symbol)
                row = q.order_by(
                    desc(MarketSnapshot.quote_time),
                    desc(MarketSnapshot.created_at),
                    desc(MarketSnapshot.id),
                ).first()
                if (
                    row
                    and Decimal(str(row.last_price)).is_finite()
                    and Decimal(str(row.last_price)) > 0
                    and is_plausible_change_rate(
                        row.market, row.symbol, Decimal(str(row.change_rate))
                    )
                ):
                    results.append(row)
            return results

        # First reduce the multi-million-row snapshot table to rows at each
        # instrument's maximum quote time. The existing
        # (market, symbol, quote_time DESC) index can serve this step. DISTINCT
        # ON then resolves equal-time ties deterministically without sorting the
        # complete history by created_at and id.
        latest_times = (
            self.db.query(
                MarketSnapshot.market,
                MarketSnapshot.symbol,
                func.max(MarketSnapshot.quote_time).label("max_time"),
            )
            .group_by(MarketSnapshot.market, MarketSnapshot.symbol)
        )
        if market is not None:
            latest_times = latest_times.filter(MarketSnapshot.market == market)
        latest_times = latest_times.subquery()

        rows = (
            self.db.query(MarketSnapshot)
            .join(
                latest_times,
                (MarketSnapshot.market == latest_times.c.market)
                & (MarketSnapshot.symbol == latest_times.c.symbol)
                & (MarketSnapshot.quote_time == latest_times.c.max_time),
            )
            .distinct(MarketSnapshot.market, MarketSnapshot.symbol)
            .order_by(
                MarketSnapshot.market,
                MarketSnapshot.symbol,
                desc(MarketSnapshot.created_at),
                desc(MarketSnapshot.id),
            )
            .all()
        )
        return [
            row
            for row in rows
            if Decimal(str(row.last_price)).is_finite()
            and Decimal(str(row.last_price)) > 0
            and is_plausible_change_rate(
                row.market, row.symbol, Decimal(str(row.change_rate))
            )
        ]

    def upsert_klines(self, bars: list[KlineBar]) -> dict:
        if not bars:
            return {
                "received": 0,
                "accepted": 0,
                "quarantined": 0,
                "deduplicated": 0,
                "quarantine_reasons": [],
            }

        accepted: dict[tuple, KlineBar] = {}
        quarantine_reasons: list[dict] = []
        for original in bars:
            prepared = prepare_kline(original)
            if not prepared.accepted:
                quarantine_reasons.append(
                    {
                        "market": original.market.value,
                        "symbol": original.symbol,
                        "interval": original.interval,
                        "bar_time": original.bar_time.isoformat(),
                        "source": prepared.source,
                        "reasons": list(prepared.reasons),
                    }
                )
                continue
            accepted[kline_identity(prepared.bar)] = prepared.bar

        for bar in accepted.values():
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
        return {
            "received": len(bars),
            "accepted": len(accepted),
            "quarantined": len(quarantine_reasons),
            "deduplicated": len(bars) - len(accepted) - len(quarantine_reasons),
            "quarantine_reasons": quarantine_reasons,
        }

    def query_klines(
        self,
        *,
        market: Market,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
        trusted_only: bool = True,
        expected_source: str | None = None,
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
        fetch_limit = limit * 8 if (trusted_only or expected_source) else limit
        rows = q.order_by(desc(KlineBarModel.bar_time)).limit(fetch_limit).all()
        if not trusted_only and expected_source is None:
            return rows

        trusted: list[KlineBarModel] = []
        seen: set[tuple] = set()
        for row in rows:
            if trusted_only and not is_trusted_kline(row):
                continue
            if expected_source and kline_source(row.raw_payload) != expected_source:
                continue
            identity = kline_identity(row)
            if identity in seen:
                continue
            seen.add(identity)
            trusted.append(row)
            if len(trusted) >= limit:
                break
        return trusted

    def delete_klines(
        self,
        *,
        market: Market,
        symbol: str,
        interval: str | None = None,
    ) -> int:
        q = self.db.query(KlineBarModel).filter(
            KlineBarModel.market == market,
            KlineBarModel.symbol == symbol,
        )
        if interval:
            q = q.filter(KlineBarModel.interval == interval)
        count = q.count()
        q.delete(synchronize_session=False)
        self.db.flush()
        return count
