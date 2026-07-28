# 同花顺 SDK 适配层设计

## 设计目标

适配层负责隔离同花顺股票 SDK 和期货 SDK 的字段、调用方式、错误模型和回调差异。业务模块只能依赖统一接口和标准领域模型。

## 适配器类型

| 适配器 | 用途 |
| --- | --- |
| `MockTradingAdapter` | 无真实 SDK 时用于开发、测试和演示 |
| `StockTradingAdapter` | 同花顺股票 SDK |
| `FuturesTradingAdapter` | 同花顺期货 SDK |

Mock 适配器必须先实现，用于验证 API、风控、订单、前端和数据库链路。

## 统一接口

```python
class TradingAdapter:
    def connect(self) -> AdapterStatus: ...
    def disconnect(self) -> None: ...
    def get_account(self) -> AccountSnapshot: ...
    def get_positions(self) -> list[PositionSnapshot]: ...
    def subscribe_quotes(self, symbols: list[str]) -> None: ...
    def get_quote(self, symbol: str) -> QuoteSnapshot: ...
    def get_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]: ...
    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult: ...
    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult: ...
    def query_orders(self, filters: OrderQuery) -> list[OrderSnapshot]: ...
    def query_trades(self, filters: TradeQuery) -> list[TradeSnapshot]: ...
```

回调事件可由适配器注册：

```python
on_order_update(event: OrderUpdateEvent) -> None
on_trade_update(event: TradeUpdateEvent) -> None
on_quote_update(event: QuoteSnapshot) -> None
on_connection_change(event: ConnectionEvent) -> None
```

## 标准模型

### PlaceOrderRequest

| 字段 | 说明 |
| --- | --- |
| client_order_id | 本地幂等 ID |
| account_id | 账户 ID |
| market | `stock` 或 `futures` |
| symbol | 标的代码 |
| side | `buy` 或 `sell` |
| action | `open`、`close`、`reduce`、`increase` |
| price_type | `limit` 或 `market` |
| price | 委托价 |
| quantity | 委托数量 |
| metadata | 扩展参数，期货平今/平昨等差异字段可放入 |

### PlaceOrderResult

| 字段 | 说明 |
| --- | --- |
| success | 是否提交成功 |
| client_order_id | 本地幂等 ID |
| sdk_order_id | SDK 委托编号 |
| status | 标准订单状态 |
| message | SDK 返回说明 |
| raw_payload | SDK 原始返回 |

### OrderUpdateEvent

| 字段 | 说明 |
| --- | --- |
| client_order_id | 本地幂等 ID，可为空 |
| sdk_order_id | SDK 委托编号 |
| status | 标准订单状态 |
| filled_quantity | 已成交数量 |
| remaining_quantity | 剩余数量 |
| event_time | 事件时间 |
| raw_payload | SDK 原始事件 |

### TradeUpdateEvent

| 字段 | 说明 |
| --- | --- |
| sdk_trade_id | SDK 成交编号 |
| client_order_id | 本地幂等 ID，可为空 |
| sdk_order_id | SDK 委托编号 |
| symbol | 标的 |
| market | 市场 |
| side | 买卖 |
| price | 成交价 |
| quantity | 成交数量 |
| fee | 手续费 |
| trade_time | 成交时间 |
| raw_payload | SDK 原始事件 |

## 字段映射原则

1. 适配层必须把 SDK 返回字段转换为标准模型。
2. 标准模型字段不足时，先放入 `metadata` 或 `raw_payload`，不要把 SDK 字段扩散到服务层。
3. 期货特有字段如开平、平今、平昨、投机/套保标志必须通过 `action` 和 `metadata` 表达。
4. 股票买卖不需要开平仓语义时，`action` 可使用 `open` 或 `close` 映射业务含义。
5. 所有数值统一转为 decimal，禁止使用浮点数参与金额和数量计算。

## 错误标准化

| 标准错误 | 场景 |
| --- | --- |
| `SDK_NOT_CONFIGURED` | SDK 路径或账号未配置 |
| `SDK_CONNECTION_FAILED` | 连接失败 |
| `SDK_AUTH_FAILED` | 授权或登录失败 |
| `SDK_TIMEOUT` | 调用超时 |
| `SDK_RESPONSE_INVALID` | 返回字段缺失或类型异常 |
| `SDK_ORDER_REJECTED` | SDK 拒绝委托 |
| `SDK_CANCEL_REJECTED` | SDK 拒绝撤单 |
| `SDK_DISCONNECTED` | 连接中断 |

