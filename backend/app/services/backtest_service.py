import logging
import hashlib
import inspect
import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.backtest.models import BacktestCreateRequest, BacktestResult
from app.backtest.runner import BacktestRunner
from app.db.models.backtest_run import BacktestRun
from app.repositories.backtest_repo import BacktestRunRepository
from app.schemas.enums import BacktestStatus
from app.schemas.error_codes import ErrorCode
from app.repositories.market_repo import MarketRepository
from app.schemas.enums import Market
from app.services.kline_quality import kline_source
from app.strategies.factory import StrategyFactory
from app.strategies.registry import get_strategy_class, import_samples
from app.repositories.strategy_repo import StrategyRepository, StrategyVersionRepository
from app.workers.data_quality import evaluate_data_quality_gate

logger = logging.getLogger(__name__)
PROVENANCE_KEY = "__provenance__"


def _guess_market(symbol: str) -> Market:
    upper = symbol.upper()
    if upper.startswith(("IF", "IC", "IH", "IM", "RB")) or "." not in symbol:
        return Market.FUTURES
    return Market.STOCK


def _build_provenance(db: Session, request: BacktestCreateRequest) -> dict:
    import_samples()
    repo = StrategyRepository(db)
    row = repo.get_by_strategy_id(request.strategy_id)

    if row and row.kind == "rule":
        version = request.strategy_version or row.current_version
        ver_row = StrategyVersionRepository(db).get_version(request.strategy_id, version) if version else None
        strategy_version = f"v{version}" if version else "unversioned"
        code_hash = f"sha256:{ver_row.checksum}" if ver_row else "unknown"
        warmup_bars = None
        if ver_row:
            from app.strategies.rule_strategy import RuleStrategy
            from app.strategies.rule_validator import resolve_parameters

            rs = RuleStrategy(
                strategy_id=row.strategy_id,
                name=row.name,
                definition=ver_row.definition,
                parameters=resolve_parameters(ver_row.definition, request.parameters),
                version=version or 1,
            )
            warmup_bars = rs.warmup_bars
    else:
        strategy_cls = get_strategy_class(request.strategy_id)
        strategy_source = inspect.getsource(strategy_cls)
        code_hash = f"sha256:{hashlib.sha256(strategy_source.encode('utf-8')).hexdigest()}"
        strategy_version = getattr(strategy_cls, "version", "unversioned")
        warmup_bars = None

    snapshot_hasher = hashlib.sha256()
    bar_count = 0
    first_bar = None
    last_bar = None
    sources: set[str] = set()
    repo = MarketRepository(db)
    for symbol in sorted(request.symbols):
        rows = repo.query_klines(
            market=_guess_market(symbol),
            symbol=symbol,
            interval=request.interval,
            start=request.start_time,
            end=request.end_time,
            limit=10000,
        )
        for row in reversed(rows):
            payload = [
                row.market.value,
                row.symbol,
                row.interval,
                row.bar_time.isoformat(),
                str(row.open),
                str(row.high),
                str(row.low),
                str(row.close),
                str(row.volume),
                kline_source(row.raw_payload),
            ]
            snapshot_hasher.update(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            )
            bar_count += 1
            first_bar = first_bar or row.bar_time.isoformat()
            last_bar = row.bar_time.isoformat()
            sources.add(kline_source(row.raw_payload))

    return {
        "recorded": True,
        "strategy_version": strategy_version,
        "code_hash": code_hash,
        "data_snapshot": f"sha256:{snapshot_hasher.hexdigest()}",
        "bar_count": bar_count,
        "first_bar": first_bar,
        "last_bar": last_bar,
        "sources": sorted(sources),
        "warmup_bars": warmup_bars,
        "strategy_version_number": request.strategy_version,
    }


def _legacy_provenance() -> dict:
    return {
        "recorded": False,
        "strategy_version": "历史未记录",
        "code_hash": "历史未记录",
        "data_snapshot": "历史未记录",
        "bar_count": None,
        "sources": [],
    }


