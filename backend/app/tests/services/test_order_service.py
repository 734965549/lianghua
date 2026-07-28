import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.api.response import BizError
from app.db.models.order import Order
from app.repositories.account_repo import AccountRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.risk_repo import RiskRepository
from app.repositories.trade_repo import TradeRepository
from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, RiskResult, SignalAction, SystemStatus
from app.sdk import manager as sdk_manager
from app.sdk.models import PlaceOrderRequest
from app.services.order_service import OrderService, order_service
from app.services.system_service import SystemStateService
from app.services.trade_service import trade_service


def _make_signal_row(*, strategy_id: str = "test_order_flow", symbol: str = "600000.SH"):
    from app.db.models.strategy_signal import StrategySignal

    signal_id = uuid4()
    now = datetime.now(timezone.utc)
    return StrategySignal(
        signal_id=signal_id,
        strategy_id=strategy_id,
        symbol=symbol,
        market=Market.STOCK,
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        reason="test",
        signal_time=now,
    )


def _make_place_req(client_order_id: str) -> PlaceOrderRequest:
    return PlaceOrderRequest(
        client_order_id=client_order_id,
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
    )


def _seed_passed_risk_check(db, client_order_id: str, signal_id=None):
    return RiskRepository(db).add_check(
        signal_id=signal_id,
        client_order_id=client_order_id,
        result=RiskResult.PASSED,
        rule_code="",
        reason="all rules passed",
        checked_at=datetime.now(timezone.utc),
        snapshot={},
    )


@pytest.mark.unit
def test_order_state_machine_valid():
    svc = OrderService()
    order = Order(status=OrderStatus.PENDING_RISK, client_order_id="t1")
    svc.transition(order, OrderStatus.SUBMITTING)
    assert order.status == OrderStatus.SUBMITTING

    order.status = OrderStatus.SUBMITTING
    svc.transition(order, OrderStatus.SUBMITTED)
    assert order.status == OrderStatus.SUBMITTED

    order.status = OrderStatus.SUBMITTED
    svc.transition(order, OrderStatus.PARTIALLY_FILLED)
    order.status = OrderStatus.PARTIALLY_FILLED
    svc.transition(order, OrderStatus.FILLED)
    assert order.status == OrderStatus.FILLED

    order.status = OrderStatus.SUBMITTED
    svc.transition(order, OrderStatus.UNKNOWN)
    assert order.status == OrderStatus.UNKNOWN
    svc.transition(order, OrderStatus.CANCELLED)
    assert order.status == OrderStatus.CANCELLED


@pytest.mark.unit
def test_order_state_machine_invalid():
    svc = OrderService()
    order = Order(status=OrderStatus.SUBMITTED, client_order_id="t2")
    with pytest.raises(BizError) as exc:
        svc.transition(order, OrderStatus.SUBMITTING)
    assert exc.value.code == "ORDER_INVALID_TRANSITION"


@pytest.mark.integration
def test_create_submit_filled(db, reset_system_state, monkeypatch):
    svc_state = SystemStateService(db, correlation_id="test_order_flow")
    svc_state.transition(SystemStatus.TRADING, reason="test")
    db.commit()

    AccountRepository(db).get_or_create_default(Market.STOCK)
    db.commit()

    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()
    from app.services.order_service import order_service as osvc
    from app.services.trade_service import trade_service as tsvc

    adapter.on_order_update(osvc.on_order_update)
    adapter.on_trade_update(tsvc.on_trade_update)

    sig = _make_signal_row()
    db.add(sig)
    db.flush()

    client_order_id = f"lh_{sig.signal_time:%Y%m%d}_{sig.signal_id.hex[:8]}"
    place_req = _make_place_req(client_order_id)
    check = _seed_passed_risk_check(db, client_order_id, signal_id=sig.signal_id)
    db.flush()

    order = order_service.create_from_signal(
        db, sig, place_req, check_id=check.check_id, correlation_id="test_flow"
    )
    assert order.client_order_id == client_order_id

    deadline = time.time() + 3.0
    final_status = None
    while time.time() < deadline:
        db.expire_all()
        row = OrderRepository(db).get_by_client_order_id(client_order_id)
        if row and row.status == OrderStatus.FILLED:
            final_status = row.status
            break
        time.sleep(0.1)

    assert final_status == OrderStatus.FILLED
    trades, total = TradeRepository(db).list_trades(client_order_id=client_order_id, limit=10)
    assert total >= 1
    filled_sum = sum(Decimal(str(t.quantity)) for t in trades)
    assert filled_sum == Decimal("100")

    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_create_from_signal_requires_passed_check(db, reset_system_state):
    AccountRepository(db).get_or_create_default(Market.STOCK)
    db.commit()

    sig = _make_signal_row()
    db.add(sig)
    db.flush()

    client_order_id = f"lh_{sig.signal_time:%Y%m%d}_{sig.signal_id.hex[:8]}"
    place_req = _make_place_req(client_order_id)

    with pytest.raises(BizError) as exc:
        order_service.create_from_signal(
            db, sig, place_req, check_id=uuid4(), correlation_id="test_no_check"
        )
    assert exc.value.code == "RISK_CHECK_REQUIRED"


