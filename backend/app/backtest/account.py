from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict


@dataclass
class Position:
    symbol: str
    quantity: Decimal = Decimal("0")
    avg_cost: Decimal = Decimal("0")

    def market_value(self, price: Decimal) -> Decimal:
        return self.quantity * price

    def apply_buy(self, quantity: Decimal, price: Decimal) -> None:
        total_cost = self.quantity * self.avg_cost + quantity * price
        self.quantity += quantity
        if self.quantity > 0:
            self.avg_cost = total_cost / self.quantity

    def apply_sell(self, quantity: Decimal, price: Decimal) -> Decimal:
        """返回已实现盈亏。"""
        realized = (price - self.avg_cost) * quantity
        self.quantity -= quantity
        if self.quantity <= 0:
            self.avg_cost = Decimal("0")
        return realized


@dataclass
class SimulationAccount:
    initial_cash: Decimal
    cash: Decimal = field(init=False)
    positions: Dict[str, Position] = field(default_factory=dict)
    realized_pnl: Decimal = Decimal("0")

    def __post_init__(self):
        self.cash = self.initial_cash

    def get_position(self, symbol: str) -> Position | None:
        return self.positions.get(symbol)

    def get_account(self) -> dict:
        return {
            "available_cash": str(self.cash),
            "total_asset": str(self.total_asset()),
        }

    def total_asset(self, prices: dict[str, Decimal] | None = None) -> Decimal:
        total = self.cash
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, Decimal("0")) if prices else Decimal("0")
            total += pos.market_value(price)
        return total

    def apply_fill(self, symbol: str, side: str, quantity: Decimal, price: Decimal, commission: Decimal, tax: Decimal) -> None:
        amount = quantity * price
        pos = self.positions.setdefault(symbol, Position(symbol=symbol))
        if side == "buy":
            pos.apply_buy(quantity, price)
            self.cash -= amount + commission + tax
        else:
            realized = pos.apply_sell(quantity, price)
            self.realized_pnl += realized
            self.cash += amount - commission - tax
