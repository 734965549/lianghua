from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.db.models.strategy import Strategy
from app.db.models.strategy_run import StrategyRun
from app.repositories.base import BaseRepository
from app.schemas.enums import StrategyRunStatus


class StrategyRepository(BaseRepository[Strategy]):
    model = Strategy

    def get_by_strategy_id(self, strategy_id: str) -> Strategy | None:
        return self.db.query(Strategy).filter(Strategy.strategy_id == strategy_id).first()

    def list_all(self) -> list[Strategy]:
        return self.db.query(Strategy).order_by(Strategy.strategy_id).all()

    def upsert_definition(
        self,
        *,
        strategy_id: str,
        name: str,
        description: str = "",
        enabled: bool = True,
        parameters: dict | None = None,
        supported_markets: list | None = None,
    ) -> Strategy:
        row = self.get_by_strategy_id(strategy_id)
        if row is None:
            row = Strategy(
                strategy_id=strategy_id,
                name=name,
                description=description,
                enabled=enabled,
                parameters=parameters or {},
                supported_markets=supported_markets or [],
            )
            return self.add(row)
        row.name = name
        row.description = description
        row.enabled = enabled
        if parameters is not None:
            row.parameters = parameters
        if supported_markets is not None:
            row.supported_markets = supported_markets
        self.db.flush()
        return row

    def update_parameters(self, strategy_id: str, parameters: dict) -> Strategy | None:
        row = self.get_by_strategy_id(strategy_id)
        if row is None:
            return None
        row.parameters = parameters
        self.db.flush()
        return row


class StrategyRunRepository(BaseRepository[StrategyRun]):
    model = StrategyRun

    def create_run(
        self,
        *,
        strategy_id: str,
        status: StrategyRunStatus,
        parameters: dict,
        started_at: datetime | None = None,
    ) -> StrategyRun:
        row = StrategyRun(
            strategy_id=strategy_id,
            status=status,
            parameters=parameters,
            started_at=started_at or datetime.now(timezone.utc),
        )
        return self.add(row)

    def get_active_run(self, strategy_id: str) -> StrategyRun | None:
        return (
            self.db.query(StrategyRun)
            .filter(
                StrategyRun.strategy_id == strategy_id,
                StrategyRun.status == StrategyRunStatus.RUNNING,
            )
            .order_by(desc(StrategyRun.started_at))
            .first()
        )

    def finish_run(
        self,
        run_id: UUID,
        *,
        status: StrategyRunStatus,
        reason: str = "",
    ) -> StrategyRun | None:
        row = self.get(run_id)
        if row is None:
            return None
        row.status = status
        row.stopped_at = datetime.now(timezone.utc)
        row.stop_reason = reason
        self.db.flush()
        return row

    def list_runs(
        self,
        *,
        strategy_id: str | None = None,
        status: StrategyRunStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[StrategyRun], int]:
        q = self.db.query(StrategyRun)
        if strategy_id:
            q = q.filter(StrategyRun.strategy_id == strategy_id)
        if status is not None:
            q = q.filter(StrategyRun.status == status)
        total = q.count()
        rows = q.order_by(desc(StrategyRun.started_at)).offset(offset).limit(limit).all()
        return rows, total
