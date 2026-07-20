from typing import Callable

from app.schemas.enums import Market
from app.sdk.base import SDKNotConfigured


class NativeThsDriver:
    """同花顺原生驱动：SDK 文档到位后在 `_load_sdk` 中加载 DLL/COM 并实现真实调用。

    集成步骤（见 doc/sdk-notes-stock.md / sdk-notes-futures.md §接入清单）：
    1. 填写 sdk-notes 中 TBD 项（版本、授权、字段枚举）
    2. 实现 `_load_sdk()` 加载 DLL/COM
    3. 逐方法替换 `_raise()` 为真实 SDK 调用
    4. 更新 `mapping.py` 中 THS_ORDER_STATUS_MAP
    5. 运行 sdk_smoke_query → sdk_small_order_cancel 小额验收
    """

    PLACEHOLDER_MSG = "原生同花顺驱动待 SDK 文档填充，请配置 LIANGHUA_SDK_DRIVER=sim 进行映射验收"

    def __init__(self, *, market: Market, config: dict):
        self.market = market
        self.config = config
        path_key = "stock_sdk_path" if market == Market.STOCK else "futures_sdk_path"
        self.sdk_path = (config.get(path_key) or "").strip()
        self._sdk_handle = None
        self._order_cb: Callable[[dict], None] | None = None
        self._trade_cb: Callable[[dict], None] | None = None
        self._quote_cb: Callable[[dict], None] | None = None
        self._connection_cb: Callable[[dict], None] | None = None

    def _load_sdk(self) -> None:
        """加载同花顺 SDK（DLL/COM）。SDK 文档到位后在此实现。"""
        if not self.sdk_path:
            raise SDKNotConfigured(f"未配置 {self.market.value} SDK 路径")
        # TODO: load DLL/COM from self.sdk_path when SDK docs are available
        # Example integration points (do NOT implement without official docs):
        #   - ctypes.CDLL(self.sdk_path) for DLL
        #   - win32com.client.Dispatch(...) for COM
        # self._sdk_handle = ...
        raise SDKNotConfigured(self.PLACEHOLDER_MSG)

    def _ensure_loaded(self) -> None:
        if self._sdk_handle is None:
            self._load_sdk()

    def _raise(self):
        self._ensure_loaded()
        raise SDKNotConfigured(self.PLACEHOLDER_MSG)

    def connect(self) -> dict:
        self._raise()

    def disconnect(self) -> None:
        self._sdk_handle = None
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
        self._order_cb = cb

    def set_trade_callback(self, cb: Callable[[dict], None] | None) -> None:
        self._trade_cb = cb

    def set_quote_callback(self, cb: Callable[[dict], None] | None) -> None:
        self._quote_cb = cb

    def set_connection_callback(self, cb: Callable[[dict], None] | None) -> None:
        self._connection_cb = cb
