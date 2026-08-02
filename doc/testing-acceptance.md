# 测试与验收方案

## 测试目标

系统涉及真实资金交易，测试重点是风控、幂等、状态恢复和可追溯性。MVP 必须先通过 Mock SDK 的端到端测试，再接入真实 SDK。

## 测试分层

| 层级 | 范围 |
| --- | --- |
| 单元测试 | 风控规则、策略信号、指标计算、字段映射 |
| 集成测试 | API + 数据库、SDK 适配器、后台任务 |
| 端到端测试 | 前端 + 后端 + Mock SDK + PostgreSQL |
| 手工验收 | 真实 SDK 连接、实盘前人工确认、异常恢复 |

## 单元测试重点

1. 风控规则按配置正确通过或拒绝。
2. 金额、数量和价格使用 decimal 计算。
3. 策略参数校验失败时不能启动。
4. SDK 原始返回能正确映射为标准模型。
5. AI 指标计算与测试数据一致。

## 集成测试重点

1. `orders.client_order_id` 幂等约束生效。
2. 重复成交回报不会重复入库。
3. 风控拒绝不会调用 SDK `place_order`。
4. SDK 下单失败会更新订单状态并写审计日志。
5. 熔断状态下新委托全部拒绝。
6. 后端重启后恢复未完成订单和风控状态。

## 端到端验收场景

### 基础启动

1. 启动 PostgreSQL。
2. 启动后端。
3. 启动前端。
4. 前端访问健康检查。
5. 仪表盘显示 API、数据库和 Mock SDK 正常。

### 策略到订单

1. 启动 Mock 策略。
2. Mock 行情触发交易信号。
3. 策略信号落库。
4. 风控检查通过。
5. Mock SDK 接收下单请求。
6. 委托状态在前端实时更新。
7. 成交回报落库。

### 风控拒绝

1. 设置单笔金额上限。
2. 触发超过上限的策略信号。
3. 风控拒绝。
4. 前端显示拒绝原因。
5. 验证 SDK 未收到下单请求。
6. `risk_checks` 和 `audit_logs` 有记录。

### 一键停止

1. 点击一键停止。
2. 系统状态变为 `emergency_stopped`。
3. 新策略信号被拒绝。
4. 可选撤销未成交委托。
5. 前端显示紧急停止状态。
6. 用户手动恢复后才允许继续交易。

### SDK 异常

1. Mock SDK 模拟断线。
2. 系统记录异常并尝试重连。
3. 超过阈值后进入降级或熔断。
4. 新委托被拒绝。
5. 恢复连接后仍需人工确认恢复交易。

### 后端重启恢复

1. 创建一笔未完成订单。
2. 停止后端。
3. 重新启动后端。
4. 系统加载未完成订单。
5. 订单同步任务继续处理。
6. 熔断或紧急停止状态不被自动解除。

## 前端验收

1. 所有主要页面可访问。
2. 实时事件断线时有提示并降级轮询。
3. 表格支持筛选、排序和详情查看。
4. 危险操作有二次确认。
5. 错误信息对用户可理解。
6. 小屏和桌面宽屏不出现文本重叠。

## 文档验收

1. PRD、架构、API、数据库、风控、SDK、部署和测试文档齐全。
2. 文档中的接口、表名、状态枚举保持一致。
3. 未决问题集中记录在 `open-questions.md`。

## 上线前检查清单

> **Mock / 工程上线（阶段 8）** 与 **真实资金上线** 分开勾选。后者依赖原生同花顺 SDK。

| # | 检查项 | Mock/工程 | 真实 SDK |
| --- | --- | --- | --- |
| 1 | 数据库迁移已执行（含 `0006_ai_reports`） | 是 | 是 |
| 2 | SDK 连接测试通过 | mock / sim | 原生 |
| 3 | 风控白名单/限额可配置 | 是 | 是 |
| 4 | 交易时段规则可用 | 是（可深化日历） | 是 |
| 5 | 一键停止 / 熔断恢复可用 | 是 | 是 |
| 6 | unknown 订单有提示（专用确认 API 仍可增强） | 是 | 是 |
| 7 | 备份脚本可用 `backup_db.ps1` | 是 | 是 |
| 8 | 一键启停 `start.ps1` / `stop.ps1` | 是 | 是 |
| 9 | Mock/pytest 自动化通过（66+） | 是 | 是 |
| 10 | 真实 SDK 小额人工验证 | 待 SDK | 是 |
| 11 | AI 复盘可生成且无下单指令 | 是 | 是 |
| 12 | 历史交易筛选/CSV 导出 | 是 | 是 |
| 13 | AI 自然语言生成策略 definition 且校验通过 | 是（需配置 AI） | 可选 |
| 14 | 规则策略构建→发布→回测 | 是 | 是 |

