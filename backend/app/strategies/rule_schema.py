"""策略规则 DSL 常量与资源限制。

用户规则策略（kind=rule）的定义 JSON 须符合本模块约束，由 RuleValidator 校验、
RuleStrategy 运行时解释。构建器与 AI 生成（AiStrategyService）均输出此格式。

设计文档：doc/strategy-builder-design.md
"""

SCHEMA_VERSION = 1
MAX_INDICATORS = 30
MAX_CONDITIONS = 50
MAX_NEST_DEPTH = 5
MAX_PERIOD = 500
MAX_SYMBOLS = 20
MAX_CONCURRENT_POSITIONS = 10
MAX_FORMULAS = 10
MAX_FORMULA_LENGTH = 200
MAX_LOOKBACK = 500

COMPARISON_OPERATORS = {"gt", "gte", "lt", "lte", "eq"}
CROSS_OPERATORS = {"cross_above", "cross_below"}
TREND_OPERATORS = {"rising", "falling"}
CHANGE_OPERATORS = {"percent_change_gte", "percent_change_lte"}
STATE_OPERATORS = {"has_position", "no_position", "bar_since_gte"}
ALL_OPERATORS = (
    COMPARISON_OPERATORS
    | CROSS_OPERATORS
    | TREND_OPERATORS
    | CHANGE_OPERATORS
    | STATE_OPERATORS
    | {"between"}
)

INDICATOR_TYPES_V1 = {
    # 趋势 / 均线
    "sma", "ema", "wma", "hma", "adx", "parabolic_sar", "supertrend", "ichimoku",
    # 动量
    "rsi", "macd", "roc", "kdj", "cci", "williams_r", "mfi", "stoch_rsi", "ao",
    # 波动率
    "bollinger", "atr", "keltner", "donchian",
    # 成交量
    "volume_sma", "obv", "vwap", "cmf", "ad_line",
}

INDICATOR_TYPES_NO_PERIOD = {
    "macd", "ao", "ichimoku", "parabolic_sar", "obv", "ad_line",
}

INDICATOR_OUTPUTS: dict[str, set[str]] = {
    "sma": {"value"},
    "ema": {"value"},
    "wma": {"value"},
    "hma": {"value"},
    "adx": {"value", "plus_di", "minus_di"},
    "parabolic_sar": {"value"},
    "supertrend": {"value", "direction"},
    "ichimoku": {"tenkan", "kijun", "senkou_a", "senkou_b"},
    "rsi": {"value"},
    "macd": {"value", "signal", "histogram"},
    "roc": {"value"},
    "kdj": {"k", "d", "j"},
    "cci": {"value"},
    "williams_r": {"value"},
    "mfi": {"value"},
    "stoch_rsi": {"k", "d"},
    "ao": {"value"},
    "bollinger": {"value", "upper", "lower", "width", "pct_b"},
    "atr": {"value"},
    "keltner": {"value", "upper", "lower"},
    "donchian": {"value", "upper", "lower"},
    "volume_sma": {"value"},
    "obv": {"value"},
    "vwap": {"value"},
    "cmf": {"value"},
    "ad_line": {"value"},
}

OHLCV_SOURCES = {"open", "high", "low", "close", "volume"}
ROLLING_FIELD_SOURCES = {"high", "low", "close"}

OPERATOR_CATALOG = [
    {"operator": "gt", "label": "大于", "arity": 2, "category": "comparison"},
    {"operator": "gte", "label": "大于等于", "arity": 2, "category": "comparison"},
    {"operator": "lt", "label": "小于", "arity": 2, "category": "comparison"},
    {"operator": "lte", "label": "小于等于", "arity": 2, "category": "comparison"},
    {"operator": "eq", "label": "等于", "arity": 2, "category": "comparison"},
    {"operator": "cross_above", "label": "上穿", "arity": 2, "category": "cross"},
    {"operator": "cross_below", "label": "下穿", "arity": 2, "category": "cross"},
    {"operator": "between", "label": "介于", "arity": 3, "category": "range"},
    {"operator": "rising", "label": "上升", "arity": 1, "category": "trend"},
    {"operator": "falling", "label": "下降", "arity": 1, "category": "trend"},
    {"operator": "percent_change_gte", "label": "涨幅≥%", "arity": 2, "category": "change"},
    {"operator": "percent_change_lte", "label": "跌幅≥%", "arity": 2, "category": "change"},
    {"operator": "has_position", "label": "有持仓", "arity": 0, "category": "state"},
    {"operator": "no_position", "label": "无持仓", "arity": 0, "category": "state"},
    {"operator": "bar_since_gte", "label": "距上次信号≥N根K线", "arity": 1, "category": "state"},
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
