"""将独立的 MarketDataAdapter 包装为 TradingAdapter，实现行情与交易解耦。"""

from app.schemas.enums import Market
from app.sdk.base import TradingAdapter
from app.sdk.market_data.base import MarketDataAdapter
from app.sdk.mock_adapter import MockTradingAdapter
from app.sdk.models import (
    AccountSnapshot,
    AdapterStatus,
    CancelOrderRequest,
    CancelOrderResult,
    KlineBar,
    OrderQuery,
    OrderSnapshot,
    PlaceOrderRequest,
    PlaceOrderResult,
    PositionSnapshot,
    QuoteSnapshot,
    TradeQuery,
    TradeSnapshot,
)


class MarketDataBackedAdapter(TradingAdapter):
    """行情数据由 MarketDataAdapter 提供，交易由内部 trading_adapter 提供。

    设计目标：
    - 行情源可独立切换为 Tushare/RQData/Wind 等专业数据源。
    - 交易端暂时走 mock 或未来接入真实 broker，互不干扰。
    """

    def __init__(
        self,
        *,
        market: Market,
        market_data_adapter: MarketDataAdapter,
        trading_adapter: TradingAdapter | None = None,
    ):
        super().__init__()
        self.market = market
        self._market_data = market_data_adapter
        self._trading = trading_adapter or MockTradingAdapter(market=market)
        self._connected = False

        # 行情事件透传
        self._market_data.on_quote_update(lambda snap: self._on_quote_update(snap) if self._on_quote_update else None)

        # 交易事件透传
        self._trading.on_order_update(
            lambda ev: self._on_order_update(ev) if self._on_order_update else None
        )
        self._trading.on_trade_update(
            lambda ev: self._on_trade_update(ev) if self._on_trade_update else None
        )
        self._trading.on_connection_change(
            lambda ev: self._on_connection_change(ev) if self._on_connection_change else None
        )

    @property
    def name(self) -> str:
        return self._market_data.name

    def list_instruments(self) -> list[dict]:
        loader = getattr(self._market_data, "list_instruments", None)
        if not callable(loader):
            raise NotImplementedError(f"{self.name} 不支持标的目录同步")
        return loader()

    def connect(self) -> AdapterStatus:
        md_status = self._market_data.connect()
        tr_status = self._trading.connect()
        self._connected = bool(
            md_status.get("connected", False)
            and getattr(tr_status, "connected", False)
        )
        return AdapterStatus(
            connected=self._connected,
            account_no=getattr(tr_status, "account_no", None),
            latency_ms=md_status.get("latency_ms"),
        )

    def disconnect(self) -> None:
        self._market_data.disconnect()
        self._trading.disconnect()
        self._connected = False

    def get_account(self) -> AccountSnapshot:
        return self._trading.get_account()

    def get_positions(self) -> list[PositionSnapshot]:
        return self._trading.get_positions()

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        return self._market_data.get_quote(symbol)

    def get_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]:
        return self._market_data.get_kline(symbol, interval, start, end)

    def subscribe_quotes(self, symbols: list[str]) -> None:
        self._market_data.subscribe_quotes(symbols)

    def unsubscribe_quotes(self, symbols: list[str]) -> None:
        self._market_data.unsubscribe_quotes(symbols)

    def query_orders(self, filters: OrderQuery | dict | None = None) -> list[OrderSnapshot]:
        return self._trading.query_orders(filters)

    def query_trades(self, filters: TradeQuery | dict | None = None) -> list[TradeSnapshot]:
        return self._trading.query_trades(filters)

    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        return self._trading.place_order(request)

    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult:
        return self._trading.cancel_order(request)
