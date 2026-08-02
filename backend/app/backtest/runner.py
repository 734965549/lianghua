import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.backtest.account import SimulationAccount
from app.backtest.broker import SimulationBroker
from app.backtest.context import BacktestContext
from app.backtest.data_source import (
    HistoricalDataSource,
    KlineDataSource,
    MarketEvent,
    SimulatedTickDataSource,
    TickDataSource,
)
from app.backtest.fill_model import FillModelEngine
from app.backtest.metrics import BacktestMetricsCalculator, calculate_trade_metrics
from app.services.cost_service import CostService
from app.backtest.models import BacktestCreateRequest, BacktestOrderRequest, BacktestResult, EquityPoint, TradeRecord
from app.schemas.enums import BacktestStatus, Granularity, Market, PriceType
from app.sdk.models import KlineBar, OrderUpdateEvent, QuoteSnapshot
from app.strategies.base import Strategy
from app.strategies.factory import StrategyFactory

logger = logging.getLogger(__name__)


def _guess_market(symbol: str) -> Market:
    upper = symbol.upper()
    if upper.startswith("IF") or upper.startswith("RB") or "." not in symbol:
        return Market.FUTURES
    return Market.STOCK


class BacktestRunner:
    """事件驱动回测执行器。"""

    def __init__(self, request: BacktestCreateRequest, db: Session):
        self.request = request
        self.db = db
        self.run_id = str(uuid.uuid4())
        self._signals: list[dict[str, Any]] = []
        self._equity_curve: list[EquityPoint] = []
        self._latest_prices: dict[str, Decimal] = {}
        self._current_time: datetime = request.start_time
        self._strategy_cls: type[Strategy] | None = None
        self._strategy: Strategy | None = None
        self._context: BacktestContext | None = None
        self._account: SimulationAccount | None = None
        self._broker: SimulationBroker | None = None

    def run(self) -> BacktestResult:
        StrategyFactory.assert_runnable(
            self.db, self.request.strategy_id, version=self.request.strategy_version
        )

        params = dict(self.request.parameters)
        params.setdefault("symbols", self.request.symbols)
        params.setdefault("interval", self.request.interval)
        self._strategy = StrategyFactory.create(
            self.db,
            self.request.strategy_id,
            params,
            version=self.request.strategy_version,
        )

        self._account = SimulationAccount(initial_cash=self.request.initial_cash)
        fill_model = FillModelEngine(
            fill_model=self.request.fill_model,
            slippage=self.request.slippage,
        )
        cost_service = CostService(
            commission_rate=self.request.commission_rate,
            stamp_tax_rate=self.request.stamp_tax_rate,
        )
        self._broker = SimulationBroker(
            account=self._account,
            fill_model=fill_model,
            cost_service=cost_service,
            order_update_callback=self._on_order_update,
        )

        self._context = BacktestContext(
            strategy_id=self.request.strategy_id,
            run_id=self.run_id,
            parameters=params,
            interval=self.request.interval,
            db=self.db,
            current_time_fn=lambda: self._current_time,
            account=self._account,
            signal_sink=self._on_signal,
        )

        data_source = self._build_data_source()

        self._strategy.on_start(self._context)

        for event in data_source.load_events(
            symbols=self.request.symbols,
            start=self.request.start_time,
            end=self.request.end_time,
            interval=self.request.interval,
        ):
            self._current_time = event.event_time
            self._update_price(event)

            # 1. 撮合上一阶段产生的订单
            self._broker.on_market_event(event)

            # 2. 驱动策略回调
            if event.bar is not None:
                self._strategy.on_bar(event.bar)
            elif event.quote is not None:
                self._strategy.on_quote(event.quote)

            # 3. 将信号转换为订单，留待下一事件撮合
            self._submit_pending_signals()

            # 4. 记录权益曲线
            self._record_equity()

        self._strategy.on_stop()

        return self._build_result(BacktestStatus.COMPLETED)

    def _build_data_source(self) -> HistoricalDataSource:
        if self.request.granularity == Granularity.KLINE:
            return KlineDataSource(self.db)
        if self.request.granularity == Granularity.SIMULATED_TICK:
            return SimulatedTickDataSource(self.db)
        if self.request.granularity == Granularity.TICK:
            return TickDataSource(self.db)
        raise ValueError(f"不支持的回放粒度: {self.request.granularity}")

    def _update_price(self, event: MarketEvent) -> None:
        if event.bar is not None:
            self._latest_prices[event.symbol] = event.bar.close
        elif event.quote is not None:
            self._latest_prices[event.symbol] = event.quote.last_price

    def _on_signal(self, **kwargs) -> None:
        self._signals.append(kwargs)

    def _on_order_update(self, event: OrderUpdateEvent) -> None:
        if self._strategy is not None:
            self._strategy.on_order_update(event)

    def _submit_pending_signals(self) -> None:
        if self._broker is None or self._context is None:
            return
        for signal in self._signals:
            order = BacktestOrderRequest(
                client_order_id=signal["signal_id"],
                symbol=signal["symbol"],
                market=signal["market"],
                side=signal["side"],
                price_type=signal.get("price_type", PriceType.MARKET),
                quantity=signal["quantity"],
                price=signal.get("price") or None,
            )
            self._broker.submit_order(order)
        self._signals.clear()

    def _record_equity(self) -> None:
        if self._account is None:
            return
        equity = self._account.total_asset(self._latest_prices)
        self._equity_curve.append(EquityPoint(time=self._current_time, equity=equity))

    def _build_result(self, status: BacktestStatus, error_message: str | None = None) -> BacktestResult:
        if self._account is None or self._broker is None:
            raise RuntimeError("回测未正确初始化")

        final_equity = self._account.total_asset(self._latest_prices)
        fills = self._broker.get_fills()
        trade_records = [
            TradeRecord(
                trade_id=f.fill_id,
                symbol=f.symbol,
                side=f.side,
                quantity=f.quantity,
                price=f.price,
                commission=f.commission,
                tax=f.tax,
                trade_time=f.fill_time,
            )
            for f in fills
        ]

        calc = BacktestMetricsCalculator(
            initial_cash=self.request.initial_cash,
            account=self._account,
            equity_curve=self._equity_curve,
        )
        equity_metrics = calc.calculate()
        trade_metrics = calculate_trade_metrics(trade_records)

        metrics = equity_metrics.model_copy(
            update={
                "win_rate_pct": trade_metrics.win_rate_pct,
                "profit_factor": trade_metrics.profit_factor,
                "total_trades": trade_metrics.total_trades,
            }
        )

        return BacktestResult(
            id=uuid.UUID(self.run_id),
            strategy_id=self.request.strategy_id,
            status=status,
            parameters=self.request.parameters,
            symbols=self.request.symbols,
            start_time=self.request.start_time,
            end_time=self.request.end_time,
            granularity=self.request.granularity.value,
            fill_model=self.request.fill_model.value,
            initial_cash=self.request.initial_cash,
            final_equity=final_equity,
            metrics=metrics,
            trades=trade_records,
            equity_curve=self._equity_curve,
            error_message=error_message,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
