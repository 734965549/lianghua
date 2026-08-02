from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from app.core.trading_calendar import shanghai_day_bounds
from app.repositories.account_repo import AccountRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.trade_repo import TradeRepository
from app.schemas.enums import (
    Market,
    OrderSide,
    OrderStatus,
    PriceType,
    SignalAction,
)


def _create_order(db, account_id, status: OrderStatus):
    return OrderRepository(db).create_order(
        client_order_id=f"scope_{status.value}_{uuid4().hex[:8]}",
        account_id=account_id,
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
    )


def test_order_scopes_keep_activity_cancellable_only(client, db):
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    for status in (
        OrderStatus.SUBMITTED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.SUBMITTING,
        OrderStatus.UNKNOWN,
        OrderStatus.FILLED,
    ):
        _create_order(db, account.id, status)
    db.commit()

    active = client.get("/api/orders", params={"scope": "active", "page_size": 50})
    attention = client.get(
        "/api/orders", params={"scope": "attention", "page_size": 50}
    )
    all_orders = client.get(
        "/api/orders", params={"scope": "all", "page_size": 50}
    )

    assert active.status_code == 200
    active_data = active.json()["data"]
    assert active_data["scope_label"] == "仅可撤委托"
    assert {row["status"] for row in active_data["items"]} == {
        "submitted",
        "partially_filled",
    }
    assert {row["status"] for row in attention.json()["data"]["items"]} == {
        "submitting",
        "unknown",
    }
    assert all_orders.json()["data"]["total"] == 5


def test_trade_scope_explicitly_separates_today_and_all(client, db):
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    today_start, _ = shanghai_day_bounds()
    repo = TradeRepository(db)
    repo.create_trade(
        sdk_trade_id=f"today_{uuid4().hex[:8]}",
        client_order_id=f"today_order_{uuid4().hex[:8]}",
        sdk_order_id=None,
        account_id=account.id,
        strategy_id="ma_cross",
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        price=Decimal("10"),
        quantity=Decimal("100"),
        fee=Decimal("1"),
        trade_time=today_start + timedelta(hours=1),
    )
    repo.create_trade(
        sdk_trade_id=f"old_{uuid4().hex[:8]}",
        client_order_id=f"old_order_{uuid4().hex[:8]}",
        sdk_order_id=None,
        account_id=account.id,
        strategy_id="ma_cross",
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.SELL,
        price=Decimal("10"),
        quantity=Decimal("100"),
        fee=Decimal("1"),
        trade_time=today_start - timedelta(days=1),
    )
    db.commit()

    today = client.get("/api/trades", params={"scope": "today", "page_size": 50})
    all_trades = client.get(
        "/api/trades", params={"scope": "all", "page_size": 50}
    )

    today_data = today.json()["data"]
    all_data = all_trades.json()["data"]
    assert today_data["scope_label"] == "今日成交（上海时区）"
    assert today_data["timezone"] == "Asia/Shanghai"
    assert today_data["total"] == 1
    assert all_data["scope_label"] == "全部成交"
    assert all_data["total"] == 2
