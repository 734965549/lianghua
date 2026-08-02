from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import BacktestStatus, FillModel, Granularity, Market, OrderSide, PriceType


class BacktestCreateRequest(BaseModel):
    """创建回测任务的请求体。"""

    strategy_id: str
    symbols: list[str]
    start_time: datetime
    end_time: datetime
    initial_cash: Decimal = Decimal("1000000")
    granularity: Granularity = Granularity.KLINE
    fill_model: FillModel = FillModel.NEXT_CLOSE
    interval: str = "1d"
    parameters: dict = Field(default_factory=dict)
    strategy_version: int | None = None
    commission_rate: Decimal = Decimal("0.0003")
    stamp_tax_rate: Decimal = Decimal("0.001")
    slippage: Decimal = Decimal("0")


class BacktestOrderRequest(BaseModel):
    """回测内部订单请求。由信号转换而来。"""

    client_order_id: str
    symbol: str
    market: Market
    side: OrderSide
    price_type: PriceType
    quantity: Decimal
    price: Decimal | None = None


class Fill(BaseModel):
    """成交记录。"""

    fill_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal
    tax: Decimal
    fill_time: datetime


class TradeRecord(BaseModel):
    """对外展示的成交记录。"""

    trade_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal
    tax: Decimal
    trade_time: datetime


class EquityPoint(BaseModel):
    """权益曲线上的单点。"""

    time: datetime
    equity: Decimal


class BacktestMetrics(BaseModel):
    """回测绩效指标。"""

    total_return_pct: Decimal
    annualized_return_pct: Decimal
    sharpe_ratio: Decimal
    max_drawdown_pct: Decimal
    win_rate_pct: Decimal
    profit_factor: Decimal
    total_trades: int


class BacktestResult(BaseModel):
    """回测结果，与 ORM 模型对应。"""

    # Pydantic V2 默认已将 Decimal 序列化为字符串、datetime 序列化为 ISO 格式，
    # 无需再使用已弃用的 json_encoders。
    id: UUID
    strategy_id: str
    status: BacktestStatus
    parameters: dict
    symbols: list[str]
    start_time: datetime
    end_time: datetime
    granularity: str
    fill_model: str
    initial_cash: Decimal
    final_equity: Decimal | None = None
    metrics: BacktestMetrics | None = None
    trades: list[TradeRecord] = Field(default_factory=list)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    error_message: str | None = None
    provenance: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