脚本：

- `backend/scripts/sdk_smoke_query.py`（real+sim 查询）
- `backend/scripts/sdk_small_order_cancel.py`（sim 下单撤单）
- `backend/scripts/acceptance_smoke.py`（后端已启动时的只读/报告冒烟）
- `backend/scripts/backup_db.ps1`（库备份）

---

## 单元测试用例骨架

### 风控规则测试

> `backend/app/tests/services/test_risk_service.py`

```python
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from app.services.risk_rules import (
    SystemStateRule, SymbolBlacklistRule, OrderAmountRule,
    DailyLossRule, DuplicateSignalRule, RiskContext,
)
from app.sdk.models import PlaceOrderRequest, Market, OrderSide, SignalAction, PriceType


def make_ctx(**overrides) -> RiskContext:
    defaults = dict(
        request=PlaceOrderRequest(
            client_order_id="t1", account_id=None, market=Market.STOCK,
            symbol="600000.SH", side=OrderSide.BUY, action=SignalAction.OPEN,
            price_type=PriceType.LIMIT, price=Decimal("10"), quantity=Decimal("100"),
            metadata={"strategy_id": "ma_cross"},
        ),
        system_status="trading",
        risk_config={"blocked_symbols": [], "allowed_symbols": [],
                     "max_order_amount": 1000000, "max_order_quantity": 10000,
                     "daily_loss_limit": 50000, "daily_trade_count_limit": 100,
                     "duplicate_signal_window_seconds": 3},
        account_asset={}, positions=[], today_trade_count=0,
        today_pnl=Decimal("0"), recent_signals=[], now=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return RiskContext(**defaults)


class TestSystemStateRule:
    def test_trading_passed(self):
        r = SystemStateRule().check(make_ctx(system_status="trading"))
        assert r.result == "passed"

    def test_breaker_rejected(self):
        r = SystemStateRule().check(make_ctx(system_status="circuit_breaker"))
        assert r.result == "rejected" and r.rule_code == "RISK_SYSTEM_STATE"


class TestSymbolBlacklistRule:
    def test_in_blacklist_rejected(self):
        r = SymbolBlacklistRule().check(
            make_ctx(risk_config={**make_ctx().risk_config, "blocked_symbols": ["600000.SH"]}))
        assert r.result == "rejected" and r.rule_code == "RISK_SYMBOL_BLACKLIST"

    def test_not_in_blacklist_passed(self):
        assert SymbolBlacklistRule().check(make_ctx()).result == "passed"


class TestOrderAmountRule:
    def test_exceed_rejected(self):
        # 10 * 100 = 1000 < 1000000 passed
        assert OrderAmountRule().check(make_ctx()).result == "passed"
        # 1000 * 10000 = 10,000,000 > 1,000,000 rejected
        ctx = make_ctx(request=PlaceOrderRequest(
            client_order_id="t2", account_id=None, market=Market.STOCK,
            symbol="600000.SH", side=OrderSide.BUY, action=SignalAction.OPEN,
            price_type=PriceType.LIMIT, price=Decimal("1000"), quantity=Decimal("10000"),
            metadata={}))
        r = OrderAmountRule().check(ctx)
        assert r.result == "rejected" and r.rule_code == "RISK_ORDER_AMOUNT_LIMIT"


class TestDailyLossRule:
    def test_loss_exceeds_limit_rejected(self):
        ctx = make_ctx(today_pnl=Decimal("-60000"))
        r = DailyLossRule().check(ctx)
        assert r.result == "rejected" and r.rule_code == "RISK_DAILY_LOSS_LIMIT"


class TestDuplicateSignalRule:
    def test_duplicate_in_window_rejected(self):
        now = datetime.now(timezone.utc)
        ctx = make_ctx(
            recent_signals=[{"strategy_id": "ma_cross", "symbol": "600000.SH",
                             "side": "buy", "action": "open", "ts": now.timestamp()}],
            now=now,
        )
        r = DuplicateSignalRule().check(ctx)
        assert r.result == "rejected" and r.rule_code == "RISK_DUPLICATE_SIGNAL"
```

### 订单状态机测试

> 实现：`order_service.VALID_TRANSITIONS` + `OrderService.transition()`，非法迁移抛 `ORDER_INVALID_TRANSITION`。
> 系统状态机另见 `system_service.VALID_TRANSITIONS`（非法迁移抛 `RISK_INVALID_STATE_TRANSITION`）。
> 单测：`backend/app/tests/services/test_order_service.py`（`test_order_state_machine_*`）。

