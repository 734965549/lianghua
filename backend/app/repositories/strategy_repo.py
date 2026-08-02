from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.db.models.strategy import Strategy
from app.db.models.strategy_run import StrategyRun
from app.db.models.strategy_version import StrategyVersion
from app.repositories.base import BaseRepository
from app.schemas.enums import StrategyRunStatus


class StrategyRepository(BaseRepository[Strategy]):
    model = Strategy

    def get_by_strategy_id(self, strategy_id: str) -> Strategy | None:
        return self.db.query(Strategy).filter(Strategy.strategy_id == strategy_id).first()

    def list_all(self) -> list[Strategy]:
        return self.db.query(Strategy).order_by(Strategy.strategy_id).all()

    def list_by_kind(self, kind: str | None = None) -> list[Strategy]:
        q = self.db.query(Strategy)
        if kind:
            q = q.filter(Strategy.kind == kind)
        return q.order_by(Strategy.strategy_id).all()

    def upsert_definition(
        self,
        *,
        strategy_id: str,
        name: str,
        description: str = "",
        enabled: bool = True,
        parameters: dict | None = None,
        supported_markets: list | None = None,
        kind: str = "builtin",
        status: str = "published",
        current_version: int | None = None,
        is_editable: bool = True,
        definition_schema_version: int = 1,
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
                kind=kind,
                status=status,
                current_version=current_version,
                is_editable=is_editable,
                definition_schema_version=definition_schema_version,
            )
            return self.add(row)
        row.name = name
        row.description = description
        row.enabled = enabled
        if parameters is not None:
            row.parameters = parameters
        if supported_markets is not None:
            row.supported_markets = supported_markets
        if kind:
            row.kind = kind
        if status:
            row.status = status
        if current_version is not None:
            row.current_version = current_version
        row.is_editable = is_editable
        row.definition_schema_version = definition_schema_version
        self.db.flush()
        return row

    def create_rule_strategy(
        self,
        *,
        strategy_id: str,
        name: str,
        description: str = "",
        parameters: dict | None = None,
        supported_markets: list | None = None,
    ) -> Strategy:
        row = Strategy(
            strategy_id=strategy_id,
            name=name,
            description=description,
            enabled=True,
            parameters=parameters or {},
            supported_markets=supported_markets or ["stock"],
            kind="rule",
            status="draft",
            current_version=None,
            is_editable=True,
            definition_schema_version=1,
        )
        return self.add(row)

    def update_rule_strategy(
        self,
        strategy_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        parameters: dict | None = None,
        supported_markets: list | None = None,
        status: str | None = None,
        current_version: int | None = None,
        enabled: bool | None = None,
    ) -> Strategy | None:
        row = self.get_by_strategy_id(strategy_id)
        if row is None:
            return None
        if name is not None:
            row.name = name
        if description is not None:
            row.description = description
        if parameters is not None:
            row.parameters = parameters
        if supported_markets is not None:
            row.supported_markets = supported_markets
        if status is not None:
            row.status = status
        if current_version is not None:
            row.current_version = current_version
        if enabled is not None:
            row.enabled = enabled
        self.db.flush()
        return row

    def update_parameters(self, strategy_id: str, parameters: dict) -> Strategy | None:
        row = self.get_by_strategy_id(strategy_id)
        if row is None:
            return None
        row.parameters = parameters
        self.db.flush()
        return row


class StrategyVersionRepository(BaseRepository[StrategyVersion]):
    model = StrategyVersion

    def get_version(self, strategy_id: str, version: int) -> StrategyVersion | None:
        return (
            self.db.query(StrategyVersion)
            .filter(
                StrategyVersion.strategy_id == strategy_id,
                StrategyVersion.version == version,
            )
            .first()
        )

    def get_draft(self, strategy_id: str) -> StrategyVersion | None:
        return (
            self.db.query(StrategyVersion)
            .filter(
                StrategyVersion.strategy_id == strategy_id,
                StrategyVersion.status == "draft",
            )
            .order_by(desc(StrategyVersion.version))
            .first()
        )

    def list_versions(self, strategy_id: str) -> list[StrategyVersion]:
        return (
            self.db.query(StrategyVersion)
            .filter(StrategyVersion.strategy_id == strategy_id)
            .order_by(desc(StrategyVersion.version))
            .all()
        )

    def next_version_number(self, strategy_id: str) -> int:
        max_ver = (
            self.db.query(func.max(StrategyVersion.version))
            .filter(StrategyVersion.strategy_id == strategy_id)
            .scalar()
        )
        return (max_ver or 0) + 1

    def create_version(
        self,
        *,
        strategy_id: str,
        version: int,
        definition: dict,
        parameters_schema: dict,
        checksum: str,
        status: str = "draft",
        change_note: str = "",
    ) -> StrategyVersion:
        row = StrategyVersion(
            strategy_id=strategy_id,
            version=version,
            definition=definition,
            parameters_schema=parameters_schema,
            checksum=checksum,
            status=status,
            change_note=change_note,
        )
        return self.add(row)

    def publish_version(self, strategy_id: str, version: int) -> StrategyVersion | None:
        row = self.get_version(strategy_id, version)
        if row is None:
            return None
        row.status = "published"
        row.published_at = datetime.now(timezone.utc)
        self.db.flush()
        return row

    def upsert_draft(
        self,
        *,
        strategy_id: str,
        definition: dict,
        parameters_schema: dict,
        checksum: str,
    ) -> StrategyVersion:
        draft = self.get_draft(strategy_id)
        if draft is not None:
            draft.definition = definition
            draft.parameters_schema = parameters_schema
            draft.checksum = checksum
            self.db.flush()
            return draft
        version = self.next_version_number(strategy_id)
        return self.create_version(
            strategy_id=strategy_id,
            version=version,
            definition=definition,
            parameters_schema=parameters_schema,
            checksum=checksum,
            status="draft",
        )


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
