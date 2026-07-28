# AKShare 行情接入与模拟交易说明

> 阶段目标：接入 AKShare 获取 A 股真实实时行情，行情落地后驱动程序内部的模拟撮合（不接实盘）。实盘交易留待后续 QMT/同花顺阶段。

## 背景与定位

当前 SDK 适配层（`backend/app/sdk/`）以同花顺为唯一真实数据源，行情与交易耦合在同一个 `ThsTradingAdapterBase` 中。AKShare 是完全免费、无需注册、pip 直装的 Python 金融数据接口库，覆盖 A 股/港股/美股/期货/宏观，底层是公开数据源的爬虫聚合，多数接口准实时（1~3 秒延迟）。

本次接入只解决「行情」一端：真实行情从 AKShare 拉取，交易仍走程序内模拟撮合。这样既能看到真实价格驱动的前端盘口和 K 线，又能验证下单→风控→撮合→成交→持仓→资产的全链路，且不触及真实资金。

## 为什么选 AKShare

| 维度 | AKShare | Tushare Pro | BaoStock |
| --- | --- | --- | --- |
| 费用 | 完全免费、无需注册 | 积分制，高级接口要积分 | 免费、需注册登录 |
| 实时行情 | 有（准实时 1~3s） | 基础有，高级受限 | 无实时 |
| 历史数据 | 可达 20 年 | 通常 5 年 | 完整 |
| 安装 | `pip install akshare` | 需 token | 需登录 |
| 稳定性 | 依赖源站，偶有波动 | 曾突发停运 | 稳定 |
| 适合角色 | **主行情源** | 交叉验证 | 补历史 |

结论：AKShare 做主行情源，BaoStock 补历史，Tushare 做交叉验证，是社区公认的免费组合。本次只接 AKShare，后续按需扩展。

## 现有架构与接入点

适配层结构（接入 AKShare 不需要改动业务层）：

```
backend/app/sdk/
├── base.py                 # TradingAdapter 抽象基类 + 错误体系
├── models.py               # 标准模型（QuoteSnapshot/KlineBar/PlaceOrderRequest...）
├── factory.py              # 按 mode/market 分发适配器  ← 需扩展
├── manager.py              # 适配器单例 + 健康检查      ← 需扩展配置
├── mapping.py              # THS 字段映射
├── mock_adapter.py         # 纯模拟适配器（行情+交易都假）
├── ths_adapter_base.py     # 同花顺真实适配器基类
├── stock_adapter.py        # 同花顺股票适配器
├── futures_adapter.py      # 同花顺期货适配器
└── drivers/
    ├── protocol.py         # ThsNativeDriver 协议
    ├── simulated.py        # 同花顺模拟驱动
    ├── native.py           # 同花顺原生驱动占位
    └── unconfigured.py     # 未配置驱动
```

关键约束：

- `TradingAdapter` 是统一抽象基类，所有数据源都要实现它。
- `factory.py` 按 `sdk_mode`（mock/real）和 `market`（stock/futures）分发。
- `manager.py` 持有单例，配置来自 `core/config.py` 的 `Settings`。
- 标准模型用 `Decimal`，禁止 float 参与金额和数量计算。

## 设计思路：行情与交易解耦

AKShare 只提供行情，没有交易能力。引入一个新的适配器 `AkshareAdapter`，它：

- 行情方法（`get_quote` / `get_kline` / `subscribe_quotes`）调用 AKShare 真实接口。
- 交易方法（`place_order` / `cancel_order` / `query_orders` / `query_trades`）复用 `MockTradingAdapter` 的撮合逻辑，但成交价不写死 10.05，而是用 AKShare 拉到的真实最新价。
- 账户/持仓（`get_account` / `get_positions`）返回模拟值，持仓随模拟成交更新。

这样前端看到的盘口、K 线是真实的，下单后按真实价格模拟撮合，整条链路（行情→信号→风控→下单→撮合→成交→持仓→资产）都能跑通，且不动真实资金。

### 适配器组合示意

```
              ┌─────────────────────────────────────────┐
              │           TradingAdapter                │
              │        (统一抽象基类)                    │
              └──────────────┬──────────────────────────┘
                             │
        ┌────────────────────┼────────────────────────┐
        │                    │                        │
┌───────▼────────┐  ┌────────▼─────────┐  ┌──────────▼──────────┐
│ MockTrading    │  │ AkshareAdapter   │  │ ThsTradingAdapter   │
│ Adapter        │  │ (本次新增)        │  │ (实盘阶段再用)       │
│ 行情=假 交易=假 │  │ 行情=真 交易=模拟 │  │ 行情=真 交易=真     │
└────────────────┘  └──────────────────┘  └─────────────────────┘
```

