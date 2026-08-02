"""策略规则 DSL 常量与资源限制。"""

SCHEMA_VERSION = 1
MAX_INDICATORS = 20
MAX_CONDITIONS = 50
MAX_NEST_DEPTH = 5
MAX_PERIOD = 500
MAX_SYMBOLS = 20
MAX_CONCURRENT_POSITIONS = 10
MAX_FORMULAS = 10
MAX_FORMULA_LENGTH = 200

COMPARISON_OPERATORS = {"gt", "gte", "lt", "lte", "eq"}
CROSS_OPERATORS = {"cross_above", "cross_below"}
TREND_OPERATORS = {"rising", "falling"}
ALL_OPERATORS = COMPARISON_OPERATORS | CROSS_OPERATORS | TREND_OPERATORS | {"between"}

INDICATOR_TYPES_V1 = {
    "sma", "ema", "rsi", "macd", "bollinger", "atr", "roc", "volume_sma",
}
INDICATOR_TYPES_NO_PERIOD = {"macd"}

INDICATOR_OUTPUTS: dict[str, set[str]] = {
    "sma": {"value"},
    "ema": {"value"},
    "rsi": {"value"},
    "macd": {"value", "signal", "histogram"},
    "bollinger": {"value", "upper", "lower"},
    "atr": {"value"},
    "roc": {"value"},
    "volume_sma": {"value"},
}
OHLCV_SOURCES = {"open", "high", "low", "close", "volume"}

OPERATOR_CATALOG = [
    {"operator": "gt", "label": "大于", "arity": 2},
    {"operator": "gte", "label": "大于等于", "arity": 2},
    {"operator": "lt", "label": "小于", "arity": 2},
    {"operator": "lte", "label": "小于等于", "arity": 2},
    {"operator": "eq", "label": "等于", "arity": 2},
    {"operator": "cross_above", "label": "上穿", "arity": 2},
    {"operator": "cross_below", "label": "下穿", "arity": 2},
    {"operator": "between", "label": "介于", "arity": 3},
    {"operator": "rising", "label": "上升", "arity": 1},
    {"operator": "falling", "label": "下降", "arity": 1},
]

FORMULA_OPERATORS = ["+", "-", "*", "/", "(", ")"]
FORMULA_REF_HELP = "@指标[.输出]  $字段  #参数  例: @fast_ma - @slow_ma"

DEFAULT_SYMBOLS_CONFIG = {
    "mode": "runtime",
    "list": [],
    "max_concurrent": 5,
}

DEFAULT_MA_CROSS_DEFINITION = {
    "schema_version": 1,
    "market": "stock",
    "interval": "1d",
    "parameters": {
        "fast": {"type": "integer", "default": 5, "min": 2, "max": 100},
        "slow": {"type": "integer", "default": 20, "min": 3, "max": 300},
        "quantity": {"type": "decimal", "default": "100"},
    },
    "indicators": [
        {
            "id": "fast_ma",
            "type": "sma",
            "source": "close",
            "period": {"parameter": "fast"},
        },
        {
            "id": "slow_ma",
            "type": "sma",
            "source": "close",
            "period": {"parameter": "slow"},
        },
    ],
    "entry_rule": {
        "all": [
            {
                "operator": "cross_above",
                "left": {"indicator": "fast_ma"},
                "right": {"indicator": "slow_ma"},
            }
        ]
    },
    "exit_rule": {
        "any": [
            {
                "operator": "cross_below",
                "left": {"indicator": "fast_ma"},
                "right": {"indicator": "slow_ma"},
            }
        ]
    },
    "execution": {
        "quantity": {"parameter": "quantity"},
        "cooldown_bars": 1,
    },
    "symbols": {
        "mode": "runtime",
        "list": [],
        "max_concurrent": 5,
    },
    "formulas": [],
    "risk": {
        "stop_loss_pct": "5",
        "take_profit_pct": "10",
        "max_position_pct": "30",
    },
}