@pytest.mark.integration
def test_submit_rejected_without_risk_check(db, reset_system_state, monkeypatch):
    """绕过 create_from_signal 直接建单提交时，submit 入口必须拦截。"""
    AccountRepository(db).get_or_create_default(Market.STOCK)
    db.commit()

    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()
    called = {"count": 0}
    original = adapter.place_order

    def spy_place_order(*args, **kwargs):
        called["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(adapter, "place_order", spy_place_order)

    now = datetime.now(timezone.utc)
    order_repo = OrderRepository(db)
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    order = order_repo.create_order(
        client_order_id=f"lh_{now:%Y%m%d}_{uuid4().hex[:8]}",
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
        status=OrderStatus.SUBMITTING,
        submitted_at=now,
    )
    db.commit()

    result = trade_service.submit(order.id, correlation_id="test_bypass")
    assert result.status == OrderStatus.FAILED
    assert "风控" in (result.fail_reason or "")
    assert called["count"] == 0

    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_submit_failed(db, reset_system_state):
    AccountRepository(db).get_or_create_default(Market.STOCK)
    db.commit()

    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()
    adapter.inject_next_order_fail()

    from app.services.order_service import order_service as osvc
    from app.services.trade_service import trade_service as tsvc

    adapter.on_order_update(osvc.on_order_update)
    adapter.on_trade_update(tsvc.on_trade_update)

    now = datetime.now(timezone.utc)
    order_repo = OrderRepository(db)
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    client_order_id = f"lh_{now:%Y%m%d}_{uuid4().hex[:8]}"
    order = order_repo.create_order(
        client_order_id=client_order_id,
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
        status=OrderStatus.SUBMITTING,
        submitted_at=now,
    )
    _seed_passed_risk_check(db, client_order_id)
    db.commit()

    result = trade_service.submit(order.id, correlation_id="test_fail")
    assert result.status == OrderStatus.FAILED
    assert result.fail_reason

    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_confirm_unknown_order(db, reset_system_state):
    now = datetime.now(timezone.utc)
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = f"unk_svc_{uuid4().hex[:8]}"
    order_repo = OrderRepository(db)
    order_repo.create_order(
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
        submitted_at=now,
    )
    db.commit()

    svc = OrderService()
    row = svc.confirm_unknown(
        db,
        cid,
        resolved_status=OrderStatus.CANCELLED,
        reason="测试确认",
        correlation_id="test_confirm_unknown",
    )
    db.commit()
    assert row.status == OrderStatus.CANCELLED
    assert "测试确认" in row.fail_reason

    db.query(Order).filter(Order.client_order_id == cid).delete(synchronize_session=False)
    db.commit()


@pytest.mark.unit
def test_order_to_dict_decimal_branches():
    from app.services.order_service import order_to_dict, _decimal_str
    from unittest.mock import MagicMock

    assert _decimal_str(None) == "0"
    assert _decimal_str(1.25) == "1.25"

    row = MagicMock()
    row.id = uuid4()
    row.client_order_id = "c1"
    row.sdk_order_id = None
    row.account_id = uuid4()
    row.strategy_id = "ma_cross"
    row.signal_id = None
    row.symbol = "600000.SH"
    row.market = Market.STOCK
    row.side = OrderSide.BUY
    row.action = SignalAction.OPEN
    row.price_type = PriceType.LIMIT
    row.price = None
    row.quantity = Decimal("100")
    row.filled_quantity = 50.0
    row.status = OrderStatus.SUBMITTED
    row.submitted_at = None
    row.last_event_at = None
    row.fail_reason = None
    row.created_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    d = order_to_dict(row)
    assert d["price"] == "0"
    assert d["filled_quantity"] == "50.0"


@pytest.mark.integration
def test_create_from_signal_risk_not_passed(db, reset_system_state):
    AccountRepository(db).get_or_create_default(Market.STOCK)
    db.commit()
    sig = _make_signal_row()
    db.add(sig)
    db.flush()
    client_order_id = f"lh_{sig.signal_time:%Y%m%d}_{sig.signal_id.hex[:8]}"
    check = RiskRepository(db).add_check(
        signal_id=sig.signal_id,
        client_order_id=client_order_id,
        result=RiskResult.REJECTED,
        rule_code="RISK_SYSTEM_STATE",
        reason="no",
        checked_at=datetime.now(timezone.utc),
        snapshot={},
    )
    db.flush()
    with pytest.raises(BizError) as exc:
        order_service.create_from_signal(
            db, sig, _make_place_req(client_order_id), check_id=check.check_id
        )
    assert exc.value.code == "RISK_CHECK_NOT_PASSED"


@pytest.mark.integration
def test_create_from_signal_risk_mismatch(db, reset_system_state):
    AccountRepository(db).get_or_create_default(Market.STOCK)
    db.commit()
    sig = _make_signal_row()
    db.add(sig)
    db.flush()
    client_order_id = f"lh_{sig.signal_time:%Y%m%d}_{sig.signal_id.hex[:8]}"
    check = RiskRepository(db).add_check(
        signal_id=sig.signal_id,
        client_order_id="other_cid",
        result=RiskResult.PASSED,
        rule_code="",
        reason="ok",
        checked_at=datetime.now(timezone.utc),
        snapshot={},
    )
    db.flush()
    with pytest.raises(BizError) as exc:
        order_service.create_from_signal(
            db, sig, _make_place_req(client_order_id), check_id=check.check_id
        )
    assert exc.value.code == "RISK_CHECK_MISMATCH"


@pytest.mark.integration
def test_create_from_signal_returns_existing(db, reset_system_state, monkeypatch):
    AccountRepository(db).get_or_create_default(Market.STOCK)
    db.commit()
    sig = _make_signal_row()
    db.add(sig)
    db.flush()
    client_order_id = f"lh_{sig.signal_time:%Y%m%d}_{sig.signal_id.hex[:8]}"
    check = _seed_passed_risk_check(db, client_order_id, signal_id=sig.signal_id)
    db.flush()

    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    existing = OrderRepository(db).create_order(
        client_order_id=client_order_id,
        account_id=account.id,
        strategy_id=sig.strategy_id,
        signal_id=sig.signal_id,
        symbol=sig.symbol,
        market=sig.market,
        side=sig.side,
        action=sig.action,
        price_type=sig.price_type,
        price=Decimal("10"),
        quantity=Decimal("100"),
        status=OrderStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
    )
    db.commit()

    called = {"n": 0}
    monkeypatch.setattr(
        "app.services.trade_service.trade_service.submit",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1),
    )
    row = order_service.create_from_signal(
        db, sig, _make_place_req(client_order_id), check_id=check.check_id
    )
    assert row.id == existing.id
    assert called["n"] == 0