## AKShare 关键接口

实时行情（本次主要用到的）：

| 接口 | 用途 | 返回要点 |
| --- | --- | --- |
| `ak.stock_zh_a_spot_em()` | 沪深京 A 股实时行情快照 | 代码、名称、最新价、涨跌幅、涨跌额、成交量、成交额、换手率、市盈率等 |
| `ak.stock_zh_a_hist(symbol, period, start, end)` | 个股历史 K 线 | 日期、开盘、收盘、最高、最低、成交量、成交额 |
| `ak.stock_individual_info_em(symbol)` | 个股基本信息 | 总市值、流通市值、行业等 |

返回均为 pandas DataFrame。适配器内部将其转换为标准模型 `QuoteSnapshot` / `KlineBar`。

注意：AKShare 接口名偶有变动（`stock_zh_a_spot` 与 `stock_zh_a_spot_em` 并存），实现时以本机安装版本的官方文档为准，建议做接口存在性检查并保留降级。

## 实施步骤

### 第一步：安装依赖

在 `backend/` 下：

```powershell
.\.venv\Scripts\pip.exe install akshare pandas
```

在 `backend/requirements.txt` 追加：

```text
akshare>=1.12.0
pandas>=2.0.0
```

版本号以安装时最新稳定版为准。

### 第二步：扩展配置

在 `backend/app/core/config.py` 的 `Settings` 中新增：

```python
# 行情源
quote_provider: str = "mock"  # mock / akshare / ths
akshare_poll_seconds: float = 2.0  # AKShare 行情轮询间隔
```

在 `backend/.env.example` 追加示例：

```env
LIANGHUA_QUOTE_PROVIDER=akshare
LIANGHUA_AKSHARE_POLL_SECONDS=2.0
```

### 第三步：新建 AkshareAdapter

新建 `backend/app/sdk/akshare_adapter.py`。核心结构（不是最终代码，实现时按真实接口字段补全）：

