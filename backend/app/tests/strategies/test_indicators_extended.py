"""扩展指标与风控测试。"""

from datetime import datetime, timezone
from decimal import Decimal

from app.schemas.enums import Market
from app.sdk.models import KlineBar
from app.strategies.indicators.base import IndicatorRegistry, create_indicator_from_def
from app.strategies.indicators.trend import ADXIndicator
from app.strategies.indicators.volume import OBVIndicator, VWAPIndicator
from app.strategies.rule_evaluator import RuleEvaluator
from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION, INDICATOR_TYPES_V1
from app.strategies.rule_validator import RuleValidator


def _bar(close: str, idx: int = 0, *, vol: str = "1000") -> KlineBar:
    c = Decimal(close)
    return KlineBar(
        symbol="600000.SH",
        market=Market.STOCK,
        interval="1d",
        bar_time=datetime(2023, 1, idx + 1, tzinfo=timezone.utc),
        open=c,
        high=c + Decimal("0.5"),
        low=c - Decimal("0.5"),
        close=c,
        volume=Decimal(vol),
    )


def test_indicator_catalog_period_not_in_params():
    catalog = {item["type"]: item for item in IndicatorRegistry.catalog()}
    for ind_type in ("sma", "ema", "rsi", "atr", "roc", "kdj", "volume_sma", "bollinger"):
        meta = catalog[ind_type]
        assert meta.get("requires_period") is True
        assert "period" in meta
        param_names = {p["name"] for p in meta.get("params", [])}
        assert "period" not in param_names


def test_macd_definition_validate():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "indicators": [
            {
                "id": "macd_line",
                "type": "macd",
                "source": "close",
                "params": {"fast": 12, "slow": 26, "signal": 9},
            }
        ],
        "entry_rule": {
            "all": [
                {
                    "operator": "cross_above",
                    "left": {"indicator": "macd_line", "output": "value"},
                    "right": {"indicator": "macd_line", "output": "signal"},
                }
            ]
        },
        "exit_rule": {
            "all": [
                {"operator": "gt", "left": {"constant": "1"}, "right": {"constant": "2"}}
            ]
        },
    }
    errors = RuleValidator().validate(definition)
    assert errors == []


def test_bollinger_output_reference():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "indicators": [
            {
                "id": "bb",
                "type": "bollinger",
                "source": "close",
                "period": 20,
                "params": {"std_dev": "2"},
            }
        ],
        "entry_rule": {
            "all": [
                {
                    "operator": "lt",
                    "left": {"field": "close"},
                    "right": {"indicator": "bb", "output": "lower"},
                }
            ]
        },
        "exit_rule": {
            "all": [
                {"operator": "gt", "left": {"constant": "1"}, "right": {"constant": "2"}}
            ]
        },
    }
    errors = RuleValidator().validate(definition)
    assert errors == []


def test_execution_quantity_pct():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "execution": {
            "quantity_pct": {"constant": "30"},
            "cooldown_bars": 1,
        },
    }
    errors = RuleValidator().validate(definition)
    assert errors == []


def test_create_macd_from_def():
    ind = create_indicator_from_def(
        {
            "id": "m",
            "type": "macd",
            "source": "close",
            "params": {"fast": 3, "slow": 5, "signal": 2},
        },
        {},
    )
    assert ind.warmup_bars >= 5


def test_kdj_definition_validate():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "indicators": [
            {
                "id": "kdj_main",
                "type": "kdj",
                "source": "close",
                "period": 9,
            }
        ],
        "entry_rule": {
            "all": [
                {
                    "operator": "cross_above",
                    "left": {"indicator": "kdj_main", "output": "k"},
                    "right": {"indicator": "kdj_main", "output": "d"},
                }
            ]
        },
        "exit_rule": {
            "any": [
                {
                    "operator": "cross_below",
                    "left": {"indicator": "kdj_main", "output": "k"},
                    "right": {"indicator": "kdj_main", "output": "d"},
                }
            ]
        },
    }
    errors = RuleValidator().validate(definition)
    assert errors == []


def test_create_kdj_from_def():
    ind = create_indicator_from_def(
        {
            "id": "k",
            "type": "kdj",
            "source": "close",
            "period": 3,
        },
        {},
    )
    assert ind.warmup_bars == 3


