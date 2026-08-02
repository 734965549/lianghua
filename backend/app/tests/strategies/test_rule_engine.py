"""规则 DSL 校验与求值测试。"""

from datetime import datetime, timezone
from decimal import Decimal

from app.schemas.enums import Market
from app.sdk.models import KlineBar
from app.strategies.indicators.moving_average import SMAIndicator
from app.strategies.rule_evaluator import RuleEvaluator
from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION
from app.strategies.rule_validator import RuleValidator


def _bar(close: str, idx: int = 0) -> KlineBar:
    c = Decimal(close)
    return KlineBar(
        symbol="600000.SH",
        market=Market.STOCK,
        interval="1d",
        bar_time=datetime(2023, 1, idx + 1, tzinfo=timezone.utc),
        open=c,
        high=c,
        low=c,
        close=c,
        volume=Decimal("1"),
    )


def test_validator_accepts_ma_cross():
    errors = RuleValidator().validate(DEFAULT_MA_CROSS_DEFINITION)
    assert errors == []


def test_validator_rejects_unknown_indicator():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "entry_rule": {
            "all": [
                {
                    "operator": "gt",
                    "left": {"indicator": "unknown"},
                    "right": {"constant": "0"},
                }
            ]
        },
    }
    errors = RuleValidator().validate(definition)
    assert any("unknown" in e for e in errors)


def test_cross_above_truth_table():
    fast = SMAIndicator(period=2, source="close")
    slow = SMAIndicator(period=3, source="close")
    bars = [_bar("10", 0), _bar("10", 1), _bar("10", 2), _bar("15", 3)]
    for bar in bars[:-1]:
        fast.update(bar)
        slow.update(bar)
    fast.update(bars[-1])
    slow.update(bars[-1])

    ev = RuleEvaluator(
        indicators={"fast_ma": fast, "slow_ma": slow},
        parameters={"fast": 2, "slow": 2},
        bar_fields={"close": Decimal("15"), "_prev_close": Decimal("10")},
    )
    result = ev.evaluate(
        {
            "operator": "cross_above",
            "left": {"indicator": "fast_ma"},
            "right": {"indicator": "slow_ma"},
        }
    )
    assert result is True


def test_nested_all_rule():
    ev = RuleEvaluator(
        indicators={},
        parameters={},
        bar_fields={"close": Decimal("5"), "_prev_close": Decimal("4")},
    )
    assert ev.evaluate(
        {"all": [{"operator": "gt", "left": {"field": "close"}, "right": {"constant": "3"}}]}
    )
