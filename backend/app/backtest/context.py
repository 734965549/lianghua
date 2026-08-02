import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from app.repositories.market_repo import MarketRepository
from app.schemas.enums import Market, OrderSide, PriceType, SignalAction
from app.sdk.models import KlineBar, QuoteSnapshot

logger = logging.getLogger(__name__)


def _guess_market(symbol: str) -> Market:
    upper = symbol.upper()
    if upper.startswith("IF") or upper.startswith("RB") or "." not in symbol:
        return Market.FUTURES
    return Market.STOCK


class BacktestContext:
    """回测专用策略上下文，行为与 StrategyContext 保持一致。"""

    def __init__(
        self,
        *,
        strategy_id: str,
        run_id: str,
        parameters: dict,
        interval: str,
        db: Session,
        current_time_fn: Callable[[], datetime],
        account,
        signal_sink: Callable[..., None],
    ):
        self.strategy_id = strategy_id
        self.run_id = run_id
        self.parameters = parameters
        self.interval = interval
        self._db = db
        self._current_time_fn = current_time_fn
        self._account = account
        self._signal_sink = signal_sink
        self._market_repo = MarketRepository(db) if db is not None else None

    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> list[KlineBar]:
        if self._market_repo is None:
            return []
        market = _guess_market(symbol)
        rows = self._market_repo.query_klines(
            market=market,
            symbol=symbol,
            interval=interval,
            end=self._current_time_fn(),
            limit=limit,
        )
        return [
            KlineBar(
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
            for row in reversed(rows)
        ]

    def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        if self._market_repo is None:
            return None
        market = _guess_market(symbol)
        row = self._market_repo.get_latest_quote(market, symbol)
        if row is None:
            return None
        return QuoteSnapshot(
            symbol=row.symbol,
            market=market,
            last_price=Decimal(str(row.last_price)),
            change_rate=Decimal(str(row.change_rate)),
            volume=Decimal(str(row.volume)),
            bid_price=Decimal(str(row.bid_price)) if row.bid_price is not None else None,
            ask_price=Decimal(str(row.ask_price)) if row.ask_price is not None else None,
            quote_time=row.quote_time,
        )

    def get_position(self, symbol: str) -> dict | None:
        pos = self._account.get_position(symbol)
        if pos is None:
            return None
        return {
            "symbol": pos.symbol,
            "quantity": str(pos.quantity),
            "avg_cost": str(pos.avg_cost),
        }

    def get_account(self) -> dict:
        return self._account.get_account()

    def submit_signal(
        self,
        *,
        symbol: str,
        market: Market,
        side: OrderSide,
        action: SignalAction,
        price_type: PriceType,
        quantity: Decimal,
        price: Decimal | None = None,
        reason: str = "",
        metadata: dict | None = None,
    ) -> str:
        signal_id = str(uuid.uuid4())
        self._signal_sink(
            signal_id=signal_id,
            strategy_id=self.strategy_id,
            symbol=symbol,
            market=market,
            side=side,
            action=action,
            price_type=price_type,
            price=price or Decimal("0"),
            quantity=quantity,
            reason=reason,
            signal_time=self._current_time_fn(),
            metadata=metadata or {},
        )
        return signal_id

    def log(self, level: str, message: str, **extra):
        logger.log(getattr(logging, level.upper(), logging.INFO), "[%s] %s %s", self.strategy_id, message, extra)