@pytest.mark.integration
def test_order_get_and_list(db, reset_system_state):
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = f"list_{uuid4().hex[:8]}"
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
        status=OrderStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
    )
    db.commit()
    assert order_service.get(db, cid) is not None
    assert order_service.get(db, "missing") is None
    rows, total = order_service.list(db, strategy_id="ma_cross", limit=10)
    assert total >= 1
    assert any(r.client_order_id == cid for r in rows)


@pytest.mark.integration
def test_order_cancel_paths(db, reset_system_state, monkeypatch):
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    db.commit()

    with pytest.raises(BizError) as exc:
        order_service.cancel(db, "no_order")
    assert exc.value.code == "ORDER_NOT_FOUND"

    cid = f"cxl_{uuid4().hex[:8]}"
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
        status=OrderStatus.FILLED,
        submitted_at=datetime.now(timezone.utc),
    )
    db.commit()
    with pytest.raises(BizError) as exc2:
        order_service.cancel(db, cid)
    assert exc2.value.code == "ORDER_NOT_CANCELLABLE"

    cid2 = f"cxl2_{uuid4().hex[:8]}"
    order = OrderRepository(db).create_order(
        client_order_id=cid2,
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
    order.sdk_order_id = "MOCK_OS_CXL"
    db.commit()

    from app.sdk.models import CancelOrderResult

    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()
    monkeypatch.setattr(
        adapter,
        "cancel_order",
        lambda req: CancelOrderResult(
            success=True,
            client_order_id=req.client_order_id,
            sdk_order_id=req.sdk_order_id,
            status=OrderStatus.CANCELLED,
        ),
    )
    row = order_service.cancel(db, cid2, reason="test", correlation_id="os_cxl")
    assert row.status == OrderStatus.CANCELLED
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_confirm_unknown_errors(db, reset_system_state):
    with pytest.raises(BizError) as exc:
        order_service.confirm_unknown(db, "missing", resolved_status=OrderStatus.CANCELLED)
    assert exc.value.code == "ORDER_NOT_FOUND"

    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = f"unk_err_{uuid4().hex[:8]}"
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
        status=OrderStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
    )
    db.commit()
    with pytest.raises(BizError) as exc2:
        order_service.confirm_unknown(db, cid, resolved_status=OrderStatus.CANCELLED)
    assert exc2.value.code == "ORDER_NOT_UNKNOWN"

    OrderRepository(db).get_by_client_order_id(cid).status = OrderStatus.UNKNOWN
    db.commit()
    with pytest.raises(BizError) as exc3:
        order_service.confirm_unknown(db, cid, resolved_status=OrderStatus.SUBMITTED)
    assert exc3.value.code == "ORDER_INVALID_RESOLVED_STATUS"