```python
import pytest
from app.api.response import BizError
from app.schemas.enums import OrderStatus
from app.schemas.error_codes import ErrorCode
from app.services.order_service import OrderService, VALID_TRANSITIONS


def test_order_state_machine_valid():
    svc = OrderService()
    order = Order(status=OrderStatus.PENDING_RISK, client_order_id="t1")
    svc.transition(order, OrderStatus.SUBMITTING)
    assert order.status == OrderStatus.SUBMITTING


def test_order_state_machine_invalid():
    svc = OrderService()
    order = Order(status=OrderStatus.SUBMITTED, client_order_id="t2")
    with pytest.raises(BizError) as exc:
        svc.transition(order, OrderStatus.SUBMITTING)  # 不可回退
    assert exc.value.code == ErrorCode.ORDER_INVALID_TRANSITION
    assert OrderStatus.SUBMITTING not in VALID_TRANSITIONS[OrderStatus.SUBMITTED]
```

## 集成测试用例骨架

> 需要真实 PostgreSQL 测试库。`pytest -m integration`。

### 幂等约束测试

> `backend/app/tests/services/test_idempotent.py`

```python
import pytest
from uuid import uuid4
from app.services.trade_service import TradeService
from app.sdk.models import TradeUpdateEvent, Market, OrderSide


@pytest.mark.integration
class TestIdempotent:
    def test_duplicate_trade_not_inserted(self, db, mock_trade_event):
        svc = TradeService(db, ...)
        # 第一次写入
        svc.on_trade_update(mock_trade_event)
        # 重复写入
        svc.on_trade_update(mock_trade_event)
        # 断言只有一条
        count = db.execute("SELECT count(*) FROM trades WHERE sdk_trade_id = :id",
                           {"id": mock_trade_event.sdk_trade_id}).scalar()
        assert count == 1


@pytest.fixture
def mock_trade_event():
    return TradeUpdateEvent(
        sdk_trade_id="MOCKT_dup_1", client_order_id="lh_test_1",
        sdk_order_id="MOCK_1", symbol="600000.SH", market=Market.STOCK,
        side=OrderSide.BUY, price=Decimal("10.05"), quantity=Decimal("50"),
        trade_time=datetime.now(timezone.utc),
    )
```

### 风控拒绝不调用 SDK

```python
@pytest.mark.integration
class TestRiskRejectNoSdk:
    def test_blacklisted_symbol_no_place_order(self, db, mock_adapter):
        risk = RiskService(db, audit)
        order = OrderService(db, risk, trade_svc)
        # 监视 mock_adapter.place_order
        mock_adapter.place_order = Mock()
        # 构造黑名单信号
        signal = make_signal(symbol="ST001.SH")
        req = build_request(signal)
        passed, _ = risk.check(req, signal_id=signal.signal_id)
        assert not passed
        order.create_from_signal(signal, req)
        # 关键断言：SDK place_order 没被调用
        mock_adapter.place_order.assert_not_called()
```

## 端到端测试骨架

> `backend/app/tests/e2e/test_signal_to_trade.py`。用 `httpx.AsyncClient` + Mock SDK + 测试库。

```python
import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_signal_to_trade_flow(test_db, mock_adapter):
    """端到端：启动策略 -> Mock 行情 -> 信号 -> 风控 -> 下单 -> 成交。"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1. 健康检查
        r = await client.get("/api/health")
        assert r.json()["data"]["api"] == "ok"

        # 2. 启动策略
        r = await client.post("/api/strategies/ma_cross/start",
                              json={"confirm": True, "run_mode": "live",
                                    "symbols": ["MOCK"], "parameters": {}})
        assert r.json()["success"]

        # 3. 推送 Mock K 线触发信号
        from app.sdk.models import KlineBar, Market
        bar = KlineBar(symbol="MOCK", market=Market.STOCK, interval="5m",
                       bar_time=datetime.now(timezone.utc),
                       open=Decimal("10"), high=Decimal("10.2"),
                       low=Decimal("9.9"), close=Decimal("11"),
                       volume=Decimal("10000"))
        strategy_service.dispatch_bar(bar)
        await asyncio.sleep(0.1)

        # 4. 查信号
        r = await client.get("/api/signals")
        assert len(r.json()["data"]["items"]) > 0

        # 5. 查订单（应自动创建并成交）
        r = await client.get("/api/orders")
        orders = r.json()["data"]["items"]
        assert len(orders) > 0

        # 6. 等待 Mock 成交
        await asyncio.sleep(0.6)
        r = await client.get(f"/api/orders/{orders[0]['client_order_id']}")
        assert r.json()["data"]["status"] in ("filled", "partially_filled")

        # 7. 查成交
        r = await client.get("/api/trades")
        assert len(r.json()["data"]["items"]) > 0
```

### 一键停止 E2E