```python
"""AKShare 行情适配器：真实行情 + 程序内模拟撮合。"""

import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

import akshare as ak

from app.schemas.enums import Market, OrderSide, OrderStatus
from app.sdk.base import SDKDisconnected, TradingAdapter
from app.sdk.models import (
    AccountSnapshot, AdapterStatus, CancelOrderRequest, CancelOrderResult,
    ConnectionEvent, KlineBar, OrderQuery, OrderSnapshot, OrderUpdateEvent,
    PlaceOrderRequest, PlaceOrderResult, QuoteSnapshot, TradeQuery,
    TradeSnapshot, TradeUpdateEvent,
)


class AkshareAdapter(TradingAdapter):
    """真实行情（AKShare）+ 模拟撮合。"""

    market = Market.STOCK

    def __init__(self, *, market: Market = Market.STOCK, config: dict | None = None):
        super().__init__()
        self.market = market
        self.config = config or {}
        self._connected = False
        self._subscribed: set[str] = set()
        self._latest_quotes: dict[str, QuoteSnapshot] = {}
        self._orders: dict[str, dict] = {}
        self._trades: list[TradeSnapshot] = []
        self._quote_thread: threading.Thread | None = None
        self._quote_stop = threading.Event()
        self._poll_seconds = float(self.config.get("akshare_poll_seconds", 2.0))
        self._lock = threading.Lock()

    # ---- 生命周期 ----
    def connect(self) -> AdapterStatus:
        self._connected = True
        # 连接时拉一次全市场快照，建立 _latest_quotes 缓存
        self._refresh_spot_snapshot()
        if self._on_connection_change:
            self._on_connection_change(
                ConnectionEvent(market=self.market, connected=True,
                                event_time=datetime.now(timezone.utc)))
        return AdapterStatus(connected=True, account_no="AKSHARE_SIM",
                             latency_ms=int(self._poll_seconds * 1000))

    def disconnect(self) -> None:
        self._quote_stop.set()
        if self._quote_thread and self._quote_thread.is_alive():
            self._quote_thread.join(timeout=2.0)
        self._connected = False

    # ---- 行情（真实）----
    def _refresh_spot_snapshot(self) -> None:
        """拉取全市场实时快照，更新 _latest_quotes 缓存。"""
        try:
            df = ak.stock_zh_a_spot_em()
        except Exception:
            return  # 源站波动时保留旧缓存
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).strip()
            if not code:
                continue
            symbol = self._normalize_symbol(code)
            self._latest_quotes[symbol] = QuoteSnapshot(
                symbol=symbol, market=self.market,
                last_price=Decimal(str(row.get("最新价", "0") or "0")),
                change_rate=Decimal(str(row.get("涨跌幅", "0") or "0")),
                volume=Decimal(str(row.get("成交量", "0") or "0")),
                quote_time=datetime.now(timezone.utc),
            )

    @staticmethod
    def _normalize_symbol(code: str) -> str:
        """6 位代码 -> 带后缀标准代码，如 600000 -> 600000.SH。"""
        if "." in code:
            return code
        if code.startswith(("60", "68", "11", "13")):
            return f"{code}.SH"
        return f"{code}.SZ"

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        self._ensure_connected()
        with self._lock:
            if symbol in self._latest_quotes:
                return self._latest_quotes[symbol]
        # 缓存未命中时单点查询（按需补）
        raise SDKDisconnected(f"AKShare 暂无 {symbol} 快照")

    def get_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]:
        self._ensure_connected()
        period = {"1m": "1", "5m": "5", "1d": "daily"}.get(interval, "daily")
        bare = symbol.split(".")[0]
        df = ak.stock_zh_a_hist(symbol=bare, period=period,
                                start=start.strftime("%Y%m%d"),
                                end=end.strftime("%Y%m%d"))
        bars = []
        for _, row in df.iterrows():
            bars.append(KlineBar(
                symbol=symbol, market=self.market, interval=interval,
                bar_time=datetime.strptime(str(row["日期"]), "%Y-%m-%d"),
                open=Decimal(str(row["开盘"])), high=Decimal(str(row["最高"])),
                low=Decimal(str(row["最低"])), close=Decimal(str(row["收盘"])),
                volume=Decimal(str(row["成交量"])),
            ))
        return bars

    def subscribe_quotes(self, symbols: list[str]) -> None:
        self._ensure_connected()
        with self._lock:
            self._subscribed.update(symbols)
        if self._quote_thread is None or not self._quote_thread.is_alive():
            self._quote_stop.clear()
            self._quote_thread = threading.Thread(target=self._quote_loop, daemon=True)
            self._quote_thread.start()

    def _quote_loop(self) -> None:
        while not self._quote_stop.is_set() and self._connected:
            self._refresh_spot_snapshot()
            with self._lock:
                snaps = [self._latest_quotes[s] for s in self._subscribed
                         if s in self._latest_quotes]
            for snap in snaps:
                if self._on_quote_update:
                    self._on_quote_update(snap)
            time.sleep(self._poll_seconds)

    # ---- 账户/持仓（模拟）----
    def get_account(self) -> AccountSnapshot:
        self._ensure_connected()
        return AccountSnapshot(
            account_id=uuid4(), account_no="AKSHARE_SIM",
            total_asset=Decimal("1000000"), available_cash=Decimal("1000000"),
            frozen_cash=Decimal("0"), market_value=Decimal("0"),
            pnl=Decimal("0"), snapshot_time=datetime.now(timezone.utc))

    def get_positions(self) -> list:
        return []  # 随模拟成交更新

    # ---- 交易（模拟撮合，用真实价）----
    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        self._ensure_connected()
        snap = self.get_quote(request.symbol)
        fill_price = snap.last_price  # 用真实最新价撮合
        # 复用 Mock 的订单/成交管理 + _simulate_fill
        # （实现时从 mock_adapter.py 搬运 _simulate_fill / _emit_trade / _emit_order_update，
        #   并把写死的 10.05 换成 fill_price）
        ...

    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult:
        # 同 Mock
        ...

    def query_orders(self, filters=None) -> list[OrderSnapshot]:
        # 同 Mock
        ...

    def query_trades(self, filters=None) -> list[TradeSnapshot]:
        # 同 Mock
        ...

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise SDKDisconnected("AKShare 适配器未连接")
```

实现要点：

- `_simulate_fill` / `_emit_trade` / `_emit_order_update` / 订单与成交的内存管理，直接从 `mock_adapter.py` 搬运，只把成交价从写死的 `10.05` 改为 `get_quote(symbol).last_price`。
- `subscribe_quotes` 的轮询间隔由 `akshare_poll_seconds` 控制，默认 2 秒，避免高频请求被源站限流。
- AKShare 返回 6 位代码，需在 `_normalize_symbol` 里转成项目标准的 `600000.SH` 格式。
- 所有数值用 `Decimal`，DataFrame 取值用 `str()` 包一层再转 `Decimal`，避免 float 精度问题。
- AKShare 接口偶发异常时 `try/except` 保留旧缓存，不中断行情推送线程。