每个错误都要保留原始错误码、原始消息和调用上下文。

## 幂等与回调

1. `place_order` 必须携带 `client_order_id`。
2. 若 SDK 不支持透传本地 ID，需要在本地建立 `client_order_id` 到 `sdk_order_id` 的映射。
3. 回调中缺失 `client_order_id` 时，通过 `sdk_order_id` 回查本地订单。
4. 成交回调按 `sdk_trade_id` 幂等入库。
5. 回调和轮询结果可能重复，服务层必须接受重复事件。

## Mock SDK 行为

Mock 适配器应支持：

1. 模拟 SDK 连接成功、失败、断线、重连。
2. 模拟行情持续推送和行情停更。
3. 模拟限价委托提交成功、失败、部分成交、全部成交、撤单。
4. 模拟重复成交回报和未知订单状态。
5. 提供可配置延迟，用于测试前端实时更新和风控熔断。

## 实现顺序

1. 定义标准模型和基类。
2. 实现 Mock 适配器。
3. 接入订单、成交、行情、资金和持仓的 Mock 流。
4. 根据真实 SDK 文档实现股票适配器。
5. 根据真实 SDK 文档实现期货适配器。
6. 用同一套适配器测试用例验证三种适配器行为一致。

---

## 标准模型 Pydantic 骨架

> 放 `backend/app/sdk/models.py`。所有数值用 `Decimal`，禁止 float。

```python
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field


class Market(str, Enum):
    STOCK = "stock"
    FUTURES = "futures"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalAction(str, Enum):
    OPEN = "open"
    CLOSE = "close"
    REDUCE = "reduce"
    INCREASE = "increase"


class PriceType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(str, Enum):
    PENDING_RISK = "pending_risk"
    RISK_REJECTED = "risk_rejected"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"
    UNKNOWN = "unknown"


class AdapterStatus(BaseModel):
    connected: bool
    account_no: str | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class QuoteSnapshot(BaseModel):
    symbol: str
    market: Market
    last_price: Decimal
    change_rate: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    bid_volume: Decimal | None = None
    ask_volume: Decimal | None = None
    quote_time: datetime
    raw_payload: dict | None = None


class KlineBar(BaseModel):
    symbol: str
    market: Market
    interval: str
    bar_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")
    raw_payload: dict | None = None


class PositionSnapshot(BaseModel):
    account_id: UUID
    symbol: str
    market: Market
    direction: str = "net"  # long/short/net
    quantity: Decimal
    available_quantity: Decimal
    avg_cost: Decimal
    market_value: Decimal
    pnl: Decimal
    snapshot_time: datetime
    raw_payload: dict | None = None


class AccountSnapshot(BaseModel):
    account_id: UUID
    account_no: str
    total_asset: Decimal
    available_cash: Decimal
    frozen_cash: Decimal
    market_value: Decimal
    pnl: Decimal
    snapshot_time: datetime
    raw_payload: dict | None = None


class PlaceOrderRequest(BaseModel):
    client_order_id: str
    account_id: UUID
    market: Market
    symbol: str
    side: OrderSide
    action: SignalAction
    price_type: PriceType
    price: Decimal | None = None  # 市价可为空
    quantity: Decimal
    metadata: dict = Field(default_factory=dict)  # 期货平今/平昨等差异字段


class PlaceOrderResult(BaseModel):
    success: bool
    client_order_id: str
    sdk_order_id: str | None = None
    status: OrderStatus
    message: str = ""
    raw_payload: dict | None = None


class CancelOrderRequest(BaseModel):
    client_order_id: str
    sdk_order_id: str | None = None
    market: Market
    reason: str = ""


class CancelOrderResult(BaseModel):
    success: bool
    client_order_id: str
    sdk_order_id: str | None = None
    status: OrderStatus
    message: str = ""
    raw_payload: dict | None = None


class OrderUpdateEvent(BaseModel):
    client_order_id: str | None = None
    sdk_order_id: str | None = None
    status: OrderStatus
    filled_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = Decimal("0")
    event_time: datetime
    raw_payload: dict | None = None


class TradeUpdateEvent(BaseModel):
    sdk_trade_id: str
    client_order_id: str | None = None
    sdk_order_id: str | None = None
    symbol: str
    market: Market
    side: OrderSide
    price: Decimal
    quantity: Decimal
    fee: Decimal = Decimal("0")
    trade_time: datetime
    raw_payload: dict | None = None


class ConnectionEvent(BaseModel):
    market: Market
    connected: bool
    reason: str = ""
    event_time: datetime
```

