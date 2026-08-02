"""阶段 5：熔断、恢复、启动恢复、未知订单。"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.api.response import BizError
from app.repositories.account_repo import AccountRepository
from app.repositories.asset_repo import AssetRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.strategy_repo import StrategyRunRepository
from app.schemas.enums import (
    Market,
    OrderSide,
    OrderStatus,
    PriceType,
    SignalAction,
    StrategyRunStatus,
    SystemStatus,
)
from app.sdk import manager as sdk_manager
from app.sdk.models import PlaceOrderRequest
from app.services import runtime_metrics
from app.services.risk_service import RiskService, ZERO_ACCOUNT_ID
from app.services.system_service import SystemStateService
from app.workers.breaker_monitor import check_breaker_conditions
from app.workers.recovery import recover_on_startup
from app.workers.sync_jobs import sync_orders_trades


def _make_request(*, symbol: str = "600000.SH") -> PlaceOrderRequest:
    return PlaceOrderRequest(
        client_order_id=f"test_{uuid4().hex[:8]}",
        account_id=ZERO_ACCOUNT_ID,
        market=Market.STOCK,
        symbol=symbol,
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        metadata={"strategy_id": "ma_cross"},
    )


def _create_order(db, *, status: OrderStatus = OrderStatus.SUBMITTING, client_order_id: str | None = None):
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = client_order_id or f"ord_{uuid4().hex[:8]}"
    return OrderRepository(db).create_order(
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
        status=status,
        submitted_at=datetime.now(timezone.utc),
    )


def _seed_reconciled_assets(db):
    accounts = AccountRepository(db)
    assets = AssetRepository(db)
    for market in (Market.STOCK, Market.FUTURES):
        account = accounts.get_or_create_default(market)
        snapshot = sdk_manager.get_adapter_for_market(market).get_account()
        assets.insert_snapshot(account.id, snapshot)
    db.flush()


def _cleanup_phase5_rows(db):
    """清理本文件测试产生的订单/运行记录，避免污染共享开发库。"""
    from app.db.models.order import Order
    from app.db.models.strategy_run import StrategyRun
    from app.db.models.system_event import SystemEvent

    db.query(Order).filter(
        Order.client_order_id.like("ord_%")
        | Order.client_order_id.like("unk_%")
        | Order.client_order_id.like("test_%")
    ).delete(synchronize_session=False)
    db.query(StrategyRun).filter(StrategyRun.stop_reason.like("%进程重启%")).delete(
        synchronize_session=False
    )
    db.query(SystemEvent).filter(
        SystemEvent.event_code.in_(["ORDER_UNKNOWN", "STARTUP_RECOVERY", "CIRCUIT_BREAKER", "EMERGENCY_STOP"])
    ).delete(synchronize_session=False)
    db.commit()


@pytest.fixture(autouse=True)
def _reset_runtime(db):
    runtime_metrics.reset_all_for_tests()
    sdk_manager.reset_adapters()
    _cleanup_phase5_rows(db)
    yield
    _cleanup_phase5_rows(db)
    runtime_metrics.reset_all_for_tests()
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_emergency_stop_blocks_new_orders(db, reset_system_state, client):
    resp = client.post(
        "/api/risk/emergency-stop",
        json={"reason": "测试一键停止", "cancel_open_orders": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "emergency_stopped"

    risk = RiskService(db, correlation_id="test_es")
    passed, results, _ = risk.check(_make_request())
    db.commit()
    assert passed is False
    assert any(r.rule_code == "RISK_SYSTEM_STATE" for r in results)


@pytest.mark.integration
def test_trigger_breaker_and_status(db, reset_system_state):
    sdk_manager.ensure_connected()
    risk = RiskService(db, correlation_id="test_breaker")
    result = risk.trigger_breaker("测试熔断")
    db.commit()
    assert result is not None
    assert result["status"] == "circuit_breaker"

    status = risk.get_status()
    assert status["breaker_active"] is True
    assert status["system_status"] == "circuit_breaker"

    passed, results, _ = risk.check(_make_request())
    assert passed is False
    assert any(r.rule_code == "RISK_SYSTEM_STATE" for r in results)


@pytest.mark.integration
def test_resume_blocked_when_sdk_disconnected(db, reset_system_state):
    sdk_manager.ensure_connected()
    svc = SystemStateService(db, correlation_id="test_resume_sdk")
    svc.transition(SystemStatus.CIRCUIT_BREAKER, reason="test")
    db.commit()

    adapter = sdk_manager.get_stock_adapter()
    adapter.inject_disconnect()
    risk = RiskService(db, correlation_id="test_resume_sdk")
    with pytest.raises(BizError) as exc:
        risk.resume("尝试恢复")
    # 可能同时命中多个 blocker；SDK 断线时必须出现在 debug/message 中
    assert exc.value.code == "RISK_RESUME_BLOCKED"
    assert "SDK" in (exc.value.debug or exc.value.message)
    adapter.clear_inject_disconnect()


@pytest.mark.integration
def test_resume_blocked_when_unknown_orders(db, reset_system_state):
    sdk_manager.ensure_connected()
    svc = SystemStateService(db, correlation_id="test_resume_unk")
    svc.transition(SystemStatus.EMERGENCY_STOPPED, reason="test")
    _create_order(db, status=OrderStatus.UNKNOWN)
    db.commit()

    risk = RiskService(db, correlation_id="test_resume_unk")
    with pytest.raises(BizError) as exc:
        risk.resume("尝试恢复")
    assert exc.value.code == "RISK_UNKNOWN_ORDERS_PENDING"


@pytest.mark.integration
def test_resume_success_when_preconditions_met(db, reset_system_state):
    sdk_manager.ensure_connected()
    _seed_reconciled_assets(db)
    svc = SystemStateService(db, correlation_id="test_resume_ok")
    svc.transition(SystemStatus.CIRCUIT_BREAKER, reason="test")
    db.commit()

    risk = RiskService(db, correlation_id="test_resume_ok")
    checklist = risk.get_resume_checklist()
    assert checklist["all_passed"] is True
    assert {item["code"] for item in checklist["checks"]} >= {
        "database",
        "channel",
        "market_data",
        "unknown_orders",
        "account_reconciliation",
    }
    result = risk.resume("已确认环境正常")
    db.commit()
    assert result["status"] == "trading"
    assert "resumed_at" in result


@pytest.mark.integration
def test_restart_preserves_breaker_and_queues_orders(db, reset_system_state):
    svc = SystemStateService(db, correlation_id="test_recovery")
    svc.transition(SystemStatus.CIRCUIT_BREAKER, reason="保留熔断")
    order = _create_order(db, status=OrderStatus.SUBMITTING)
    run_repo = StrategyRunRepository(db)
    run_repo.create_run(
        strategy_id="ma_cross",
        status=StrategyRunStatus.RUNNING,
        parameters={"symbols": ["600000.SH"]},
    )
    db.commit()

    runtime_metrics.clear_sync_queue()
    result = recover_on_startup(db, correlation_id="test_recovery")
    db.commit()

    assert result["system_status"] == "circuit_breaker"
    assert order.client_order_id in result["open_orders_queued"]
    assert order.client_order_id in runtime_metrics.list_sync_queue()
    assert "ma_cross" in result["pending_confirm_strategies"]

    status = SystemStateService(db).get_status()
    assert status["status"] == "circuit_breaker"


@pytest.mark.integration
def test_sync_marks_unknown_sdk_status(db, reset_system_state):
    from app.services.market_service import market_service

    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    market_service._started = True  # noqa: SLF001 — 允许同步任务跳过 started 检查

    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = f"unk_{uuid4().hex[:8]}"
    order = OrderRepository(db).create_order(
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
        status=OrderStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
    )
    db.commit()

    adapter = sdk_manager.get_stock_adapter()
    # 直接写入 mock 内部订单表
    adapter._orders[cid] = {  # noqa: SLF001
        "client_order_id": cid,
        "sdk_order_id": "sdk_x",
        "status": "SDK_STATUS_XYZ",
        "filled": Decimal("0"),
        "remaining": Decimal("100"),
    }

    sync_orders_trades(db)
    db.refresh(order)
    assert order.status == OrderStatus.UNKNOWN

    risk = RiskService(db, correlation_id="test_unk_sync")
    assert risk.count_unknown_orders() >= 1

    market_service._started = False  # noqa: SLF001
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_breaker_monitor_consecutive_fail(db, reset_system_state):
    sdk_manager.ensure_connected()
    from app.repositories.risk_repo import RiskRepository

    RiskRepository(db).update_config({"consecutive_order_fail_limit": 2})
    db.commit()

    runtime_metrics.record_order_submit_result(False)
    runtime_metrics.record_order_submit_result(False)

    reason = check_breaker_conditions(db)
    assert reason == "连续下单失败超过阈值"
    status = SystemStateService(db).get_status()
    assert status["status"] == "circuit_breaker"
