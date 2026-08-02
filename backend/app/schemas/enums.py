import enum


class Market(str, enum.Enum):
    STOCK = "stock"
    FUTURES = "futures"


class OrderSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class SignalAction(str, enum.Enum):
    OPEN = "open"
    CLOSE = "close"
    REDUCE = "reduce"
    INCREASE = "increase"


class PriceType(str, enum.Enum):
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(str, enum.Enum):
    PENDING_RISK = "pending_risk"
    RISK_REJECTED = "risk_rejected"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"
    UNKNOWN = "unknown"


class SystemStatus(str, enum.Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    TRADING = "trading"
    PAUSED = "paused"
    CIRCUIT_BREAKER = "circuit_breaker"
    EMERGENCY_STOPPED = "emergency_stopped"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class RiskResult(str, enum.Enum):
    PASSED = "passed"
    REJECTED = "rejected"
    WARNING = "warning"


class Severity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class StrategyRunStatus(str, enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"
    PENDING_CONFIRM = "pending_confirm"


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class BacktestStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Granularity(str, enum.Enum):
    KLINE = "kline"
    SIMULATED_TICK = "simulated_tick"
    TICK = "tick"


class FillModel(str, enum.Enum):
    NEXT_OPEN = "next_open"
    NEXT_CLOSE = "next_close"
    VWAP = "vwap"
    TICK_PRICE = "tick_price"
