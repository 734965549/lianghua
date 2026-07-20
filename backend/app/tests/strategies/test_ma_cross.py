from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.schemas.enums import Market, OrderSide
from app.sdk.models import KlineBar
from app.strategies.context import StrategyContext
from app.strategies.registry import import_samples
from app.strategies.registry import get_strategy_class


@pytest.fixture
def ma_cross_strategy():
    import_samples()
    cls = get_strategy_class("ma_cross")
    params = {
        "symbols": ["600000.SH"],
        "interval": "1m",
        "fast": 2,
        "slow": 3,
        "quantity": "100",
    }
    return cls(params)


def _make_bars(closes: list[Decimal], symbol: str = "600000.SH") -> list[KlineBar]:
    base = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    bars = []
    for i, close in enumerate(closes):
        bars.append(
            KlineBar(
                symbol=symbol,
                market=Market.STOCK,
                interval="1m",
                bar_time=base + timedelta(minutes=i),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=Decimal("1000"),
            )
        )
    return bars


def test_ma_cross_golden_cross_emits_buy(ma_cross_strategy):
    submitted = []

    def sink(**kwargs):
        submitted.append(kwargs)

    ctx = StrategyContext(
        strategy_id="ma_cross",
        run_id="test-run",
        parameters={"symbols": ["600000.SH"], "fast": 2, "slow": 3, "quantity": "100"},
        market_data_reader=type("R", (), {"get_klines": lambda *a, **k: [], "get_quote": lambda *a, **k: None})(),
        account_reader=type("A", (), {"get_position": lambda *a, **k: None, "get_account": lambda *a, **k: {}})(),
        signal_sink=sink,
        logger=lambda *a, **k: None,
    )
    ma_cross_strategy.on_start(ctx)

    # 预热：10, 10, 10 -> fast=slow=10
    for bar in _make_bars([Decimal("10"), Decimal("10"), Decimal("10")]):
        ma_cross_strategy.on_bar(bar)
    assert submitted == []

    # 金叉：上一根 fast<=slow，当前 fast>slow
    bar = _make_bars([Decimal("12")])[-1]
    ma_cross_strategy.on_bar(bar)
    assert len(submitted) == 1
    assert submitted[0]["side"] == OrderSide.BUY
    assert submitted[0]["symbol"] == "600000.SH"


def test_ma_cross_death_cross_emits_sell(ma_cross_strategy):
    submitted = []

    def sink(**kwargs):
        submitted.append(kwargs)

    ctx = StrategyContext(
        strategy_id="ma_cross",
        run_id="test-run",
        parameters={"symbols": ["600000.SH"], "fast": 2, "slow": 3, "quantity": "100"},
        market_data_reader=type("R", (), {"get_klines": lambda *a, **k: [], "get_quote": lambda *a, **k: None})(),
        account_reader=type("A", (), {"get_position": lambda *a, **k: None, "get_account": lambda *a, **k: {}})(),
        signal_sink=sink,
        logger=lambda *a, **k: None,
    )
    ma_cross_strategy.on_start(ctx)

    for bar in _make_bars([Decimal("12"), Decimal("12"), Decimal("12")]):
        ma_cross_strategy.on_bar(bar)

    bar = _make_bars([Decimal("8")])[-1]
    ma_cross_strategy.on_bar(bar)
    assert len(submitted) == 1
    assert submitted[0]["side"] == OrderSide.SELL
