from app.strategies.indicators.base import IndicatorRegistry, create_indicator, create_indicator_from_def
from app.strategies.indicators.momentum import KDJIndicator, MACDIndicator, ROCIndicator, RSIIndicator
from app.strategies.indicators.moving_average import EMAIndicator, SMAIndicator
from app.strategies.indicators.volatility import ATRIndicator, BollingerIndicator
from app.strategies.indicators.volume import VolumeSMAIndicator

IndicatorRegistry.register(
    "sma",
    SMAIndicator,
    catalog={
        "name": "简单移动平均",
        "outputs": ["value"],
        "requires_period": True,
        "params": [{"name": "period", "type": "integer", "min": 1, "max": 500}],
        "sources": ["open", "high", "low", "close", "volume"],
    },
)
IndicatorRegistry.register(
    "ema",
    EMAIndicator,
    catalog={
        "name": "指数移动平均",
        "outputs": ["value"],
        "requires_period": True,
        "params": [{"name": "period", "type": "integer", "min": 1, "max": 500}],
        "sources": ["open", "high", "low", "close", "volume"],
    },
)
IndicatorRegistry.register(
    "rsi",
    RSIIndicator,
    catalog={
        "name": "相对强弱指数",
        "outputs": ["value"],
        "requires_period": True,
        "params": [{"name": "period", "type": "integer", "min": 2, "max": 500}],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "macd",
    MACDIndicator,
    catalog={
        "name": "MACD",
        "outputs": ["value", "signal", "histogram"],
        "requires_period": False,
        "params": [
            {"name": "fast", "type": "integer", "default": 12, "min": 2, "max": 100},
            {"name": "slow", "type": "integer", "default": 26, "min": 3, "max": 300},
            {"name": "signal", "type": "integer", "default": 9, "min": 2, "max": 100},
        ],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "bollinger",
    BollingerIndicator,
    catalog={
        "name": "布林带",
        "outputs": ["value", "upper", "lower"],
        "requires_period": True,
        "params": [
            {"name": "period", "type": "integer", "min": 2, "max": 500},
            {"name": "std_dev", "type": "decimal", "default": "2", "min": "0.1", "max": "5"},
        ],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "atr",
    ATRIndicator,
    catalog={
        "name": "平均真实波幅",
        "outputs": ["value"],
        "requires_period": True,
        "params": [{"name": "period", "type": "integer", "min": 1, "max": 500}],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "roc",
    ROCIndicator,
    catalog={
        "name": "变动率 ROC",
        "outputs": ["value"],
        "requires_period": True,
        "params": [{"name": "period", "type": "integer", "min": 1, "max": 500}],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "kdj",
    KDJIndicator,
    catalog={
        "name": "KDJ 随机指标",
        "outputs": ["k", "d", "j"],
        "requires_period": True,
        "params": [{"name": "period", "type": "integer", "min": 2, "max": 500}],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "volume_sma",
    VolumeSMAIndicator,
    catalog={
        "name": "成交量均线",
        "outputs": ["value"],
        "requires_period": True,
        "params": [{"name": "period", "type": "integer", "min": 1, "max": 500}],
        "sources": ["volume"],
    },
)

__all__ = [
    "IndicatorRegistry",
    "create_indicator",
    "create_indicator_from_def",
]