## 适配器基类与错误体系

> 放 `backend/app/sdk/base.py`。

```python
from abc import ABC, abstractmethod
from typing import Callable
from .models import (
    AdapterStatus, QuoteSnapshot, KlineBar, PositionSnapshot, AccountSnapshot,
    PlaceOrderRequest, PlaceOrderResult, CancelOrderRequest, CancelOrderResult,
    OrderUpdateEvent, TradeUpdateEvent, ConnectionEvent, Market,
)


class AdapterError(Exception):
    """适配器标准错误基类。"""
    def __init__(self, code: str, message: str, *, raw_code: str | None = None,
                 raw_message: str | None = None, retryable: bool = False):
        self.code, self.message = code, message
        self.raw_code, self.raw_message = raw_code, raw_message
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


# 常用错误码（见上文 §错误标准化）
class SDKNotConfigured(AdapterError):
    def __init__(self, msg="SDK 未配置"):
        super().__init__("SDK_NOT_CONFIGURED", msg)

class SDKConnectionFailed(AdapterError):
    def __init__(self, msg="SDK 连接失败", **kw):
        super().__init__("SDK_CONNECTION_FAILED", msg, retryable=True, **kw)

class SDKAuthFailed(AdapterError):
    def __init__(self, msg="SDK 授权失败", **kw):
        super().__init__("SDK_AUTH_FAILED", msg, **kw)

class SDKTimeout(AdapterError):
    def __init__(self, msg="SDK 调用超时", **kw):
        super().__init__("SDK_TIMEOUT", msg, retryable=True, **kw)

class SDKResponseInvalid(AdapterError):
    def __init__(self, msg="SDK 返回字段异常", **kw):
        super().__init__("SDK_RESPONSE_INVALID", msg, **kw)

class SDKOrderRejected(AdapterError):
    def __init__(self, msg="SDK 拒绝委托", **kw):
        super().__init__("SDK_ORDER_REJECTED", msg, **kw)

class SDKDisconnected(AdapterError):
    def __init__(self, msg="SDK 连接中断", **kw):
        super().__init__("SDK_DISCONNECTED", msg, retryable=True, **kw)


class TradingAdapter(ABC):
    """适配器抽象基类。子类实现所有 abstractmethod。"""

    market: Market  # 子类声明

    def __init__(self):
        self._on_order_update: Callable[[OrderUpdateEvent], None] | None = None
        self._on_trade_update: Callable[[TradeUpdateEvent], None] | None = None
        self._on_quote_update: Callable[[QuoteSnapshot], None] | None = None
        self._on_connection_change: Callable[[ConnectionEvent], None] | None = None

    # ---- 回调注册 ----
    def on_order_update(self, cb): self._on_order_update = cb
    def on_trade_update(self, cb): self._on_trade_update = cb
    def on_quote_update(self, cb): self._on_quote_update = cb
    def on_connection_change(self, cb): self._on_connection_change = cb

    # ---- 生命周期 ----
    @abstractmethod
    def connect(self) -> AdapterStatus: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    # ---- 查询 ----
    @abstractmethod
    def get_account(self) -> AccountSnapshot: ...

    @abstractmethod
    def get_positions(self) -> list[PositionSnapshot]: ...

    @abstractmethod
    def get_quote(self, symbol: str) -> QuoteSnapshot: ...

    @abstractmethod
    def get_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]: ...

    @abstractmethod
    def subscribe_quotes(self, symbols: list[str]) -> None: ...

    @abstractmethod
    def query_orders(self, filters: dict) -> list[dict]: ...

    @abstractmethod
    def query_trades(self, filters: dict) -> list[dict]: ...

    # ---- 交易 ----
    @abstractmethod
    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult: ...

    @abstractmethod
    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult: ...
```

## Mock 适配器骨架

> 放 `backend/app/sdk/mock_adapter.py`。关键点：所有行为可配置、可注入异常、可控制延迟，用于测试风控熔断和前端实时更新。
>
> **实现说明（2026-07）：** 因适配器对外 API 为同步调用，行情推送与成交模拟采用 `threading.Thread` + `sleep`，与下方 asyncio 骨架**功能等价**；不强制改为 asyncio Task。

