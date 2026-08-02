from decimal import Decimal

import pytest

from app.backtest.account import Position, SimulationAccount


@pytest.fixture
def account() -> SimulationAccount:
    return SimulationAccount(initial_cash=Decimal("100000"))


def test_initial_state(account: SimulationAccount) -> None:
    assert account.cash == Decimal("100000")
    assert account.total_asset() == Decimal("100000")
    assert account.realized_pnl == Decimal("0")


def test_apply_buy(account: SimulationAccount) -> None:
    account.apply_fill(
        symbol="600519.SH",
        side="buy",
        quantity=Decimal("100"),
        price=Decimal("1000"),
        commission=Decimal("30"),
        tax=Decimal("0"),
    )
    assert account.cash == Decimal("100000") - Decimal("100000") - Decimal("30")
    pos = account.get_position("600519.SH")
    assert pos is not None
    assert pos.quantity == Decimal("100")
    assert pos.avg_cost == Decimal("1000")


def test_apply_sell_realized_pnl(account: SimulationAccount) -> None:
    account.apply_fill(
        symbol="600519.SH",
        side="buy",
        quantity=Decimal("100"),
        price=Decimal("1000"),
        commission=Decimal("30"),
        tax=Decimal("0"),
    )
    account.apply_fill(
        symbol="600519.SH",
        side="sell",
        quantity=Decimal("100"),
        price=Decimal("1100"),
        commission=Decimal("33"),
        tax=Decimal("110"),
    )
    assert account.realized_pnl == Decimal("10000")
    assert account.cash == Decimal("100000") - Decimal("100000") - Decimal("30") + Decimal("110000") - Decimal("33") - Decimal("110")
    pos = account.get_position("600519.SH")
    assert pos is not None
    assert pos.quantity == Decimal("0")


def test_total_asset_with_prices(account: SimulationAccount) -> None:
    account.apply_fill(
        symbol="600519.SH",
        side="buy",
        quantity=Decimal("100"),
        price=Decimal("1000"),
        commission=Decimal("0"),
        tax=Decimal("0"),
    )
    total = account.total_asset({"600519.SH": Decimal("1200")})
    assert total == Decimal("100000") - Decimal("100000") + Decimal("120000")


def test_position_market_value() -> None:
    pos = Position(symbol="000001.SZ", quantity=Decimal("500"), avg_cost=Decimal("10"))
    assert pos.market_value(Decimal("12")) == Decimal("6000")
