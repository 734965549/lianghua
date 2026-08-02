"""扩展指标与风控测试。"""

from decimal import Decimal

from app.strategies.indicators.base import IndicatorRegistry, create_indicator_from_def
from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION
from app.strategies.rule_validator import RuleValidator


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
