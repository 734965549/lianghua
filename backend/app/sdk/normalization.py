"""SDK 边界数据归一化工具。"""

from decimal import Decimal

from app.schemas.enums import Market


def percentage_points_to_ratio(value: Decimal) -> Decimal:
    """将行情源的百分数值（如 10.07）转换为小数比率（如 0.1007）。"""
    return value / Decimal("100")


def max_abs_change_rate(market: Market | str, symbol: str) -> Decimal:
    """返回保守的市场涨跌幅上限，包含价格取整容差。"""
    market = market if isinstance(market, Market) else Market(market)
    if market == Market.FUTURES:
        return Decimal("0.50")

    bare = symbol.strip().upper().split(".", 1)[0]
    if symbol.upper().endswith(".BJ") or bare.startswith(("4", "8", "9")):
        return Decimal("0.31")
    if bare.startswith(("300", "301", "688")):
        return Decimal("0.21")
    return Decimal("0.11")


def is_plausible_change_rate(
    market: Market | str, symbol: str, value: Decimal
) -> bool:
    return value.is_finite() and abs(value) <= max_abs_change_rate(market, symbol)
