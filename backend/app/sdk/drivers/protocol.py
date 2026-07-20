"""同花顺原生驱动协议：返回 SDK 原始 dict，由适配层做字段映射。"""

from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class ThsNativeDriver(Protocol):
    """同花顺 SDK 原生驱动接口（原始字段，非标准模型）。"""

    market: str

    def connect(self) -> dict:
        """返回 {"connected": bool, "AcctNo": str, "latency_ms": int, ...}"""
        ...

    def disconnect(self) -> None:
        ...

    def get_account(self) -> dict:
        ...

    def get_positions(self) -> list[dict]:
        ...

    def get_quote(self, symbol: str) -> dict:
        ...

    def get_kline(self, symbol: str, interval: str, start, end) -> list[dict]:
        ...

    def subscribe_quotes(self, symbols: list[str]) -> None:
        ...

    def query_orders(self, filters: dict) -> list[dict]:
        ...

    def query_trades(self, filters: dict) -> list[dict]:
        ...

    def place_order(self, payload: dict) -> dict:
        ...

    def cancel_order(self, payload: dict) -> dict:
        ...

    def set_order_callback(self, cb: Callable[[dict], None] | None) -> None:
        ...

    def set_trade_callback(self, cb: Callable[[dict], None] | None) -> None:
        ...

    def set_quote_callback(self, cb: Callable[[dict], None] | None) -> None:
        ...

    def set_connection_callback(self, cb: Callable[[dict], None] | None) -> None:
        ...
