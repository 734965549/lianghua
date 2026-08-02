import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.repositories.strategy_repo import StrategyRepository, StrategyVersionRepository
from app.schemas.error_codes import ErrorCode
from app.services.audit_service import AuditService
import app.strategies.indicators  # noqa: F401 — 注册指标元数据
from app.strategies.indicators.base import IndicatorRegistry
from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION, OPERATOR_CATALOG
from app.strategies.rule_validator import (
    RuleValidationError,
    RuleValidator,
    definition_checksum,
    parameters_json_schema,
    resolve_parameters,
)


def _generate_strategy_id() -> str:
    return f"user_{uuid.uuid4().hex[:12]}"


class StrategyBuilderService:
    def get_indicator_catalog(self) -> dict:
        from app.strategies.rule_schema import FORMULA_OPERATORS, FORMULA_REF_HELP

        return {
            "indicators": IndicatorRegistry.catalog(),
            "operators": OPERATOR_CATALOG,
            "fields": ["open", "high", "low", "close", "volume"],
            "formula_operators": FORMULA_OPERATORS,
            "formula_ref_help": FORMULA_REF_HELP,
            "schema_version": 1,
        }

    def validate_definition(self, definition: dict) -> dict:
        validator = RuleValidator()
        errors = validator.validate(definition)
        return {"valid": len(errors) == 0, "errors": errors}

    def create_strategy(
        self,
        db: Session,
        *,
        name: str,
        description: str = "",
        definition: dict | None = None,
        parameters: dict | None = None,
        correlation_id: str = "",
    ) -> dict:
        definition = definition or DEFAULT_MA_CROSS_DEFINITION.copy()
        validator = RuleValidator()
        errors = validator.validate(definition)
        if errors:
            raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, "策略定义无效", debug="; ".join(errors))

        strategy_id = _generate_strategy_id()
        resolved = resolve_parameters(definition, parameters)
        repo = StrategyRepository(db)
        ver_repo = StrategyVersionRepository(db)

        row = repo.create_rule_strategy(
            strategy_id=strategy_id,
            name=name,
            description=description,
            parameters=resolved,
            supported_markets=[definition.get("market", "stock")],
        )
        checksum = definition_checksum(definition)
        pschema = parameters_json_schema(definition)
        ver_repo.upsert_draft(
            strategy_id=strategy_id,
            definition=definition,
            parameters_schema=pschema,
            checksum=checksum,
        )

        AuditService(db, correlation_id=correlation_id).log(
            action="strategy_create",
            module="strategy",
            object_type="strategy",
            object_id=strategy_id,
            result="success",
            request_summary={"name": name},
        )
        return self._to_dict(db, row, validation_errors=[])

    def update_strategy(
        self,
        db: Session,
        strategy_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        definition: dict | None = None,
        parameters: dict | None = None,
        correlation_id: str = "",
    ) -> dict:
        repo = StrategyRepository(db)
        row = repo.get_by_strategy_id(strategy_id)
        if row is None:
            raise BizError(ErrorCode.STRATEGY_NOT_FOUND, f"策略不存在: {strategy_id}")
        if not row.is_editable:
            raise BizError(ErrorCode.STRATEGY_RUNNING_PARAMS_LOCKED, "内置策略不可编辑")
        if row.kind != "rule":
            raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, "仅规则策略可编辑定义")

        validation_errors: list[str] = []
        if definition is not None:
            validation_errors = RuleValidator().validate(definition)
            if validation_errors:
                raise BizError(
                    ErrorCode.STRATEGY_PARAM_INVALID,
                    "策略定义无效",
                    debug="; ".join(validation_errors),
                )
            checksum = definition_checksum(definition)
            pschema = parameters_json_schema(definition)
            StrategyVersionRepository(db).upsert_draft(
                strategy_id=strategy_id,
                definition=definition,
                parameters_schema=pschema,
                checksum=checksum,
            )
            if parameters is not None:
                resolved = resolve_parameters(definition, parameters)
            else:
                resolved = resolve_parameters(definition, row.parameters)
            repo.update_rule_strategy(strategy_id, parameters=resolved)
            if row.status == "published":
                repo.update_rule_strategy(strategy_id, status="draft")

        if name is not None or description is not None:
            repo.update_rule_strategy(strategy_id, name=name, description=description)

        if parameters is not None and definition is None:
            draft = StrategyVersionRepository(db).get_draft(strategy_id)
            if draft is None:
                raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, "无草稿版本可更新参数")
            resolved = resolve_parameters(draft.definition, parameters)
            repo.update_rule_strategy(strategy_id, parameters=resolved)

        AuditService(db, correlation_id=correlation_id).log(
            action="strategy_update",
            module="strategy",
            object_type="strategy",
            object_id=strategy_id,
            result="success",
        )
        row = repo.get_by_strategy_id(strategy_id)
        return self._to_dict(db, row, validation_errors=validation_errors)

    def publish_strategy(
        self,
        db: Session,
        strategy_id: str,
        *,
        change_note: str = "",
        correlation_id: str = "",
    ) -> dict:
        repo = StrategyRepository(db)
        ver_repo = StrategyVersionRepository(db)
        row = repo.get_by_strategy_id(strategy_id)
        if row is None:
            raise BizError(ErrorCode.STRATEGY_NOT_FOUND, f"策略不存在: {strategy_id}")
        if row.kind != "rule":
            raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, "仅规则策略可发布")

        draft = ver_repo.get_draft(strategy_id)
        if draft is None:
            raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, "无草稿版本可发布")

        errors = RuleValidator().validate(draft.definition)
        if errors:
            raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, "定义校验失败", debug="; ".join(errors))

        ver_repo.publish_version(strategy_id, draft.version)
        repo.update_rule_strategy(
            strategy_id,
            status="published",
            current_version=draft.version,
            enabled=True,
        )

        AuditService(db, correlation_id=correlation_id).log(
            action="strategy_publish",
            module="strategy",
            object_type="strategy",
            object_id=strategy_id,
            result="success",
            request_summary={"version": draft.version, "change_note": change_note},
        )
        row = repo.get_by_strategy_id(strategy_id)
        return self._to_dict(db, row, validation_errors=[])

    def clone_strategy(
        self,
        db: Session,
        strategy_id: str,
        *,
        name: str | None = None,
        correlation_id: str = "",
    ) -> dict:
        repo = StrategyRepository(db)
        ver_repo = StrategyVersionRepository(db)
        source = repo.get_by_strategy_id(strategy_id)
        if source is None:
            raise BizError(ErrorCode.STRATEGY_NOT_FOUND, f"策略不存在: {strategy_id}")

        new_id = _generate_strategy_id()
        clone_name = name or f"{source.name} (副本)"

        if source.kind == "builtin":
            from app.strategies.registry import get_strategy_class

            cls = get_strategy_class(strategy_id)
            definition = DEFAULT_MA_CROSS_DEFINITION.copy() if strategy_id == "ma_cross" else {
                "schema_version": 1,
                "market": source.supported_markets[0] if source.supported_markets else "stock",
                "interval": "1d",
                "parameters": {},
                "indicators": [],
                "entry_rule": {"all": []},
                "exit_rule": {"any": []},
                "execution": {"quantity": {"constant": "100"}, "cooldown_bars": 1},
                "risk": {},
            }
            if strategy_id == "ma_cross":
                params = cls.param_schema().model_dump(mode="json")
                definition["parameters"] = {
                    "fast": {"type": "integer", "default": params.get("fast", 5), "min": 2, "max": 100},
                    "slow": {"type": "integer", "default": params.get("slow", 20), "min": 3, "max": 300},
                    "quantity": {"type": "decimal", "default": str(params.get("quantity", "100"))},
                }
            else:
                params = source.parameters
        else:
            ver = source.current_version
            if ver is None:
                draft = ver_repo.get_draft(strategy_id)
                if draft is None:
                    raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, "源策略无可用版本")
                definition = draft.definition
            else:
                ver_row = ver_repo.get_version(strategy_id, ver)
                definition = ver_row.definition if ver_row else {}
            params = source.parameters

        new_row = repo.create_rule_strategy(
            strategy_id=new_id,
            name=clone_name,
            description=source.description,
            parameters=params,
            supported_markets=list(source.supported_markets),
        )
        checksum = definition_checksum(definition)
        pschema = parameters_json_schema(definition)
        ver_repo.upsert_draft(
            strategy_id=new_id,
            definition=definition,
            parameters_schema=pschema,
            checksum=checksum,
        )

        AuditService(db, correlation_id=correlation_id).log(
            action="strategy_clone",
            module="strategy",
            object_type="strategy",
            object_id=new_id,
            result="success",
            request_summary={"source": strategy_id},
        )
        return self._to_dict(db, new_row, validation_errors=[])

    def archive_strategy(
        self,
        db: Session,
        strategy_id: str,
        *,
        correlation_id: str = "",
    ) -> dict:
        from app.services.strategy_service import strategy_service

        if strategy_id in strategy_service._running:
            raise BizError(ErrorCode.STRATEGY_ALREADY_RUNNING, "运行中的策略不可归档")

        repo = StrategyRepository(db)
        row = repo.get_by_strategy_id(strategy_id)
        if row is None:
            raise BizError(ErrorCode.STRATEGY_NOT_FOUND, f"策略不存在: {strategy_id}")
        if row.kind == "builtin":
            raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, "内置策略不可归档")

        repo.update_rule_strategy(strategy_id, status="archived", enabled=False)
        AuditService(db, correlation_id=correlation_id).log(
            action="strategy_archive",
            module="strategy",
            object_type="strategy",
            object_id=strategy_id,
            result="success",
        )
        row = repo.get_by_strategy_id(strategy_id)
        return self._to_dict(db, row, validation_errors=[])

    def list_versions(self, db: Session, strategy_id: str) -> list[dict]:
        rows = StrategyVersionRepository(db).list_versions(strategy_id)
        return [
            {
                "version": r.version,
                "status": r.status,
                "checksum": r.checksum,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "change_note": r.change_note,
            }
            for r in rows
        ]

    def get_version(self, db: Session, strategy_id: str, version: int) -> dict:
        row = StrategyVersionRepository(db).get_version(strategy_id, version)
        if row is None:
            raise BizError(ErrorCode.STRATEGY_NOT_FOUND, f"版本不存在: v{version}")
        return {
            "strategy_id": strategy_id,
            "version": row.version,
            "status": row.status,
            "definition": row.definition,
            "parameters_schema": row.parameters_schema,
            "checksum": row.checksum,
            "published_at": row.published_at.isoformat() if row.published_at else None,
        }

    def _to_dict(self, db: Session, row, *, validation_errors: list[str]) -> dict:
        from app.services.strategy_service import strategy_service
        from app.strategies.registry import get_strategy_class, list_strategies

        parameters_schema: dict = {}
        if row.kind == "rule":
            draft = StrategyVersionRepository(db).get_draft(row.strategy_id)
            if draft:
                parameters_schema = draft.parameters_schema
                validation_errors = RuleValidator().validate(draft.definition)
            elif row.current_version:
                ver = StrategyVersionRepository(db).get_version(row.strategy_id, row.current_version)
                if ver:
                    parameters_schema = ver.parameters_schema
        else:
            try:
                cls = get_strategy_class(row.strategy_id)
                parameters_schema = cls.param_schema.model_json_schema()
            except KeyError:
                pass

        return {
            "strategy_id": row.strategy_id,
            "name": row.name,
            "description": row.description,
            "enabled": row.enabled,
            "parameters": row.parameters,
            "supported_markets": row.supported_markets,
            "kind": row.kind,
            "status": row.status,
            "current_version": row.current_version,
            "editable": row.is_editable,
            "definition_schema_version": row.definition_schema_version,
            "parameters_schema": parameters_schema,
            "validation_errors": validation_errors,
            "running": row.strategy_id in strategy_service._running,
        }


strategy_builder_service = StrategyBuilderService()
