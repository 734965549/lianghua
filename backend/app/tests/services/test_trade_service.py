"""trade_service 提交 / 撤单 / 成交回报覆盖补测。"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import MagicMock

import pytest

from app.api.response import BizError
from app.repositories.account_repo import AccountRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.risk_repo import RiskRepository
from app.repositories.trade_repo import TradeRepository
from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, RiskResult, SignalAction
from app.sdk import manager as sdk_manager
from app.sdk.base import SDKOrderRejected
from app.sdk.models import CancelOrderResult, PlaceOrderResult, TradeUpdateEvent
from app.services.trade_service import _decimal_str, trade_service, trade_to_dict


def _seed_account(db):
    return AccountRepository(db).get_or_create_default(Market.STOCK)


def _seed_passed_risk(db, client_order_id: str):
    return RiskRepository(db).add_check(
        signal_id=None,
        client_order_id=client_order_id,
        result=RiskResult.PASSED,
        rule_code="",
        reason="all rules passed",
        checked_at=datetime.now(timezone.utc),
        snapshot={},
    )


def _create_order(db, *, status=OrderStatus.SUBMITTING, client_order_id=None, sdk_order_id=None):
    account = _seed_account(db)
    now = datetime.now(timezone.utc)
    cid = client_order_id or f"lh_{now:%Y%m%d}_{uuid4().hex[:8]}"
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
        status=status,
        submitted_at=now,
    )
    if sdk_order_id:
        order.sdk_order_id = sdk_order_id
    db.commit()
    return order


@pytest.mark.unit
def test_decimal_str_helpers():
    assert _decimal_str(None) == "0"
    assert _decimal_str(Decimal("1.5")) == "1.5"
    assert _decimal_str(2.5) == "2.5"


@pytest.mark.integration
def test_submit_order_not_found(db, reset_system_state):
    with pytest.raises(BizError) as exc:
        trade_service.submit(uuid4(), correlation_id="missing")
    assert exc.value.code == "ORDER_NOT_FOUND"


@pytest.mark.integration
def test_submit_skips_non_submitting(db, reset_system_state):
    order = _create_order(db, status=OrderStatus.SUBMITTED)
    result = trade_service.submit(order.id, correlation_id="skip")
    assert result.status == OrderStatus.SUBMITTED


@pytest.mark.integration
def test_submit_rejects_without_passed_risk(db, reset_system_state):
    """P0-2：缺少 passed 风控记录时禁止提交，订单置 FAILED。"""
    order = _create_order(db, status=OrderStatus.SUBMITTING)
    order_id = order.id
    # 故意不调用 _seed_passed_risk
    result = trade_service.submit(order_id, correlation_id="no_passed_risk")
    assert result.status == OrderStatus.FAILED
    assert "缺少通过的风控记录" in (result.fail_reason or "")
    # 测试会话可能缓存旧对象，expire 后重读
    db.expire_all()
    persisted = OrderRepository(db).get_by_id(order_id)
    assert persisted is not None
    assert persisted.status == OrderStatus.FAILED
    assert "缺少通过的风控记录" in (persisted.fail_reason or "")


@pytest.mark.integration
def test_submit_adapter_error(db, reset_system_state, monkeypatch):
    order = _create_order(db)
    _seed_passed_risk(db, order.client_order_id)
    db.commit()

    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()

    def boom(_req):
        raise SDKOrderRejected("注入 AdapterError")

    monkeypatch.setattr(adapter, "place_order", boom)
    result = trade_service.submit(order.id, correlation_id="adapter_err")
    assert result.status == OrderStatus.FAILED
    assert "注入 AdapterError" in (result.fail_reason or "")
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_submit_generic_exception(db, reset_system_state, monkeypatch):
    order = _create_order(db)
    _seed_passed_risk(db, order.client_order_id)
    db.commit()

    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()

    def boom(_req):
        raise RuntimeError("unexpected boom")

    monkeypatch.setattr(adapter, "place_order", boom)
    result = trade_service.submit(order.id, correlation_id="generic_err")
    assert result.status == OrderStatus.FAILED
    assert "unexpected boom" in (result.fail_reason or "")
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_submit_success_with_raw_payload(db, reset_system_state, monkeypatch):
    order = _create_order(db)
    _seed_passed_risk(db, order.client_order_id)
    db.commit()

    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()

    def fake_place(req):
        return PlaceOrderResult(
            success=True,
            client_order_id=req.client_order_id,
            sdk_order_id="MOCK_RAW_1",
            status=OrderStatus.SUBMITTED,
            message="ok",
            raw_payload={"channel": "test"},
        )

    monkeypatch.setattr(adapter, "place_order", fake_place)
    result = trade_service.submit(order.id, correlation_id="raw")
    assert result.status == OrderStatus.SUBMITTED
    assert result.sdk_order_id == "MOCK_RAW_1"
    assert result.raw_payload == {"channel": "test"}
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_submit_order_missing_after_place(db, reset_system_state, monkeypatch):
    order = _create_order(db)
    _seed_passed_risk(db, order.client_order_id)
    db.commit()

    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()

    monkeypatch.setattr(
        adapter,
        "place_order",
        lambda req: PlaceOrderResult(
            success=True,
            client_order_id=req.client_order_id,
            sdk_order_id="MOCK_GONE",
            status=OrderStatus.SUBMITTED,
        ),
    )
    monkeypatch.setattr(
        OrderRepository,
        "get_by_client_order_id",
        lambda self, cid: None,
    )
    with pytest.raises(BizError) as exc:
        trade_service.submit(order.id, correlation_id="gone")
    assert exc.value.code == "ORDER_NOT_FOUND"
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_cancel_success(db, reset_system_state, monkeypatch):
    order = _create_order(db, status=OrderStatus.SUBMITTED, sdk_order_id="MOCK_CXL_1")
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
            message="ok",
        ),
    )
    result = trade_service.cancel(order.client_order_id, reason="user_cancel", correlation_id="cxl")
    assert result.status == OrderStatus.CANCELLED
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_cancel_not_found(db, reset_system_state):
    with pytest.raises(BizError) as exc:
        trade_service.cancel("missing_cid", correlation_id="cxl_miss")
    assert exc.value.code == "ORDER_NOT_FOUND"


@pytest.mark.integration
def test_cancel_adapter_error(db, reset_system_state, monkeypatch):
    order = _create_order(db, status=OrderStatus.SUBMITTED, sdk_order_id="MOCK_CXL_ERR")
    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()

    def boom(_req):
        raise SDKOrderRejected("撤单被拒")

    monkeypatch.setattr(adapter, "cancel_order", boom)
    with pytest.raises(BizError) as exc:
        trade_service.cancel(order.client_order_id, correlation_id="cxl_err")
    assert exc.value.code == "ORDER_CANCEL_FAILED"
    assert "撤单被拒" in exc.value.message
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_cancel_generic_exception(db, reset_system_state, monkeypatch):
    order = _create_order(db, status=OrderStatus.SUBMITTED, sdk_order_id="MOCK_CXL_EX")
    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()

    def boom(_req):
        raise RuntimeError("cancel boom")

    monkeypatch.setattr(adapter, "cancel_order", boom)
    with pytest.raises(BizError) as exc:
        trade_service.cancel(order.client_order_id, correlation_id="cxl_ex")
    assert exc.value.code == "ORDER_CANCEL_FAILED"
    assert "cancel boom" in exc.value.message
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_cancel_order_missing_after_sdk(db, reset_system_state, monkeypatch):
    order = _create_order(db, status=OrderStatus.SUBMITTED, sdk_order_id="MOCK_CXL_GONE")
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
    calls = {"n": 0}
    real_get = OrderRepository.get_by_client_order_id

    def flaky_get(self, cid):
        calls["n"] += 1
        if calls["n"] == 1:
            return real_get(self, cid)
        return None

    monkeypatch.setattr(OrderRepository, "get_by_client_order_id", flaky_get)
    with pytest.raises(BizError) as exc:
        trade_service.cancel(order.client_order_id, correlation_id="cxl_gone")
    assert exc.value.code == "ORDER_NOT_FOUND"
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_cancel_commit_generic_exception(db, reset_system_state, monkeypatch):
    order = _create_order(db, status=OrderStatus.SUBMITTED, sdk_order_id="MOCK_CXL_COMMIT")
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
    from app.services import order_service as os_mod

    def boom_transition(o, st):
        raise RuntimeError("transition boom")

    monkeypatch.setattr(os_mod.order_service, "transition", boom_transition)
    with pytest.raises(RuntimeError, match="transition boom"):
        trade_service.cancel(order.client_order_id, correlation_id="cxl_boom")
    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_on_trade_update_by_sdk_order_id(db, reset_system_state):
    sdk_oid = f"MOCK_SDK_{uuid4().hex[:8]}"
    order = _create_order(db, status=OrderStatus.SUBMITTED, sdk_order_id=sdk_oid)
    order_id = order.id
    client_order_id = order.client_order_id
    now = datetime.now(timezone.utc)
    event = TradeUpdateEvent(
        sdk_trade_id=f"MOCKT_SDK_{uuid4().hex[:8]}",
        client_order_id=None,
        sdk_order_id=sdk_oid,
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        price=Decimal("10.1"),
        quantity=Decimal("100"),
        trade_time=now,
    )
    trade_service.on_trade_update(event)
    db.expire_all()
    persisted = OrderRepository(db).get_by_id(order_id)
    assert persisted is not None
    assert persisted.status == OrderStatus.FILLED
    trades, total = TradeRepository(db).list_trades(client_order_id=client_order_id, limit=10)
    assert total == 1


@pytest.mark.integration
def test_on_trade_update_order_missing(db, reset_system_state):
    event = TradeUpdateEvent(
        sdk_trade_id=f"MOCKT_MISS_{uuid4().hex[:8]}",
        client_order_id="no_such_order",
        sdk_order_id="no_sdk",
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        price=Decimal("10"),
        quantity=Decimal("10"),
        trade_time=datetime.now(timezone.utc),
    )
    trade_service.on_trade_update(event)  # 不抛异常
    trades, total = TradeRepository(db).list_trades(limit=10)
    assert total == 0


@pytest.mark.integration
def test_on_trade_update_idempotent_skip(db, reset_system_state):
    """同一 sdk_trade_id 重复回报应跳过，不重复落库。"""
    sdk_oid = f"MOCK_IDEM_{uuid4().hex[:8]}"
    order = _create_order(db, status=OrderStatus.SUBMITTED, sdk_order_id=sdk_oid)
    now = datetime.now(timezone.utc)
    tid = f"MOCKT_IDEM_{uuid4().hex[:8]}"
    event = TradeUpdateEvent(
        sdk_trade_id=tid,
        client_order_id=order.client_order_id,
        sdk_order_id=sdk_oid,
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        price=Decimal("10"),
        quantity=Decimal("100"),
        trade_time=now,
    )
    trade_service.on_trade_update(event)
    trade_service.on_trade_update(event)
    trades, total = TradeRepository(db).list_trades(client_order_id=order.client_order_id, limit=10)
    assert total == 1
    assert trades[0].sdk_trade_id == tid


@pytest.mark.integration
def test_on_trade_update_partial_then_fill_with_transition_fallback(db, reset_system_state, monkeypatch):
    order = _create_order(db, status=OrderStatus.SUBMITTED, sdk_order_id="MOCK_PF")
    order_id = order.id
    client_order_id = order.client_order_id
    now = datetime.now(timezone.utc)

    from app.services import order_service as os_mod

    def flaky_transition(order_obj, new_status):
        # 目标状态失败时不得直接赋值，仅允许标记 UNKNOWN
        if new_status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            raise BizError("ORDER_INVALID_TRANSITION", "forced")
        order_obj.status = new_status

    monkeypatch.setattr(os_mod.order_service, "transition", flaky_transition)

    trade_service.on_trade_update(
        TradeUpdateEvent(
            sdk_trade_id=f"MOCKT_P1_{uuid4().hex[:8]}",
            client_order_id=client_order_id,
            sdk_order_id="MOCK_PF",
            symbol="600000.SH",
            market=Market.STOCK,
            side=OrderSide.BUY,
            price=Decimal("10"),
            quantity=Decimal("40"),
            trade_time=now,
        )
    )
    db.expire_all()
    order = OrderRepository(db).get_by_id(order_id)
    assert order is not None
    assert order.status == OrderStatus.UNKNOWN
    assert order.filled_quantity == Decimal("40")

    trade_service.on_trade_update(
        TradeUpdateEvent(
            sdk_trade_id=f"MOCKT_P2_{uuid4().hex[:8]}",
            client_order_id=client_order_id,
            sdk_order_id="MOCK_PF",
            symbol="600000.SH",
            market=Market.STOCK,
            side=OrderSide.BUY,
            price=Decimal("10"),
            quantity=Decimal("60"),
            trade_time=now,
        )
    )
    db.expire_all()
    order = OrderRepository(db).get_by_id(order_id)
    assert order is not None
    # 已是 UNKNOWN，不再尝试 PARTIALLY_FILLED/FILLED 的非法直写
    assert order.status == OrderStatus.UNKNOWN
    assert order.filled_quantity == Decimal("100")


@pytest.mark.integration
def test_on_trade_update_exception_swallowed(db, reset_system_state, monkeypatch):
    order = _create_order(db, status=OrderStatus.SUBMITTED, sdk_order_id="MOCK_EX")
    order_id = order.id
    monkeypatch.setattr(
        TradeRepository,
        "create_trade",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db fail")),
    )
    trade_service.on_trade_update(
        TradeUpdateEvent(
            sdk_trade_id=f"MOCKT_EX_{uuid4().hex[:8]}",
            client_order_id=order.client_order_id,
            sdk_order_id="MOCK_EX",
            symbol="600000.SH",
            market=Market.STOCK,
            side=OrderSide.BUY,
            price=Decimal("10"),
            quantity=Decimal("10"),
            trade_time=datetime.now(timezone.utc),
        )
    )
    db.expire_all()
    persisted = OrderRepository(db).get_by_id(order_id)
    assert persisted is not None
    assert persisted.status == OrderStatus.SUBMITTED


@pytest.mark.unit
def test_trade_to_dict_decimal_branches():
    row = MagicMock()
    row.id = uuid4()
    row.sdk_trade_id = "t1"
    row.client_order_id = "c1"
    row.sdk_order_id = "s1"
    row.account_id = uuid4()
    row.strategy_id = "ma_cross"
    row.symbol = "600000.SH"
    row.market = Market.STOCK
    row.side = OrderSide.BUY
    row.price = None
    row.quantity = 1.5
    row.fee = Decimal("0.1")
    row.trade_time = datetime.now(timezone.utc)
    row.created_at = datetime.now(timezone.utc)
    d = trade_to_dict(row)
    assert d["price"] == "0"
    assert d["quantity"] == "1.5"
    assert d["fee"] == "0.1"
