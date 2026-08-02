from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models.backtest_run import BacktestRun
from app.repositories.base import BaseRepository
from app.schemas.enums import BacktestStatus


class BacktestRunRepository(BaseRepository[BacktestRun]):
    model = BacktestRun

    def create(
        self,
        *,
        strategy_id: str,
        parameters: dict,
        symbols: list[str],
        start_time,
        end_time,
        granularity: str,
        fill_model: str,
        initial_cash: str,
        status: BacktestStatus = BacktestStatus.PENDING,
    ) -> BacktestRun:
        row = BacktestRun(
            strategy_id=strategy_id,
            parameters=parameters,
            symbols=symbols,
            start_time=start_time,
            end_time=end_time,
            granularity=granularity,
            fill_model=fill_model,
            initial_cash=initial_cash,
            status=status,
        )
        return self.add(row)

    def update_result(
        self,
        run_id: UUID,
        *,
        status: BacktestStatus,
        final_equity: str | None = None,
        metrics_json: dict | None = None,
        trades_json: list | None = None,
        equity_curve_json: list | None = None,
        error_message: str | None = None,
    ) -> BacktestRun | None:
        row = self.get(run_id)
        if row is None:
            return None
        row.status = status
        if final_equity is not None:
            row.final_equity = final_equity
        if metrics_json is not None:
            row.metrics_json = metrics_json
        if trades_json is not None:
            row.trades_json = trades_json
        if equity_curve_json is not None:
            row.equity_curve_json = equity_curve_json
        if error_message is not None:
            row.error_message = error_message
        self.db.flush()
        return row

    def list_runs(self, *, offset: int = 0, limit: int = 20) -> tuple[list[BacktestRun], int]:
        q = self.db.query(BacktestRun).order_by(desc(BacktestRun.created_at))
        total = q.count()
        return q.offset(offset).limit(limit).all(), total