def test_htf_interval_on_indicator_validate():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "interval": "5m",
        "indicators": [
            {
                "id": "sma_20",
                "type": "sma",
                "source": "close",
                "period": 20,
                "interval": "1d",
            },
            {
                "id": "kdj",
                "type": "kdj",
                "source": "close",
                "period": 9,
            },
        ],
        "entry_rule": {
            "all": [
                {
                    "operator": "gt",
                    "left": {"field": "close"},
                    "right": {"indicator": "sma_20", "output": "value"},
                },
                {
                    "operator": "gt",
                    "left": {"indicator": "kdj", "output": "j"},
                    "right": {"constant": "80"},
                },
            ]
        },
        "exit_rule": {
            "all": [
                {
                    "operator": "gt",
                    "left": {"constant": "1"},
                    "right": {"constant": "2"},
                }
            ]
        },
    }
    assert RuleValidator().validate(definition) == []


def test_indicator_catalog_covers_all_types():
    catalog_types = {item["type"] for item in IndicatorRegistry.catalog()}
    assert catalog_types == INDICATOR_TYPES_V1
    assert len(catalog_types) == 26


def test_adx_outputs():
    ind = ADXIndicator(period=3, source="close")
    for i, c in enumerate(["10", "11", "12", "13", "14", "15", "16"]):
        ind.update(_bar(c, i))
    assert ind.get_output("plus_di") is not None
    assert ind.get_output("minus_di") is not None


def test_obv_cumulative():
    ind = OBVIndicator(source="close")
    for i, c in enumerate(["10", "11", "10", "12"]):
        ind.update(_bar(c, i, vol=str(1000 + i * 100)))
    assert ind.ready
    assert ind.value is not None


def test_vwap_rolling():
    ind = VWAPIndicator(period=3, source="close")
    for i, c in enumerate(["10", "11", "12", "13"]):
        ind.update(_bar(c, i))
    assert ind.ready
    assert ind.value is not None


def test_adx_definition_validate():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "indicators": [{"id": "adx_main", "type": "adx", "source": "close", "period": 14}],
        "entry_rule": {
            "all": [
                {"operator": "gt", "left": {"indicator": "adx_main"}, "right": {"constant": "25"}},
                {"operator": "gt", "left": {"indicator": "adx_main", "output": "plus_di"},
                 "right": {"indicator": "adx_main", "output": "minus_di"}},
            ]
        },
        "exit_rule": {
            "all": [
                {"operator": "gt", "left": {"constant": "1"}, "right": {"constant": "2"}}
            ]
        },
    }
    assert RuleValidator().validate(definition) == []


def test_new_operators_validate():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "entry_rule": {
            "all": [
                {"operator": "no_position"},
                {"operator": "bar_since_gte", "bars": 3},
                {"operator": "percent_change_gte", "operand": {"field": "close"}, "right": {"constant": "2"}},
                {"operator": "gt", "left": {"field": "close"},
                 "right": {"field": "high", "lookback": 20}},
            ]
        },
        "exit_rule": {
            "all": [
                {"operator": "gt", "left": {"constant": "1"}, "right": {"constant": "2"}}
            ]
        },
    }
    assert RuleValidator().validate(definition) == []


def test_has_position_evaluator():
    ev = RuleEvaluator(
        indicators={},
        parameters={},
        bar_fields={},
        has_position=True,
    )
    assert ev.evaluate({"operator": "has_position"})
    assert not ev.evaluate({"operator": "no_position"})


def test_rolling_field_evaluator():
    ev = RuleEvaluator(
        indicators={},
        parameters={},
        bar_fields={"close": Decimal("21")},
        rolling_fields={"high:3": Decimal("20"), "_prev_high:3": Decimal("18")},
    )
    assert ev.evaluate(
        {"operator": "gt", "left": {"field": "close"}, "right": {"field": "high", "lookback": 3}}
    )


def test_invalid_indicator_interval_rejected():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "indicators": [
            {
                "id": "sma_20",
                "type": "sma",
                "source": "close",
                "period": 20,
                "interval": "",
            }
        ],
    }
    errors = RuleValidator().validate(definition)
    assert any("interval" in e for e in errors)
