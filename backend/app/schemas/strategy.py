from pydantic import BaseModel, Field


class StrategyStartRequest(BaseModel):
    confirm: bool = False
    run_mode: str = Field(default="live", description="运行模式: live | paper")
    symbols: list[str] = Field(default_factory=list)
    parameters: dict | None = None
    strategy_version: int | None = None
    reason: str = Field(default="", description="启动原因，写入审计日志")


class StrategyStopRequest(BaseModel):
    reason: str = "用户停止"
    cancel_open_orders: bool = False


class StrategyParametersUpdate(BaseModel):
    parameters: dict


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    definition: dict | None = None
    parameters: dict | None = None


class StrategyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    definition: dict | None = None
    parameters: dict | None = None


class StrategyValidateRequest(BaseModel):
    definition: dict


class StrategyPublishRequest(BaseModel):
    change_note: str = ""


class StrategyCloneRequest(BaseModel):
    name: str | None = None


class RiskSettingsUpdate(BaseModel):
    confirm: bool = False
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
    reason: str | None = Field(default=None, description="变更原因，写入审计日志")


class EmergencyStopRequest(BaseModel):
    reason: str = "用户手动紧急停止"
    cancel_open_orders: bool = True


class RiskResumeRequest(BaseModel):
    confirm: bool = False
    reason: str = Field(min_length=1, description="恢复原因，必填并写入审计")


class ConfirmUnknownOrderRequest(BaseModel):
    confirm: bool = False
    resolved_status: str = Field(description="人工确认后的最终状态: cancelled/filled/failed")
    reason: str = Field(default="", description="确认说明")