```python
import asyncio
import random
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from .base import TradingAdapter, SDKDisconnected, SDKOrderRejected
from .models import *


class MockTradingAdapter(TradingAdapter):
    market = Market.STOCK  # Mock 可同时模拟两个市场，实例化时传入

    def __init__(self, *, config: dict | None = None):
        super().__init__()
        self.config = config or {}
        self._connected = False
        self._subscribed: set[str] = set()
        self._orders: dict[str, dict] = {}        # client_order_id -> 内部订单
        self._sdk_order_map: dict[str, str] = {}  # sdk_order_id -> client_order_id
        self._trades_seen: set[str] = set()       # 已生成的 sdk_trade_id
        self._quote_task: asyncio.Task | None = None
        self._inject_fail = False                 # 下次下单强制失败
        self._inject_disconnect = False
        self._latency_ms = self.config.get("latency_ms", 50)

    # ---- 生命周期 ----
    def connect(self) -> AdapterStatus:
        if self._inject_disconnect:
            raise SDKDisconnected("Mock 注入断线")
        self._connected = True
        return AdapterStatus(connected=True, account_no="MOCK001", latency_ms=self._latency_ms)

    def disconnect(self) -> None:
        self._connected = False
        if self._quote_task:
            self._quote_task.cancel()

    # ---- 行情 ----
    def subscribe_quotes(self, symbols: list[str]) -> None:
        self._subscribed.update(symbols)
        if not self._quote_task:
            self._quote_task = asyncio.create_task(self._quote_loop())

    async def _quote_loop(self):
        """每 200ms 推送一次行情，价格随机波动。"""
        base_prices = {s: Decimal("10.00") for s in self._subscribed}
        while self._connected:
            for s in self._subscribed:
                base_prices[s] += Decimal(str(random.uniform(-0.05, 0.05)))
                snap = QuoteSnapshot(
                    symbol=s, market=self.market, last_price=base_prices[s],
                    quote_time=datetime.now(timezone.utc),
                )
                if self._on_quote_update:
                    self._on_quote_update(snap)
            await asyncio.sleep(0.2)

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        return QuoteSnapshot(symbol=symbol, market=self.market,
                             last_price=Decimal("10.00"),
                             quote_time=datetime.now(timezone.utc))

    def get_kline(self, symbol, interval, start, end) -> list[KlineBar]:
        # 生成模拟 K 线
        bars = []
        t = start
        step = {"1m": timedelta(minutes=1), "5m": timedelta(minutes=5),
                "1d": timedelta(days=1)}[interval]
        price = Decimal("10.00")
        while t < end:
            bars.append(KlineBar(symbol=symbol, market=self.market, interval=interval,
                                 bar_time=t, open=price, high=price+Decimal("0.1"),
                                 low=price-Decimal("0.1"), close=price,
                                 volume=Decimal("10000")))
            t += step
        return bars

    # ---- 账户与持仓 ----
    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(account_id=uuid4(), account_no="MOCK001",
                               total_asset=Decimal("1000000"), available_cash=Decimal("800000"),
                               frozen_cash=Decimal("50000"), market_value=Decimal("150000"),
                               pnl=Decimal("0"), snapshot_time=datetime.now(timezone.utc))

    def get_positions(self) -> list[PositionSnapshot]:
        return []

    # ---- 交易 ----
    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        if not self._connected:
            raise SDKDisconnected("Mock 未连接")
        if self._inject_fail:
            self._inject_fail = False
            raise SDKOrderRejected("Mock 注入下单失败")

        sdk_order_id = f"MOCK_{int(time.time()*1000)}_{random.randint(100,999)}"
        self._orders[request.client_order_id] = {
            "sdk_order_id": sdk_order_id, "status": OrderStatus.SUBMITTED,
            "filled": Decimal("0"), "remaining": request.quantity,
        }
        self._sdk_order_map[sdk_order_id] = request.client_order_id

        # 异步触发成交（部分成交 + 全部成交）
        asyncio.create_task(self._simulate_fill(request.client_order_id, sdk_order_id, request.quantity))

        return PlaceOrderResult(success=True, client_order_id=request.client_order_id,
                                sdk_order_id=sdk_order_id, status=OrderStatus.SUBMITTED,
                                message="Mock 接受委托")

    async def _simulate_fill(self, client_order_id, sdk_order_id, quantity):
        """模拟 200ms 后部分成交 50%，再 200ms 后全部成交。"""
        await asyncio.sleep(0.2)
        partial = (quantity * Decimal("0.5")).quantize(Decimal("1"))
        self._emit_trade(sdk_order_id, client_order_id, partial, Decimal("10.05"))
        self._emit_order_update(client_order_id, sdk_order_id, OrderStatus.PARTIALLY_FILLED, partial)
        await asyncio.sleep(0.2)
        rest = quantity - partial
        self._emit_trade(sdk_order_id, client_order_id, rest, Decimal("10.06"))
        self._emit_order_update(client_order_id, sdk_order_id, OrderStatus.FILLED, quantity)

    def _emit_trade(self, sdk_order_id, client_order_id, qty, price):
        sdk_trade_id = f"MOCKT_{int(time.time()*1000)}_{random.randint(1000,9999)}"
        if sdk_trade_id in self._trades_seen:
            return  # 幂等
        self._trades_seen.add(sdk_trade_id)
        if self._on_trade_update:
            self._on_trade_update(TradeUpdateEvent(
                sdk_trade_id=sdk_trade_id, client_order_id=client_order_id,
                sdk_order_id=sdk_order_id, symbol="MOCK", market=self.market,
                side=OrderSide.BUY, price=price, quantity=qty,
                trade_time=datetime.now(timezone.utc)))

    def _emit_order_update(self, client_order_id, sdk_order_id, status, filled):
        if self._on_order_update:
            self._on_order_update(OrderUpdateEvent(
                client_order_id=client_order_id, sdk_order_id=sdk_order_id,
                status=status, filled_quantity=filled,
                remaining_quantity=Decimal("0"), event_time=datetime.now(timezone.utc)))

    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult:
        order = self._orders.get(request.client_order_id)
        if not order:
            raise SDKOrderRejected(f"Mock 未找到订单 {request.client_order_id}")
        order["status"] = OrderStatus.CANCELLED
        return CancelOrderResult(success=True, client_order_id=request.client_order_id,
                                 sdk_order_id=request.sdk_order_id, status=OrderStatus.CANCELLED)

    def query_orders(self, filters: dict) -> list[dict]:
        return list(self._orders.values())

    def query_trades(self, filters: dict) -> list[dict]:
        return []

    # ---- 测试辅助：注入异常 ----
    def inject_next_order_fail(self): self._inject_fail = True
    def inject_disconnect(self): self._inject_disconnect = True; self._connected = False
```

