from sqlalchemy.orm import Session

from app.api.response import BizError
from app.schemas.error_codes import ErrorCode
import app.strategies.indicators  # noqa: F401 — 注册指标
from app.strategies.base import Strategy
from app.strategies.registry import get_strategy_class, import_samples
from app.strategies.rule_strategy import RuleStrategy
from app.strategies.rule_validator import resolve_parameters
from app.repositories.strategy_repo import StrategyRepository, StrategyVersionRepository


class StrategyFactory:
    """统一创建内置 Python 策略或用户规则策略。"""

    @classmethod
    def create(
        cls,
        db: Session,
        strategy_id: str,
        parameters: dict | None = None,
        *,
        version: int | None = None,
    ) -> Strategy:
        import_samples()
        repo = StrategyRepository(db)
        row = repo.get_by_strategy_id(strategy_id)
        if row is None:
            raise BizError(ErrorCode.STRATEGY_NOT_FOUND, f"策略不存在: {strategy_id}")

        params = dict(row.parameters or {})
        if parameters:
            params.update(parameters)

        if row.kind == "builtin":
            strategy_cls = get_strategy_class(strategy_id)
            validated = strategy_cls.param_schema(**params).model_dump(mode="json")
            return strategy_cls(validated)

        if row.kind == "rule":
            return cls._create_rule_strategy(db, row, params, version=version)

        raise BizError(ErrorCode.STRATEGY_NOT_FOUND, f"未知策略类型: {row.kind}")

    @classmethod
    def _create_rule_strategy(
        cls,
        db: Session,
        row,
        params: dict,
        *,
        version: int | None,
    ) -> RuleStrategy:
        ver_repo = StrategyVersionRepository(db)
        target_version = version or row.current_version
        if target_version is None:
            raise BizError(
                ErrorCode.STRATEGY_PARAM_INVALID,
                f"策略 {row.strategy_id} 无已发布版本",
            )

        ver_row = ver_repo.get_version(row.strategy_id, target_version)
        if ver_row is None:
            raise BizError(
                ErrorCode.STRATEGY_NOT_FOUND,
                f"策略版本不存在: {row.strategy_id} v{target_version}",
            )
        if ver_row.status != "published":
            raise BizError(
                ErrorCode.STRATEGY_PARAM_INVALID,
                f"策略版本 v{target_version} 未发布，不可运行",
            )

        definition = ver_row.definition
        resolved = resolve_parameters(definition, params)
        return RuleStrategy(
            strategy_id=row.strategy_id,
            name=row.name,
            definition=definition,
            parameters=resolved,
            version=target_version,
        )

    @classmethod
    def assert_runnable(cls, db: Session, strategy_id: str, version: int | None = None) -> None:
        repo = StrategyRepository(db)
        row = repo.get_by_strategy_id(strategy_id)
        if row is None:
            raise BizError(ErrorCode.STRATEGY_NOT_FOUND, f"策略不存在: {strategy_id}")
        if row.status == "draft":
            raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, "草稿策略不可回测或启动")
        if row.status == "archived":
            raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, "已归档策略不可运行")
        if row.kind == "rule":
            ver = version or row.current_version
            if ver is None:
                raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, "规则策略无已发布版本")
            ver_row = StrategyVersionRepository(db).get_version(strategy_id, ver)
            if ver_row is None:
                raise BizError(ErrorCode.STRATEGY_NOT_FOUND, f"策略版本不存在: v{ver}")
            if ver_row.status != "published":
                raise BizError(ErrorCode.STRATEGY_PARAM_INVALID, f"版本 v{ver} 未发布")
