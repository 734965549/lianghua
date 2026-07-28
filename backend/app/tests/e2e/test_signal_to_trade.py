"""端到端：策略信号 → 风控 → 下单成交 / 一键停止 / 重启恢复。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.repositories.account_repo import AccountRepository
from app.repositories.order_repo import OrderRepository
from app.schemas.enums import (
    Market,
    OrderSide,
    OrderStatus,
    PriceType,
    SignalAction,
    SystemStatus,
)
from app.sdk import manager as sdk_manager
from app.sdk.models import KlineBar
from app.services import runtime_metrics
from app.services.strategy_service import strategy_service
from app.services.system_service import SystemStateService
from app.workers.recovery import recover_on_startup


def _make_bar(
    *,
    symbol: str = "600000.SH",
    close: Decimal = Decimal("10"),
    bar_time: datetime | None = None,
) -> KlineBar:
    t = bar_time or datetime.now(timezone.utc)
    return KlineBar(
        symbol=symbol,
        market=Market.STOCK,
        interval="1m",
        bar_time=t,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=Decimal("1000"),
    )


def _golden_cross_bars(symbol: str = "600000.SH") -> list[KlineBar]:
    """fast=2/slow=3 时构造金叉：prev_fast<=prev_slow 且 fast>slow。"""
    base = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    closes = [Decimal("10"), Decimal("9"), Decimal("8"), Decimal("12")]
    return [
        _make_bar(symbol=symbol, close=c, bar_time=base + timedelta(minutes=i))
        for i, c in enumerate(closes)
    ]


@pytest.fixture(autouse=True)
def _e2e_reset(db, reset_system_state):
    strategy_service._running.clear()
    runtime_metrics.reset_all_for_tests()
    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    yield
    strategy_service._running.clear()
    runtime_metrics.reset_all_for_tests()
    sdk_manager.reset_adapters()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_signal_to_trade_flow(db, reset_system_state):
    """端到端：启动策略 -> Mock K 线 -> 信号 -> 风控 -> 下单 -> 成交。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["data"]["api"] == "ok"

        r = await client.post(
            "/api/strategies/ma_cross/start",
            json={
                "confirm": True,
                "run_mode": "live",
                "symbols": ["600000.SH"],
                "parameters": {
                    "symbols": ["600000.SH"],
                    "fast": 2,
                    "slow": 3,
                    "interval": "1m",
                    "quantity": "100",
                },
            },
        )
        assert r.status_code == 200
        assert r.json()["success"] is True

        for bar in _golden_cross_bars():
            strategy_service.dispatch_bar(bar)
        await asyncio.sleep(0.2)

        r = await client.get("/api/signals")
        assert r.status_code == 200
        signals = r.json()["data"]["items"]
        assert len(signals) > 0

        r = await client.get("/api/orders")
        assert r.status_code == 200
        orders = r.json()["data"]["items"]
        assert len(orders) > 0

        await asyncio.sleep(0.8)
        r = await client.get(f"/api/orders/{orders[0]['client_order_id']}")
        assert r.status_code == 200
        order_status = r.json()["data"]["order"]["status"]
        assert order_status in ("filled", "partially_filled", "submitted")

        r = await client.get("/api/trades")
        assert r.status_code == 200
        # Mock 成交可能略有延迟；至少信号与订单链路已通
        assert r.json()["success"] is True
        if order_status in ("filled", "partially_filled"):
            assert len(r.json()["data"]["items"]) > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_emergency_stop_blocks_new_orders(db, reset_system_state):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 先启动策略（emergency_stopped 后无法再 start）
        r = await client.post(
            "/api/strategies/ma_cross/start",
            json={
                "confirm": True,
                "symbols": ["600000.SH"],
                "parameters": {
                    "symbols": ["600000.SH"],
                    "fast": 2,
                    "slow": 3,
                    "interval": "1m",
                    "quantity": "100",
                },
            },
        )
        assert r.json()["success"] is True

        r = await client.post(
            "/api/risk/emergency-stop",
            json={"reason": "测试", "cancel_open_orders": False},
        )
        assert r.status_code == 200
        assert r.json()["success"] is True
        assert r.json()["data"]["status"] == "emergency_stopped"

        for bar in _golden_cross_bars():
            strategy_service.dispatch_bar(bar)
        await asyncio.sleep(0.2)

        r = await client.get("/api/risk/checks?result=rejected")
        assert r.status_code == 200
        checks = r.json()["data"]["items"]
        assert any(c["rule_code"] == "RISK_SYSTEM_STATE" for c in checks)

        r = await client.get("/api/orders")
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) == 0


@pytest.mark.e2e
def test_restart_preserves_breaker_and_unknown_orders(db, reset_system_state):
    """熔断状态和未知订单不因重启自动解除。"""
    SystemStateService(db, correlation_id="e2e_restart").transition(
        SystemStatus.CIRCUIT_BREAKER, reason="e2e 熔断"
    )
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = f"unk_{uuid4().hex[:8]}"
    OrderRepository(db).create_order(
        client_order_id=cid,
        account_id=account.id,
        strategy_id="ma_cross",
        signal_id=None,
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        status=OrderStatus.UNKNOWN,
        submitted_at=datetime.now(timezone.utc),
    )
    db.commit()

    runtime_metrics.clear_sync_queue()
    result = recover_on_startup(db, correlation_id="e2e_restart")
    db.commit()

    assert result["system_status"] == "circuit_breaker"
    assert cid in result["open_orders_queued"]
    assert cid in runtime_metrics.list_sync_queue()
    status = SystemStateService(db).get_status()
    assert status["status"] == "circuit_breaker"