## 适配器工厂

> 放 `backend/app/sdk/factory.py`。根据配置返回 Mock / 真实适配器实例。

```python
from .base import TradingAdapter
from .mock_adapter import MockTradingAdapter


def get_adapter(market: str, config: dict) -> TradingAdapter:
    """根据配置返回适配器。MVP 默认返回 Mock。"""
    mode = config.get("mode", "mock")
    if mode == "mock":
        return MockTradingAdapter(config=config)
    if market == "stock" and mode == "real":
        from .stock_adapter import StockTradingAdapter
        return StockTradingAdapter(config=config)
    if market == "futures" and mode == "real":
        from .futures_adapter import FuturesTradingAdapter
        return FuturesTradingAdapter(config=config)
    raise ValueError(f"不支持的适配器: market={market} mode={mode}")
```

## 适配器测试用例骨架

> 放 `backend/app/tests/sdk/test_adapter_contract.py`。Mock/股票/期货三种适配器跑同一套契约测试。

```python
import pytest
from app.sdk.mock_adapter import MockTradingAdapter
from app.sdk.models import *

@pytest.fixture
def adapter():
    a = MockTradingAdapter()
    a.connect()
    yield a
    a.disconnect()

def test_place_and_fill(adapter):
    """下单后能收到部分成交和全部成交回调。"""
    events = []
    adapter.on_order_update(lambda e: events.append(("order", e)))
    adapter.on_trade_update(lambda e: events.append(("trade", e)))

    req = PlaceOrderRequest(client_order_id="test_1", account_id=None,
                            market=Market.STOCK, symbol="MOCK", side=OrderSide.BUY,
                            action=SignalAction.OPEN, price_type=PriceType.LIMIT,
                            price=Decimal("10"), quantity=Decimal("100"))
    result = adapter.place_order(req)
    assert result.success

    import time; time.sleep(0.6)  # 等待异步成交
    statuses = [e[1].status for e in events if e[0] == "order"]
    assert OrderStatus.PARTIALLY_FILLED in statuses
    assert OrderStatus.FILLED in statuses
    trades = [e[1] for e in events if e[0] == "trade"]
    assert len(trades) == 2
    assert sum(t.quantity for t in trades) == Decimal("100")

def test_duplicate_trade_idempotent(adapter):
    """重复成交回报不重复入库（在 trade_service 层用 sdk_trade_id 幂等）。"""
    # 见 testing-acceptance.md 集成测试
    pass

def test_injected_disconnect_raises(adapter):
    adapter.inject_disconnect()
    with pytest.raises(SDKDisconnected):
        adapter.connect()
```
