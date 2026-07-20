from pydantic import BaseModel, Field


class StrategyStartRequest(BaseModel):
    confirm: bool = False
    run_mode: str = "live"
    symbols: list[str] = Field(default_factory=list)
    parameters: dict | None = None


class StrategyStopRequest(BaseModel):
    reason: str = "用户停止"
    cancel_open_orders: bool = False


class StrategyParametersUpdate(BaseModel):
    parameters: dict


class RiskSettingsUpdate(BaseModel):
    allowed_symbols: list[str] | None = None
    blocked_symbols: list[str] | None = None
    trading_sessions: list | None = None
    max_order_amount: str | None = None
    max_order_quantity: str | None = None
    max_symbol_position: str | None = None
    max_total_position: str | None = None
    daily_loss_limit: str | None = None
    daily_trade_count_limit: int | None = None
    sdk_disconnect_timeout_seconds: int | None = None
    quote_stale_timeout_seconds: int | None = None
    consecutive_order_fail_limit: int | None = None
    duplicate_signal_window_seconds: int | None = None
    auto_cancel_on_breaker: bool | None = None


class EmergencyStopRequest(BaseModel):
    reason: str = "用户手动紧急停止"
    cancel_open_orders: bool = True


class RiskResumeRequest(BaseModel):
    confirm: bool = False
    reason: str = ""


class ConfirmUnknownOrderRequest(BaseModel):
    confirm: bool = False
    resolved_status: str = Field(description="人工确认后的最终状态: cancelled/filled/failed")
    reason: str = Field(default="", description="确认说明")
