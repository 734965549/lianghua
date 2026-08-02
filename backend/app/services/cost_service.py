from dataclasses import dataclass
from decimal import Decimal

from app.schemas.enums import Market, OrderSide


@dataclass
class CostResult:
    commission: Decimal
    stamp_tax: Decimal
    transfer_fee: Decimal
    margin: Decimal
    total_fee: Decimal


class CostService:
    """交易成本计算器。

    股票：佣金 + 过户费（双向），印花税（卖出）。
    期货：佣金 + 保证金（占用，非费用）。
    """

    def __init__(
        self,
        *,
        commission_rate: Decimal = Decimal("0.0003"),
        min_commission: Decimal = Decimal("5"),
        stamp_tax_rate: Decimal = Decimal("0.001"),
        transfer_fee_rate: Decimal = Decimal("0.00001"),
        futures_margin_rate: Decimal = Decimal("0.12"),
        futures_commission_per_lot: Decimal = Decimal("10"),
    ):
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.stamp_tax_rate = stamp_tax_rate
        self.transfer_fee_rate = transfer_fee_rate
        self.futures_margin_rate = futures_margin_rate
        self.futures_commission_per_lot = futures_commission_per_lot

    def calculate(
        self,
        *,
        market: Market,
        side: OrderSide,
        price: Decimal,
        quantity: Decimal,
    ) -> CostResult:
        amount = price * quantity
        commission = max(amount * self.commission_rate, self.min_commission)

        if market == Market.STOCK:
            stamp_tax = amount * self.stamp_tax_rate if side == OrderSide.SELL else Decimal("0")
            transfer_fee = amount * self.transfer_fee_rate
            margin = Decimal("0")
        elif market == Market.FUTURES:
            stamp_tax = Decimal("0")
            transfer_fee = Decimal("0")
            commission = self.futures_commission_per_lot * quantity
            margin = amount * self.futures_margin_rate
        else:
            stamp_tax = Decimal("0")
            transfer_fee = Decimal("0")
            margin = Decimal("0")

        return CostResult(
            commission=commission,
            stamp_tax=stamp_tax,
            transfer_fee=transfer_fee,
            margin=margin,
            total_fee=commission + stamp_tax + transfer_fee,
        )


cost_service = CostService()
