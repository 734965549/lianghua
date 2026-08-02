from app.strategies.indicators.base import IndicatorRegistry, create_indicator, create_indicator_from_def
from app.strategies.indicators.momentum import (
    AOIndicator,
    CCIIndicator,
    KDJIndicator,
    MACDIndicator,
    MFIIndicator,
    ROCIndicator,
    RSIIndicator,
    StochRSIIndicator,
    WilliamsRIndicator,
)
from app.strategies.indicators.moving_average import EMAIndicator, HMAIndicator, SMAIndicator, WMAIndicator
from app.strategies.indicators.trend import (
    ADXIndicator,
    IchimokuIndicator,
    ParabolicSARIndicator,
    SuperTrendIndicator,
)
from app.strategies.indicators.volatility import ATRIndicator, BollingerIndicator, DonchianIndicator, KeltnerIndicator
from app.strategies.indicators.volume import (
    ADLineIndicator,
    CMFIndicator,
    OBVIndicator,
    VolumeSMAIndicator,
    VWAPIndicator,
)

_PERIOD_1_500 = {"type": "integer", "min": 1, "max": 500}
_PERIOD_2_500 = {"type": "integer", "min": 2, "max": 500}

# ── 趋势 / 均线 ──
IndicatorRegistry.register(
    "sma",
    SMAIndicator,
    catalog={
        "name": "简单移动平均",
        "category": "trend",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_1_500,
        "params": [],
        "sources": ["open", "high", "low", "close", "volume"],
    },
)
IndicatorRegistry.register(
    "ema",
    EMAIndicator,
    catalog={
        "name": "指数移动平均",
        "category": "trend",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_1_500,
        "params": [],
        "sources": ["open", "high", "low", "close", "volume"],
    },
)
IndicatorRegistry.register(
    "wma",
    WMAIndicator,
    catalog={
        "name": "加权移动平均",
        "category": "trend",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_1_500,
        "params": [],
        "sources": ["open", "high", "low", "close", "volume"],
    },
)
IndicatorRegistry.register(
    "hma",
    HMAIndicator,
    catalog={
        "name": "Hull 移动平均",
        "category": "trend",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [],
        "sources": ["open", "high", "low", "close", "volume"],
    },
)
IndicatorRegistry.register(
    "adx",
    ADXIndicator,
    catalog={
        "name": "平均趋向指数 ADX",
        "category": "trend",
        "outputs": ["value", "plus_di", "minus_di"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "parabolic_sar",
    ParabolicSARIndicator,
    catalog={
        "name": "抛物线 SAR",
        "category": "trend",
        "outputs": ["value"],
        "requires_period": False,
        "params": [
            {"name": "step", "type": "decimal", "default": "0.02", "min": "0.01", "max": "0.1"},
            {"name": "max_step", "type": "decimal", "default": "0.2", "min": "0.05", "max": "0.5"},
        ],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "supertrend",
    SuperTrendIndicator,
    catalog={
        "name": "超级趋势 SuperTrend",
        "category": "trend",
        "outputs": ["value", "direction"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [
            {"name": "multiplier", "type": "decimal", "default": "3", "min": "0.5", "max": "10"},
        ],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "ichimoku",
    IchimokuIndicator,
    catalog={
        "name": "一目均衡表",
        "category": "trend",
        "outputs": ["tenkan", "kijun", "senkou_a", "senkou_b"],
        "requires_period": False,
        "params": [
            {"name": "tenkan", "type": "integer", "default": 9, "min": 2, "max": 100},
            {"name": "kijun", "type": "integer", "default": 26, "min": 3, "max": 300},
            {"name": "senkou_b", "type": "integer", "default": 52, "min": 5, "max": 500},
        ],
        "sources": ["close"],
    },
)

# ── 动量 ──
IndicatorRegistry.register(
    "rsi",
    RSIIndicator,
    catalog={
        "name": "相对强弱指数",
        "category": "momentum",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "macd",
    MACDIndicator,
    catalog={
        "name": "MACD",
        "category": "momentum",
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
    "roc",
    ROCIndicator,
    catalog={
        "name": "变动率 ROC",
        "category": "momentum",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_1_500,
        "params": [],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "kdj",
    KDJIndicator,
    catalog={
        "name": "KDJ 随机指标",
        "category": "momentum",
        "outputs": ["k", "d", "j"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "cci",
    CCIIndicator,
    catalog={
        "name": "商品通道指数 CCI",
        "category": "momentum",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "williams_r",
    WilliamsRIndicator,
    catalog={
        "name": "威廉指标 %R",
        "category": "momentum",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "mfi",
    MFIIndicator,
    catalog={
        "name": "资金流量指数 MFI",
        "category": "momentum",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "stoch_rsi",
    StochRSIIndicator,
    catalog={
        "name": "随机 RSI",
        "category": "momentum",
        "outputs": ["k", "d"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [
            {"name": "stoch_period", "type": "integer", "default": 14, "min": 2, "max": 100},
            {"name": "k_smooth", "type": "integer", "default": 3, "min": 1, "max": 50},
            {"name": "d_smooth", "type": "integer", "default": 3, "min": 1, "max": 50},
        ],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "ao",
    AOIndicator,
    catalog={
        "name": "Awesome Oscillator",
        "category": "momentum",
        "outputs": ["value"],
        "requires_period": False,
        "params": [
            {"name": "fast", "type": "integer", "default": 5, "min": 2, "max": 100},
            {"name": "slow", "type": "integer", "default": 34, "min": 3, "max": 300},
        ],
        "sources": ["close"],
    },
)

# ── 波动率 ──
IndicatorRegistry.register(
    "bollinger",
    BollingerIndicator,
    catalog={
        "name": "布林带",
        "category": "volatility",
        "outputs": ["value", "upper", "lower", "width", "pct_b"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [
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
        "category": "volatility",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_1_500,
        "params": [],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "keltner",
    KeltnerIndicator,
    catalog={
        "name": "肯特纳通道",
        "category": "volatility",
        "outputs": ["value", "upper", "lower"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [
            {"name": "multiplier", "type": "decimal", "default": "2", "min": "0.5", "max": "5"},
        ],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "donchian",
    DonchianIndicator,
    catalog={
        "name": "唐奇安通道",
        "category": "volatility",
        "outputs": ["value", "upper", "lower"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [],
        "sources": ["close"],
    },
)

# ── 成交量 ──
IndicatorRegistry.register(
    "volume_sma",
    VolumeSMAIndicator,
    catalog={
        "name": "成交量均线",
        "category": "volume",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_1_500,
        "params": [],
        "sources": ["volume"],
    },
)
IndicatorRegistry.register(
    "obv",
    OBVIndicator,
    catalog={
        "name": "能量潮 OBV",
        "category": "volume",
        "outputs": ["value"],
        "requires_period": False,
        "params": [],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "vwap",
    VWAPIndicator,
    catalog={
        "name": "成交量加权平均价 VWAP",
        "category": "volume",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "cmf",
    CMFIndicator,
    catalog={
        "name": "柴金资金流 CMF",
        "category": "volume",
        "outputs": ["value"],
        "requires_period": True,
        "period": _PERIOD_2_500,
        "params": [],
        "sources": ["close"],
    },
)
IndicatorRegistry.register(
    "ad_line",
    ADLineIndicator,
    catalog={
        "name": "累积/派发线 A/D",
        "category": "volume",
        "outputs": ["value"],
        "requires_period": False,
        "params": [],
        "sources": ["close"],
    },
)

__all__ = [
    "IndicatorRegistry",
    "create_indicator",
    "create_indicator_from_def",
]