### 第四步：工厂分发

修改 `backend/app/sdk/factory.py`：

```python
def get_adapter(market: str | Market, config: dict) -> TradingAdapter:
    if isinstance(market, str):
        market = Market(market)
    mode = config.get("mode", "mock")
    quote_provider = config.get("quote_provider", "mock")

    # 行情源 = akshare 时，用 AkshareAdapter（行情真 + 交易模拟）
    if quote_provider == "akshare":
        from app.sdk.akshare_adapter import AkshareAdapter
        return AkshareAdapter(market=market, config=config)

    if mode == "mock":
        return MockTradingAdapter(market=market, config=config)
    if market == Market.STOCK and mode == "real":
        from app.sdk.stock_adapter import StockTradingAdapter
        return StockTradingAdapter(config=config)
    if market == Market.FUTURES and mode == "real":
        from app.sdk.futures_adapter import FuturesTradingAdapter
        return FuturesTradingAdapter(config=config)
    raise ValueError(f"不支持的适配器: market={market} mode={mode}")
```

### 第五步：manager 传参

修改 `backend/app/sdk/manager.py` 的 `_sdk_config()`，把新配置项带进去：

```python
def _sdk_config() -> dict:
    return {
        "mode": settings.sdk_mode,
        "sdk_driver": settings.sdk_driver,
        "quote_provider": settings.quote_provider,
        "akshare_poll_seconds": settings.akshare_poll_seconds,
        "stock_sdk_path": settings.stock_sdk_path,
        "futures_sdk_path": settings.futures_sdk_path,
        "stock_account": settings.stock_account,
        "futures_account": settings.futures_account,
    }
```

### 第六步：验证

先做单点探活（不依赖后端服务），新建 `backend/scripts/akshare_smoke.py`：

```python
"""AKShare 行情探活：拉一次快照 + 查询指定标的。"""
import akshare as ak

df = ak.stock_zh_a_spot_em()
print(f"快照行数: {len(df)}")
print(df.columns.tolist())
print(df.head(3))

# 单标的 K 线
k = ak.stock_zh_a_hist(symbol="600000", period="daily",
                       start="20260101", end="20260727")
print(k.tail(3))
```

运行：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\akshare_smoke.py
```

确认能拉到数据后，启动后端并配置 `.env`：

```env
LIANGHUA_SDK_MODE=mock
LIANGHUA_QUOTE_PROVIDER=akshare
LIANGHUA_AKSHARE_POLL_SECONDS=2.0
```

启动后端，在前端行情页订阅 `600000.SH`，应看到真实最新价；在交易页下一笔限价单，应看到按真实价模拟成交的订单/成交回报和持仓变化。

## 下一步做什么

按依赖顺序，下一步该做的事：

1. **装依赖**：`pip install akshare pandas`，更新 `requirements.txt`。先跑通 `akshare_smoke.py`，确认本机能拉到 A 股实时快照和 K 线。
2. **加配置**：在 `config.py` 加 `quote_provider` / `akshare_poll_seconds`，在 `.env.example` 补示例。
3. **写适配器**：新建 `akshare_adapter.py`，行情方法接 AKShare，交易方法从 `mock_adapter.py` 搬运撮合逻辑并把成交价换成真实价。
4. **改工厂**：`factory.py` 按 `quote_provider=akshare` 分发到 `AkshareAdapter`；`manager.py` 的 `_sdk_config()` 补上新字段。
5. **联调验证**：启动后端，前端订阅真实标的看盘口，下一笔模拟单看撮合链路。
6. **加测试**：在 `backend/app/tests/sdk/` 加 `test_akshare_adapter.py`，至少覆盖：连接/断开、`get_quote` 返回真实价、`place_order` 按真实价模拟成交、订单/成交回调幂等。

做完这六步，就实现了「真实行情 + 模拟交易」的闭环。实盘交易（QMT 或同花顺）作为后续阶段，届时再写对应的 `QmtAdapter` 或补全 `ThsTradingAdapterBase` 的原生驱动。

## 风险与限制

- AKShare 底层是爬虫聚合，依赖源站可用性，高峰期可能限流或返回延迟。生产环境建议加缓存和重试，并预留 BaoStock/Tushare 作为降级源。
- AKShare 不提供交易能力，本阶段的「成交」是程序内模拟，成交价采用最新价快照，与真实盘口撮合存在差异，不能作为实盘依据。
- AKShare 接口名和返回字段会随版本调整，实现时以本机安装版本的实际接口为准，建议对关键接口做存在性检查。
