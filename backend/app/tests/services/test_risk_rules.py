"""risk_rules 各规则拒绝分支单元测试。"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.enums import Market, OrderSide, PriceType, SignalAction
from app.sdk.models import PlaceOrderRequest
from app.services.risk_rules import (
    DataQualityRule,
    DailyLossRule,
    DailyTradeCountRule,
    OrderAmountRule,
    OrderQuantityRule,
    RiskContext,
    SymbolPositionRule,
    TotalPositionRule,
    TradingSessionRule,
)


def _ctx(**overrides) -> RiskContext:
    req = PlaceOrderRequest(
        client_order_id=f"t_{uuid4().hex[:8]}",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        metadata={"strategy_id": "ma_cross"},
    )
    base = dict(
        request=req,
        system_status="trading",
        risk_config={
            "allowed_symbols": ["600000.SH"],
            "blocked_symbols": [],
            "trading_sessions": [{"start": "00:00", "end": "23:59"}],
            "max_order_amount": "1000000",
            "max_order_quantity": "100000",
            "max_symbol_position": "100000",
            "max_total_position": "100000000",
            "daily_loss_limit": "10000",
            "daily_trade_count_limit": "1000",
        },
        account_asset={},
        positions=[],
        today_trade_count=0,
        today_pnl=Decimal("0"),
        recent_signals=[],
        now=datetime.now(timezone.utc),
        latest_price=None,
    )
    base.update(overrides)
    return RiskContext(**base)


@pytest.mark.unit
def test_trading_session_rejects_outside():
    # days 无效 → 永远不命中时段 → rejected
    cfg = {**_ctx().risk_config, "trading_sessions": [{"start": "00:00", "end": "23:59", "days": ["never"]}]}
    result = TradingSessionRule().check(_ctx(risk_config=cfg))
    assert result.result == "rejected"
    assert result.rule_code == "RISK_TRADING_SESSION"


@pytest.mark.unit
def test_data_quality_rule_blocks_live_gate_failure():
    result = DataQualityRule().check(
        _ctx(data_quality={"ready": False, "reason": "600000.SH：存在日线缺口"})
    )

    assert result.result == "rejected"
    assert result.rule_code == "RISK_DATA_QUALITY"


@pytest.mark.unit
def test_data_quality_rule_allows_risk_reducing_close():
    request = _ctx().request.model_copy(update={"action": SignalAction.CLOSE})

    result = DataQualityRule().check(
        _ctx(
            request=request,
            data_quality={"ready": False, "reason": "600000.SH：存在日线缺口"},
        )
    )

    assert result.result == "passed"


@pytest.mark.unit
def test_order_amount_uses_latest_price_and_rejects():
    req = _ctx().request.model_copy(update={"price": None, "quantity": Decimal("100")})
    ctx = _ctx(
        request=req,
        latest_price=Decimal("20"),
        risk_config={**_ctx().risk_config, "max_order_amount": "1000"},
    )
    result = OrderAmountRule().check(ctx)
    assert result.result == "rejected"
    assert "超过上限" in result.reason


@pytest.mark.unit
def test_order_amount_passes_when_no_price():
    req = _ctx().request.model_copy(update={"price": None})
    ctx = _ctx(request=req, latest_price=None)
    result = OrderAmountRule().check(ctx)
    assert result.result == "passed"


@pytest.mark.unit
def test_order_quantity_rejects():
    ctx = _ctx(risk_config={**_ctx().risk_config, "max_order_quantity": "50"})
    result = OrderQuantityRule().check(ctx)
    assert result.result == "rejected"


@pytest.mark.unit
def test_symbol_position_rejects():
    ctx = _ctx(
        positions=[{"symbol": "600000.SH", "quantity": "90"}],
        risk_config={**_ctx().risk_config, "max_symbol_position": "100"},
    )
    result = SymbolPositionRule().check(ctx)
    assert result.result == "rejected"


@pytest.mark.unit
def test_total_position_rejects():
    # 现有市值 1000 + 本次买入 10*100=1000 = 2000 > 上限 1500
    ctx = _ctx(
        positions=[{"symbol": "600000.SH", "quantity": "10", "market_value": "1000"}],
        risk_config={**_ctx().risk_config, "max_total_position": "1500"},
    )
    result = TotalPositionRule().check(ctx)
    assert result.result == "rejected"
    assert "超过上限" in result.reason


@pytest.mark.unit
def test_total_position_passes_without_new_buy_exposure():
    # 仅现有仓位未超限；卖出不增加敞口
    req = _ctx().request.model_copy(update={"side": OrderSide.SELL})
    ctx = _ctx(
        request=req,
        positions=[{"symbol": "600000.SH", "quantity": "10", "market_value": "1000"}],
        risk_config={**_ctx().risk_config, "max_total_position": "1500"},
    )
    result = TotalPositionRule().check(ctx)
    assert result.result == "passed"


@pytest.mark.unit
def test_daily_loss_rejects():
    ctx = _ctx(
        today_pnl=Decimal("-5000"),
        risk_config={**_ctx().risk_config, "daily_loss_limit": "1000"},
    )
    result = DailyLossRule().check(ctx)
    assert result.result == "rejected"


@pytest.mark.unit
def test_daily_trade_count_rejects():
    ctx = _ctx(
        today_trade_count=10,
        risk_config={**_ctx().risk_config, "daily_trade_count_limit": "10"},
    )
    result = DailyTradeCountRule().check(ctx)
    assert result.result == "rejected"
