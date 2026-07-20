from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from app.schemas.enums import Market, OrderSide, PriceType, SignalAction
from app.sdk.models import KlineBar, QuoteSnapshot


class StrategyContext:
    """策略运行上下文。只读数据 + 信号提交。"""

    def __init__(
        self,
        *,
        strategy_id: str,
        run_id: str,
        parameters: dict,
        market_data_reader,
        account_reader,
        signal_sink,
        logger,
    ):
        self.strategy_id = strategy_id
        self.run_id = run_id
        self.parameters = parameters
        self._market_reader = market_data_reader
        self._account_reader = account_reader
        self._signal_sink = signal_sink
        self._logger = logger

    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> list[KlineBar]:
        return self._market_reader.get_klines(symbol, interval, limit)

    def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        return self._market_reader.get_quote(symbol)

    def get_position(self, symbol: str) -> dict | None:
        return self._account_reader.get_position(symbol)

    def get_account(self) -> dict:
        return self._account_reader.get_account()

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
        signal_id = str(uuid4())
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
            signal_time=datetime.now(),
            metadata=metadata or {},
        )
        return signal_id

    def log(self, level: str, message: str, **extra):
        self._logger(level, self.strategy_id, message, extra)
