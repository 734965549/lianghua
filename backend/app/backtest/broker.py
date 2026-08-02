import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from app.backtest.account import SimulationAccount
from app.backtest.data_source import MarketEvent
from app.backtest.fill_model import FillModelEngine
from app.backtest.models import BacktestOrderRequest, Fill
from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType
from app.sdk.models import OrderUpdateEvent
from app.services.cost_service import CostService


@dataclass
class BacktestOrder:
    client_order_id: str
    symbol: str
    market: Market
    side: OrderSide
    price_type: PriceType
    quantity: Decimal
    price: Decimal | None = None
    status: OrderStatus = OrderStatus.SUBMITTED
    filled_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = field(init=False)

    def __post_init__(self):
        self.remaining_quantity = self.quantity


class SimulationBroker:
    """模拟经纪商：管理挂单、撮合、维护账户。"""

    def __init__(
        self,
        account: SimulationAccount,
        fill_model: FillModelEngine,
        cost_service: CostService,
        order_update_callback: Callable[[OrderUpdateEvent], None] | None = None,
    ):
        self.account = account
        self.fill_model = fill_model
        self.cost_service = cost_service
        self._orders: dict[str, BacktestOrder] = {}
        self._pending: list[BacktestOrder] = []
        self._fills: list[Fill] = []
        self._order_update_callback = order_update_callback

    def submit_order(self, order_request: BacktestOrderRequest) -> str:
        order = BacktestOrder(
            client_order_id=order_request.client_order_id,
            symbol=order_request.symbol,
            market=order_request.market,
            side=order_request.side,
            price_type=order_request.price_type,
            quantity=order_request.quantity,
            price=order_request.price,
        )
        self._orders[order.client_order_id] = order
        self._pending.append(order)
        return order.client_order_id

    def on_market_event(self, event: MarketEvent) -> list[Fill]:
        """在每个市场事件后尝试撮合所有挂单。"""
        fills: list[Fill] = []
        still_pending: list[BacktestOrder] = []
        for order in self._pending:
            fill = self._try_fill(order, event)
            if fill is not None:
                fills.append(fill)
                self._fills.append(fill)
                self._update_order(order, fill)
                if order.remaining_quantity > 0:
                    still_pending.append(order)
            else:
                still_pending.append(order)
        self._pending = still_pending
        return fills

    def _try_fill(self, order: BacktestOrder, event: MarketEvent) -> Fill | None:
        if order.symbol != event.symbol:
            return None
        fill_price = self.fill_model.can_fill(order, event)
        if fill_price is None:
            return None

        quantity = order.remaining_quantity
        price = fill_price.price
        cost = self.cost_service.calculate(
            market=order.market,
            side=order.side,
            price=price,
            quantity=quantity,
        )

        self.account.apply_fill(
            symbol=order.symbol,
            side=order.side.value,
            quantity=quantity,
            price=price,
            commission=cost.commission,
            tax=cost.stamp_tax + cost.transfer_fee,
        )

        return Fill(
            fill_id=str(uuid.uuid4()),
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            price=price,
            commission=cost.commission,
            tax=cost.stamp_tax + cost.transfer_fee,
            fill_time=event.event_time,
        )

    def _update_order(self, order: BacktestOrder, fill: Fill) -> None:
        order.filled_quantity += fill.quantity
        order.remaining_quantity -= fill.quantity
        if order.remaining_quantity <= 0:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
        if self._order_update_callback:
            event = OrderUpdateEvent(
                client_order_id=order.client_order_id,
                status=order.status,
                filled_quantity=order.filled_quantity,
                remaining_quantity=order.remaining_quantity,
                event_time=fill.fill_time,
            )
            self._order_update_callback(event)

    def get_fills(self) -> list[Fill]:
        return list(self._fills)
