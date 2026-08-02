from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterator

import pytest

from app.backtest.data_source import HistoricalDataSource, MarketEvent
from app.backtest.models import BacktestCreateRequest
from app.backtest.runner import BacktestRunner
from app.schemas.enums import FillModel, Granularity, Market
from app.sdk.models import KlineBar


class InMemoryKlineSource(HistoricalDataSource):
    """内存 K 线数据源，避免测试依赖数据库。"""

    def __init__(self, bars: list[KlineBar]) -> None:
        self.bars = bars

    def load_events(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval: str,
    ) -> Iterator[MarketEvent]:
        for bar in self.bars:
            if start <= bar.bar_time <= end and bar.symbol in symbols:
                yield MarketEvent(event_time=bar.bar_time, symbol=bar.symbol, bar=bar)


def make_bars(symbol: str, start_price: Decimal, count: int) -> list[KlineBar]:
    bars: list[KlineBar] = []
    price = start_price
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        close = price + Decimal(str(i % 3 - 1))  # 小幅波动
        bars.append(
            KlineBar(
                symbol=symbol,
                market=Market.STOCK,
                interval="1d",
                bar_time=base_time + timedelta(days=i),
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=close,
                volume=Decimal("10000"),
            )
        )
        price = close
    return bars


def test_runner_basic_workflow() -> None:
    bars = make_bars("600519.SH", Decimal("100"), 10)
    source = InMemoryKlineSource(bars)

    request = BacktestCreateRequest(
        strategy_id="grid_trading",
        symbols=["600519.SH"],
        start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2024, 1, 10, tzinfo=timezone.utc),
        initial_cash=Decimal("100000"),
        granularity=Granularity.KLINE,
        fill_model=FillModel.NEXT_CLOSE,
        interval="1d",
        parameters={"symbols": ["600519.SH"], "interval": "1d", "grid_size": "2", "quantity": "100"},
    )

    runner = BacktestRunner(request, db=None)  # type: ignore[arg-type]
    # 注入内存数据源
    runner._build_data_source = lambda: source  # type: ignore[method-assign]

    result = runner.run()
    assert result.status.value == "completed"
    assert result.initial_cash == Decimal("100000")
    assert result.final_equity is not None
    assert result.metrics is not None
    assert result.equity_curve
    assert len(result.trades) >= 0


def test_runner_unknown_strategy() -> None:
    request = BacktestCreateRequest(
        strategy_id="non_existent_strategy",
        symbols=["600519.SH"],
        start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    runner = BacktestRunner(request, db=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="策略不存在"):
        runner.run()


def test_runner_records_equity_curve() -> None:
    bars = make_bars("600519.SH", Decimal("100"), 5)
    source = InMemoryKlineSource(bars)
    request = BacktestCreateRequest(
        strategy_id="grid_trading",
        symbols=["600519.SH"],
        start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2024, 1, 5, tzinfo=timezone.utc),
        initial_cash=Decimal("100000"),
        granularity=Granularity.KLINE,
        fill_model=FillModel.NEXT_CLOSE,
        interval="1d",
        parameters={"symbols": ["600519.SH"], "interval": "1d", "grid_size": "10", "quantity": "100"},
    )
    runner = BacktestRunner(request, db=None)  # type: ignore[arg-type]
    runner._build_data_source = lambda: source  # type: ignore[method-assign]
    result = runner.run()
    assert len(result.equity_curve) == 5
    assert result.equity_curve[0].equity == Decimal("100000")
