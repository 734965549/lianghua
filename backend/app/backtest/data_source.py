import heapq
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterator

from sqlalchemy.orm import Session

from app.repositories.market_repo import MarketRepository
from app.schemas.enums import Market
from app.sdk.models import KlineBar, QuoteSnapshot


def _guess_market(symbol: str) -> Market:
    upper = symbol.upper()
    if upper.startswith("IF") or upper.startswith("RB") or "." not in symbol:
        return Market.FUTURES
    return Market.STOCK


@dataclass
class MarketEvent:
    """统一市场事件，按时间顺序回放。"""

    event_time: datetime
    symbol: str
    bar: KlineBar | None = None
    quote: QuoteSnapshot | None = None


class HistoricalDataSource(ABC):
    """历史数据读取抽象。"""

    @abstractmethod
    def load_events(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval: str,
    ) -> Iterator[MarketEvent]: ...


class KlineDataSource(HistoricalDataSource):
    """从数据库读取 K 线并按时间合并。"""

    def __init__(self, db: Session):
        self.repo = MarketRepository(db)

    def load_events(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval: str,
    ) -> Iterator[MarketEvent]:
        per_symbol_events: list[Iterator[MarketEvent]] = []
        for symbol in symbols:
            market = _guess_market(symbol)
            rows = self.repo.query_klines(
                market=market,
                symbol=symbol,
                interval=interval,
                start=start,
                end=end,
                limit=10000,
            )
            rows = list(reversed(rows))
            per_symbol_events.append(self._to_events(rows, market))

        for event in heapq.merge(*per_symbol_events, key=lambda e: e.event_time):
            yield event

    def _to_events(self, rows: list, market: Market) -> Iterator[MarketEvent]:
        for row in rows:
            bar = KlineBar(
                symbol=row.symbol,
                market=market,
                interval=row.interval,
                bar_time=row.bar_time,
                open=Decimal(str(row.open)),
                high=Decimal(str(row.high)),
                low=Decimal(str(row.low)),
                close=Decimal(str(row.close)),
                volume=Decimal(str(row.volume)),
            )
            yield MarketEvent(event_time=row.bar_time, symbol=row.symbol, bar=bar)


class SimulatedTickDataSource(HistoricalDataSource):
    """基于 K 线生成 OHLC 伪 tick，用于触发 on_quote。"""

    def __init__(self, db: Session):
        self.kline_source = KlineDataSource(db)

    def load_events(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval: str,
    ) -> Iterator[MarketEvent]:
        base_events = self.kline_source.load_events(symbols, start, end, interval)
        for event in base_events:
            bar = event.bar
            if bar is None:
                continue
            prices = [bar.open, bar.high, bar.low, bar.close]
            for i, price in enumerate(prices):
                quote_time = bar.bar_time + timedelta(milliseconds=i * 100)
                quote = QuoteSnapshot(
                    symbol=bar.symbol,
                    market=bar.market,
                    last_price=price,
                    change_rate=Decimal("0"),
                    volume=bar.volume / Decimal("4") if bar.volume else Decimal("0"),
                    quote_time=quote_time,
                )
                yield MarketEvent(
                    event_time=quote_time,
                    symbol=bar.symbol,
                    quote=quote,
                )


class TickDataSource(HistoricalDataSource):
    """真实 tick 数据源预留接口。"""

    def load_events(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval: str,
    ) -> Iterator[MarketEvent]:
        raise NotImplementedError("真实 tick 回放尚未实现，需接入历史 tick 数据源")
