"""规则 DSL 校验与求值测试。"""

from decimal import Decimal

from app.strategies.indicators.moving_average import SMAIndicator
from app.strategies.rule_evaluator import RuleEvaluator
from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION
from app.strategies.rule_validator import RuleValidator


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
    slow = SMAIndicator(period=2, source="close")
    # 预热：使 fast 从下方穿越 slow
    from datetime import datetime, timezone
    from app.schemas.enums import Market
    from app.sdk.models import KlineBar

    bars = [
        KlineBar("600000.SH", Market.STOCK, "1d", datetime(2023, 1, 1, tzinfo=timezone.utc),
                 Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10"), Decimal("1")),
        KlineBar("600000.SH", Market.STOCK, "1d", datetime(2023, 1, 2, tzinfo=timezone.utc),
                 Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10"), Decimal("1")),
        KlineBar("600000.SH", Market.STOCK, "1d", datetime(2023, 1, 3, tzinfo=timezone.utc),
                 Decimal("15"), Decimal("15"), Decimal("15"), Decimal("15"), Decimal("1")),
    ]
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
