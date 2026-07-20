from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.repositories.account_repo import AccountRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.trade_repo import TradeRepository
from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction
from app.sdk.models import TradeUpdateEvent
from app.services.trade_service import trade_service


@pytest.mark.integration
def test_trade_idempotent(db):
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    now = datetime.now(timezone.utc)
    client_order_id = f"lh_{now:%Y%m%d}_{uuid4().hex[:8]}"

    order_repo = OrderRepository(db)
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
        status=OrderStatus.SUBMITTED,
        submitted_at=now,
    )
    sdk_order_id = f"MOCK_SDK_{uuid4().hex[:8]}"
    order.sdk_order_id = sdk_order_id
    db.commit()

    event = TradeUpdateEvent(
        sdk_trade_id=f"MOCKT_DUP_{uuid4().hex[:8]}",
        client_order_id=client_order_id,
        sdk_order_id=sdk_order_id,
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        price=Decimal("10.05"),
        quantity=Decimal("50"),
        trade_time=now,
    )

    trade_service.on_trade_update(event)
    trade_service.on_trade_update(event)

    trades, total = TradeRepository(db).list_trades(client_order_id=client_order_id, limit=10)
    assert total == 1
    assert trades[0].sdk_trade_id == event.sdk_trade_id

    db.refresh(order)
    assert Decimal(str(order.filled_quantity)) == Decimal("50")