def _result_from_row(row: BacktestRun) -> BacktestResult:
    parameters = dict(row.parameters or {})
    provenance = parameters.pop(PROVENANCE_KEY, None) or _legacy_provenance()
    error_message = row.error_message
    if error_message and row.strategy_id in error_message:
        import_samples()
        try:
            get_strategy_class(row.strategy_id)
        except KeyError:
            pass
        else:
            error_message = "历史运行环境未加载该策略；当前版本已支持，请重新运行。"
    return BacktestResult(
        id=row.id,
        strategy_id=row.strategy_id,
        status=row.status,
        parameters=parameters,
        symbols=row.symbols,
        start_time=row.start_time,
        end_time=row.end_time,
        granularity=row.granularity,
        fill_model=row.fill_model,
        initial_cash=Decimal(str(row.initial_cash)),
        final_equity=Decimal(str(row.final_equity)) if row.final_equity is not None else None,
        metrics=row.metrics_json,
        trades=row.trades_json or [],
        equity_curve=row.equity_curve_json or [],
        error_message=error_message,
        provenance=provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class BacktestService:
    def run_backtest(self, db: Session, request: BacktestCreateRequest) -> BacktestResult:
        StrategyFactory.assert_runnable(
            db, request.strategy_id, version=request.strategy_version
        )
        gate = evaluate_data_quality_gate(
            db,
            targets=[(_guess_market(symbol), symbol) for symbol in request.symbols],
            interval=request.interval,
            start=request.start_time,
            end=request.end_time,
        )
        if not gate["ready"]:
            raise BizError(
                ErrorCode.DATA_QUALITY_NOT_READY,
                f"回测数据未通过准入：{gate['reason']}",
                status=409,
                debug=json.dumps(gate, ensure_ascii=False, default=str),
            )

        repo = BacktestRunRepository(db)
        provenance = _build_provenance(db, request)
        stored_parameters = {
            **request.parameters,
            PROVENANCE_KEY: provenance,
        }
        row = repo.create(
            strategy_id=request.strategy_id,
            parameters=stored_parameters,
            symbols=request.symbols,
            start_time=request.start_time,
            end_time=request.end_time,
            granularity=request.granularity.value,
            fill_model=request.fill_model.value,
            initial_cash=str(request.initial_cash),
            status=BacktestStatus.RUNNING,
        )
        db.commit()

        try:
            runner = BacktestRunner(request, db)
            result = runner.run()
            result = result.model_copy(
                update={"id": row.id, "provenance": provenance}
            )
            repo.update_result(
                row.id,
                status=BacktestStatus.COMPLETED,
                final_equity=str(result.final_equity) if result.final_equity is not None else None,
                metrics_json=result.metrics.model_dump(mode="json") if result.metrics else None,
                trades_json=[t.model_dump(mode="json") for t in result.trades],
                equity_curve_json=[p.model_dump(mode="json") for p in result.equity_curve],
            )
            db.commit()
            return result
        except Exception as exc:
            logger.exception("回测执行失败: %s", row.id)
            repo.update_result(
                row.id,
                status=BacktestStatus.FAILED,
                error_message=str(exc),
            )
            db.commit()
            raise

    def list_backtests(self, db: Session, *, offset: int = 0, limit: int = 20) -> tuple[list[BacktestResult], int]:
        rows, total = BacktestRunRepository(db).list_runs(offset=offset, limit=limit)
        return [_result_from_row(r) for r in rows], total

    def get_backtest(self, db: Session, backtest_id: UUID) -> BacktestResult | None:
        row = BacktestRunRepository(db).get(backtest_id)
        if row is None:
            return None
        return _result_from_row(row)

    def delete_backtest(self, db: Session, backtest_id: UUID) -> bool:
        repo = BacktestRunRepository(db)
        row = repo.get(backtest_id)
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True


backtest_service = BacktestService()