@pytest.mark.integration
def test_on_order_update_edge_cases(db, reset_system_state):
    from app.sdk.models import OrderUpdateEvent

    # 找不到订单
    order_service.on_order_update(
        OrderUpdateEvent(
            client_order_id="ghost",
            sdk_order_id="ghost_sdk",
            status=OrderStatus.SUBMITTED,
            event_time=datetime.now(timezone.utc),
        )
    )

    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = f"ou_{uuid4().hex[:8]}"
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

    # 仅 sdk_order_id 命中 + 回填 sdk_order_id + raw_payload + 合法迁移
    order.sdk_order_id = "SDK_OU_1"
    db.commit()
    order_service.on_order_update(
        OrderUpdateEvent(
            client_order_id=None,
            sdk_order_id="SDK_OU_1",
            status=OrderStatus.PARTIALLY_FILLED,
            filled_quantity=Decimal("40"),
            remaining_quantity=Decimal("60"),
            event_time=datetime.now(timezone.utc),
            raw_payload={"x": 1},
        )
    )
    db.refresh(order)
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert Decimal(str(order.filled_quantity)) == Decimal("40")
    assert order.raw_payload == {"x": 1}

    # 非法迁移：保守标记为 UNKNOWN，避免静默忽略异常回报
    order_service.on_order_update(
        OrderUpdateEvent(
            client_order_id=cid,
            sdk_order_id="SDK_OU_1",
            status=OrderStatus.PENDING_RISK,
            filled_quantity=Decimal("40"),
            event_time=datetime.now(timezone.utc),
        )
    )
    db.refresh(order)
    assert order.status == OrderStatus.UNKNOWN


@pytest.mark.integration
def test_on_order_update_backfill_sdk_id_and_forced_fallback(db, reset_system_state, monkeypatch):
    from app.sdk.models import OrderUpdateEvent
    from app.services.order_service import VALID_TRANSITIONS

    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = f"ou_bf_{uuid4().hex[:8]}"
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
    assert order.sdk_order_id is None
    db.commit()

    # 回填 sdk_order_id（300）
    order_service.on_order_update(
        OrderUpdateEvent(
            client_order_id=cid,
            sdk_order_id="SDK_BACKFILL",
            status=OrderStatus.SUBMITTED,
            filled_quantity=Decimal("0"),
            event_time=datetime.now(timezone.utc),
        )
    )
    db.refresh(order)
    assert order.sdk_order_id == "SDK_BACKFILL"

    # transition 抛错时不得直接赋值目标状态，仅尝试标记 UNKNOWN
    call_targets: list[OrderStatus] = []

    def raise_then_allow_unknown(o, st):
        call_targets.append(st)
        if st == OrderStatus.UNKNOWN:
            o.status = st
            return
        raise BizError("ORDER_INVALID_TRANSITION", "forced")

    monkeypatch.setattr(order_service, "transition", raise_then_allow_unknown)
    assert OrderStatus.PARTIALLY_FILLED in VALID_TRANSITIONS[OrderStatus.SUBMITTED]
    order_service.on_order_update(
        OrderUpdateEvent(
            client_order_id=cid,
            sdk_order_id="SDK_BACKFILL",
            status=OrderStatus.PARTIALLY_FILLED,
            filled_quantity=Decimal("10"),
            event_time=datetime.now(timezone.utc),
        )
    )
    db.refresh(order)
    assert call_targets == [OrderStatus.PARTIALLY_FILLED, OrderStatus.UNKNOWN]
    assert order.status == OrderStatus.UNKNOWN


@pytest.mark.integration
def test_on_order_update_exception_swallowed(db, reset_system_state, monkeypatch):
    from app.sdk.models import OrderUpdateEvent

    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = f"ou_ex_{uuid4().hex[:8]}"
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
        status=OrderStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
    )
    db.commit()

    monkeypatch.setattr(
        OrderRepository,
        "get_by_client_order_id",
        lambda self, x: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    order_service.on_order_update(
        OrderUpdateEvent(
            client_order_id=cid,
            sdk_order_id=None,
            status=OrderStatus.FILLED,
            event_time=datetime.now(timezone.utc),
        )
    )