```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_emergency_stop_blocks_new_orders(test_db, mock_adapter):
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 一键停止
        r = await client.post("/api/risk/emergency-stop",
                              json={"reason": "测试", "cancel_open_orders": False})
        assert r.json()["success"]

        # 启动策略 + 推行情 -> 信号应被风控拒绝
        await client.post("/api/strategies/ma_cross/start",
                          json={"confirm": True, "run_mode": "live", "symbols": ["MOCK"]})
        strategy_service.dispatch_bar(make_bar())
        await asyncio.sleep(0.1)

        # 查 risk_checks，应有 RISK_SYSTEM_STATE 拒绝
        r = await client.get("/api/risk/checks?result=rejected")
        checks = r.json()["data"]["items"]
        assert any(c["rule_code"] == "RISK_SYSTEM_STATE" for c in checks)

        # 查 orders，不应有新订单
        r = await client.get("/api/orders")
        assert len(r.json()["data"]["items"]) == 0
```

### 重启恢复 E2E

```python
@pytest.mark.e2e
def test_restart_preserves_breaker_and_unknown_orders(test_db):
    """熔断状态和未知订单不因重启自动解除。"""
    # 1. 构造熔断状态 + 一笔 unknown 订单
    set_system_status("circuit_breaker")
    create_order(status="unknown")

    # 2. 模拟重启：调用 recovery
    from app.workers.recovery import recover_on_startup
    recover_on_startup(test_db)

    # 3. 断言状态保持
    assert get_system_status() == "circuit_breaker"
    assert get_unknown_orders()  # unknown 订单进入同步队列
```

## 覆盖率目标

| 模块 | 目标覆盖率 | 补测前 | 补测后（2026-07-20） |
| --- | --- | --- | --- |
| `app/services/risk_rules.py` | ≥ 95% | 91% | **100%** ✅ |
| `app/services/order_service.py` | ≥ 90% | 78% | **100%** ✅ |
| `app/services/trade_service.py` | ≥ 90% | 60% | **100%** ✅ |
| `app/sdk/mock_adapter.py` | ≥ 85% | 84% | **100%** ✅ |
| `app/services/metrics_service.py` | ≥ 85% | 95% | **95%** ✅ |
| `app/services/ai_report_service.py` | ≥ 85% | 84% | **100%** ✅ |
| `app/services/strategy_service.py` | ≥ 80% | 82% | **82%** ✅ |
| `app/api/routes/*` | ≥ 70% | 参差；history/ai 已补 | 参差；history/ai 已补 |
| 整体 | ≥ 80% | 81% | **85%** ✅（4917 statements，753 missed） |

跑覆盖率：`pytest --cov=app --cov-report=html --cov-report=term-missing`

> 2026-07-21 结论：`pytest` **170 passed**；整体覆盖率 **85%**。文档列出的关键服务模块均已达到或超过目标（含 P0-2 风控关口与 `mock_adapter` 边缘补测）。

## 手工验收脚本（真实 SDK 前）

用 Mock 模式按以下步骤手工跑一遍，每步对照预期：

| 步骤 | 操作 | 预期 |
| --- | --- | --- |
| 1 | 启动后端 + 前端 | 健康检查全绿 |
| 2 | 仪表盘 | 显示 Mock SDK 连接、状态 ready |
| 3 | 行情看板 | Mock 行情实时刷新 |
| 4 | 风控设置 | 把 MOCK 标的加入白名单 |
| 5 | 启动 ma_cross 策略 | 状态 running |
| 6 | 等待行情触发信号 | 信号列表有记录 |
| 7 | 查订单 | 自动创建并部分成交 |
| 8 | 查成交 | 成交记录落库 |
| 9 | 查持仓/资金 | 快照更新 |
| 10 | 点一键停止 | 状态变 emergency_stopped |
| 11 | 再推行情 | 新信号被风控拒绝 |
| 12 | 恢复交易 | 需输入原因，恢复后状态 trading |
| 13 | 重启后端 | 系统状态保持，未完结订单继续同步 |
| 14 | 生成 AI 报告 | 报告含指标，无下单指令 |
| 15 | 历史交易筛选/导出 CSV | 列表与 BOM CSV 正常 |
| 16 | 交易链路抽屉 | 信号→风控→委托→成交→审计 |
| 17 | 策略构建器 AI 生成 | 自然语言→definition 填入表单，校验后可保存 |
| 18 | 发布规则策略并回测 | 回测任务正常完成 |

阶段 7 自动化补充：`test_metrics_service.py`（FIFO 盈亏/胜率）、`test_ai_report_service.py`（指令词过滤与免责声明）、`test_ai_strategy_service.py`（JSON 解析与 DSL 校验）。
