"""扩展指标与风控测试。"""

from decimal import Decimal

from app.strategies.indicators.base import IndicatorRegistry, create_indicator_from_def
from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION
from app.strategies.rule_validator import RuleValidator


def test_indicator_catalog_includes_macd():
    types = {item["type"] for item in IndicatorRegistry.catalog()}
    assert "macd" in types
    assert "bollinger" in types
    assert "atr" in types
    assert "roc" in types
    assert "volume_sma" in types


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
