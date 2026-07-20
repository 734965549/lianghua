from typing import Callable

from app.schemas.enums import Market
from app.sdk.base import SDKNotConfigured


class UnconfiguredDriver:
    """SDK 路径或账号未配置时使用的占位驱动。"""

    def __init__(self, *, market: Market, config: dict):
        self.market = market
        self.config = config
        self._msg = self._build_message()

    def _build_message(self) -> str:
        path_key = "stock_sdk_path" if self.market == Market.STOCK else "futures_sdk_path"
        acct_key = "stock_account" if self.market == Market.STOCK else "futures_account"
        path = (self.config.get(path_key) or "").strip()
        account = (self.config.get(acct_key) or "").strip()
        missing = []
        if not path:
            missing.append(path_key)
        if not account:
            missing.append(acct_key)
        return f"同花顺 {self.market.value} SDK 未配置: {', '.join(missing) or '未知'}"

    def _raise(self):
        raise SDKNotConfigured(self._msg)

    def connect(self) -> dict:
        self._raise()

    def disconnect(self) -> None:
        return None

    def get_account(self) -> dict:
        self._raise()

    def get_positions(self) -> list[dict]:
        self._raise()

    def get_quote(self, symbol: str) -> dict:
        self._raise()

    def get_kline(self, symbol: str, interval: str, start, end) -> list[dict]:
        self._raise()

    def subscribe_quotes(self, symbols: list[str]) -> None:
        self._raise()

    def query_orders(self, filters: dict) -> list[dict]:
        self._raise()

    def query_trades(self, filters: dict) -> list[dict]:
        self._raise()

    def place_order(self, payload: dict) -> dict:
        self._raise()

    def cancel_order(self, payload: dict) -> dict:
        self._raise()

    def set_order_callback(self, cb: Callable[[dict], None] | None) -> None:
        return None

    def set_trade_callback(self, cb: Callable[[dict], None] | None) -> None:
        return None

    def set_quote_callback(self, cb: Callable[[dict], None] | None) -> None:
        return None

    def set_connection_callback(self, cb: Callable[[dict], None] | None) -> None:
        return None
