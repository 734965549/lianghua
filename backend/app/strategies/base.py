from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.sdk.models import KlineBar, OrderUpdateEvent, QuoteSnapshot

if TYPE_CHECKING:
    from app.strategies.context import StrategyContext


class StrategyParamSchema(BaseModel):
    """策略参数 schema，子类用 Pydantic 模型声明参数。"""

    pass


class Strategy(ABC):
    """策略抽象基类。子类只生成信号，不接触订单/SDK/数据库。"""

    strategy_id: str
    name: str
    version: str = "unversioned"
    description: str = ""
    param_schema: type[StrategyParamSchema] = StrategyParamSchema
    supported_markets: list[str] = ["stock", "futures"]

    def __init__(self, parameters: dict):
        self.parameters = self.param_schema(**parameters)
        self.context: "StrategyContext | None" = None

    @abstractmethod
    def on_start(self, context: "StrategyContext") -> None: ...

    @abstractmethod
    def on_quote(self, quote: QuoteSnapshot) -> list: ...

    @abstractmethod
    def on_bar(self, bar: KlineBar) -> list: ...

    def on_order_update(self, event: OrderUpdateEvent) -> None:
        pass

    @abstractmethod
    def on_stop(self) -> None: ...

    def log(self, level: str, message: str, **extra):
        if self.context:
            self.context.log(level, message, **extra)
