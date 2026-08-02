from abc import ABC, abstractmethod
from datetime import datetime
from typing import Callable

from app.schemas.enums import Market
from app.sdk.base import SDKAuthFailed, SDKNotConfigured, SDKTimeout
from app.sdk.models import KlineBar, QuoteSnapshot


class MarketDataAdapter(ABC):
    """行情数据适配器抽象基类，与交易适配器解耦。

    职责边界：
    - 只负责行情类数据（快照、K 线、订阅推送）。
    - 不处理账户、持仓、委托、成交等交易行为。
    """

    name: str = ""
    market: Market

    def __init__(self, *, market: Market, config: dict | None = None):
        self.market = market
        self.config = config or {}
        self._connected = False
        self._on_quote_update: Callable[[QuoteSnapshot], None] | None = None
        self._on_connection_change: Callable[[bool, str], None] | None = None

    def on_quote_update(self, cb: Callable[[QuoteSnapshot], None]) -> None:
        self._on_quote_update = cb

    def on_connection_change(self, cb: Callable[[bool, str], None]) -> None:
        self._on_connection_change = cb

    def _require_config(self, key: str) -> str:
        """读取必要配置；缺失时抛出 SDKNotConfigured。"""
        value = self.config.get(key)
        if not value:
            raise SDKNotConfigured(f"{self.name} 缺少配置项: {key}")
        return value

    @abstractmethod
    def connect(self) -> dict:
        """建立连接/鉴权，返回状态字典。"""

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接并释放资源。"""

    def is_connected(self) -> bool:
        return self._connected

    @abstractmethod
    def get_quote(self, symbol: str) -> QuoteSnapshot:
        """获取单个标的最新快照。"""

    @abstractmethod
    def get_kline(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[KlineBar]:
        """获取历史 K 线。"""

    @abstractmethod
    def subscribe_quotes(self, symbols: list[str]) -> None:
        """订阅实时行情；底层实现可轮询或推送。"""

    def unsubscribe_quotes(self, symbols: list[str]) -> None:
        """取消订阅，默认空实现。"""
        pass

    def _emit_quote(self, snap: QuoteSnapshot) -> None:
        if self._on_quote_update:
            self._on_quote_update(snap)

    def _emit_connection_change(self, connected: bool, reason: str = "") -> None:
        self._connected = connected
        if self._on_connection_change:
            self._on_connection_change(connected, reason)
