import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.api.ws_hub import broadcast_sync
from app.db.session import SessionLocal
from app.repositories.market_repo import MarketRepository
from app.repositories.signal_repo import SignalRepository
from app.repositories.strategy_repo import StrategyRepository, StrategyRunRepository
from app.schemas.enums import Market, StrategyRunStatus, SystemStatus
from app.sdk.models import KlineBar, PlaceOrderRequest, QuoteSnapshot
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService, ZERO_ACCOUNT_ID
from app.services.system_service import SystemStateService
from app.strategies.context import StrategyContext
from app.strategies.registry import get_strategy_class, import_samples, list_strategies

logger = logging.getLogger(__name__)


@dataclass
class _BarBuilder:
    symbol: str
    market: Market
    interval: str
    bar_time: datetime | None = None
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")

    def update(self, quote: QuoteSnapshot) -> KlineBar | None:
        bucket = quote.quote_time.replace(second=0, microsecond=0)
        if self.bar_time is None:
            self._start_bar(bucket, quote)
            return None
        if bucket != self.bar_time:
            finished = self._to_bar()
            self._start_bar(bucket, quote)
            return finished
        price = quote.last_price
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += quote.volume or Decimal("0")
        return None

    def _start_bar(self, bar_time: datetime, quote: QuoteSnapshot) -> None:
        self.bar_time = bar_time
        self.open = quote.last_price
        self.high = quote.last_price
        self.low = quote.last_price
        self.close = quote.last_price
        self.volume = quote.volume or Decimal("0")

    def _to_bar(self) -> KlineBar:
        return KlineBar(
            symbol=self.symbol,
            market=self.market,
            interval=self.interval,
            bar_time=self.bar_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


@dataclass
class _RunningStrategy:
    instance: object
    context: StrategyContext
    run_id: UUID
    symbols: set[str]
    interval: str
    bar_builders: dict[str, _BarBuilder] = field(default_factory=dict)


class _MarketDataReader:
    def __init__(self, db: Session):
        self.repo = MarketRepository(db)

    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> list[KlineBar]:
        market = _guess_market(symbol)
        rows = self.repo.query_klines(market=market, symbol=symbol, interval=interval, limit=limit)
        return [
            KlineBar(
                symbol=row.symbol,
                market=row.market,
                interval=row.interval,
                bar_time=row.bar_time,
                open=Decimal(str(row.open)),
                high=Decimal(str(row.high)),
                low=Decimal(str(row.low)),
                close=Decimal(str(row.close)),
                volume=Decimal(str(row.volume)),
            )
            for row in reversed(rows)
        ]

    def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        market = _guess_market(symbol)
        row = self.repo.get_latest_quote(market, symbol)
        if row is None:
            return None
        return QuoteSnapshot(
            symbol=row.symbol,
            market=row.market,
            last_price=Decimal(str(row.last_price)),
            change_rate=Decimal(str(row.change_rate)),
            volume=Decimal(str(row.volume)),
            bid_price=Decimal(str(row.bid_price)) if row.bid_price is not None else None,
            ask_price=Decimal(str(row.ask_price)) if row.ask_price is not None else None,
            quote_time=row.quote_time,
        )


class _AccountReader:
    def get_position(self, symbol: str) -> dict | None:
        return None

    def get_account(self) -> dict:
        return {"available_cash": "0", "total_asset": "0"}


def _guess_market(symbol: str) -> Market:
    upper = symbol.upper()
    if upper.startswith("IF") or upper.startswith("RB") or "." not in symbol:
        return Market.FUTURES
    return Market.STOCK


def _decimal_str(value) -> str:
    if value is None:
        return "0"
    return str(value)


class StrategyService:
    def __init__(self):
        self._running: dict[str, _RunningStrategy] = {}
        self._samples_loaded = False

    def _ensure_samples(self) -> None:
        if not self._samples_loaded:
            import_samples()
            self._samples_loaded = True

    def _get_db_services(self, db: Session, correlation_id: str = ""):
        return {
            "strategy_repo": StrategyRepository(db),
            "run_repo": StrategyRunRepository(db),
            "signal_repo": SignalRepository(db),
            "audit": AuditService(db, correlation_id=correlation_id),
            "risk": RiskService(db, correlation_id=correlation_id),
            "system": SystemStateService(db, correlation_id=correlation_id),
        }

    def ensure_definitions(self, db: Session) -> None:
        self._ensure_samples()
        repo = StrategyRepository(db)
        for cls in list_strategies():
            defaults = cls.param_schema().model_dump(mode="json")
            existing = repo.get_by_strategy_id(cls.strategy_id)
            repo.upsert_definition(
                strategy_id=cls.strategy_id,
                name=cls.name,
                description=cls.description,
                enabled=True,
                parameters=defaults if existing is None else None,
                supported_markets=cls.supported_markets,
            )

    def list_strategies(self, db: Session) -> list[dict]:
        self.ensure_definitions(db)
        db_rows = {r.strategy_id: r for r in StrategyRepository(db).list_all()}
        items = []
        for cls in list_strategies():
            row = db_rows.get(cls.strategy_id)
            items.append(
                {
                    "strategy_id": cls.strategy_id,
                    "name": cls.name,
                    "description": cls.description,
                    "enabled": row.enabled if row else True,
                    "parameters": row.parameters if row else cls.param_schema().model_dump(mode="json"),
                    "supported_markets": cls.supported_markets,
                    "parameters_schema": cls.param_schema.model_json_schema(),
                    "running": cls.strategy_id in self._running,
                }
            )
        return items

    def get_strategy(self, db: Session, strategy_id: str) -> dict:
        self.ensure_definitions(db)
        row = StrategyRepository(db).get_by_strategy_id(strategy_id)
        if row is None:
            raise BizError("STRATEGY_NOT_FOUND", f"策略不存在: {strategy_id}")
        cls = get_strategy_class(strategy_id)
        return {
            "strategy_id": row.strategy_id,
            "name": row.name,
            "description": row.description,
            "enabled": row.enabled,
            "parameters": row.parameters,
            "supported_markets": row.supported_markets,
            "parameters_schema": cls.param_schema.model_json_schema(),
            "running": strategy_id in self._running,
        }

    def update_parameters(self, db: Session, strategy_id: str, parameters: dict, correlation_id: str = "") -> dict:
        self.ensure_definitions(db)
        repo = StrategyRepository(db)
        cls = get_strategy_class(strategy_id)
        validated = cls.param_schema(**parameters).model_dump(mode="json")
        row = repo.update_parameters(strategy_id, validated)
        if row is None:
            raise BizError("STRATEGY_NOT_FOUND", f"策略不存在: {strategy_id}")
        AuditService(db, correlation_id=correlation_id).log(
            action="strategy_parameters_update",
            module="strategy",
            object_type="strategy",
            object_id=strategy_id,
            result="success",
            request_summary={"parameters": validated},
        )
        return self.get_strategy(db, strategy_id)

    def start(
        self,
        db: Session,
        strategy_id: str,
        *,
        symbols: list[str] | None = None,
        parameters: dict | None = None,
        confirm: bool = False,
        correlation_id: str = "",
    ) -> dict:
        if not confirm:
            raise BizError("STRATEGY_CONFIRM_REQUIRED", "启动策略需要 confirm=true")

        self._ensure_samples()
        if strategy_id in self._running:
            raise BizError("STRATEGY_ALREADY_RUNNING", "策略已在运行")

        svc = self._get_db_services(db, correlation_id)
        row = svc["strategy_repo"].get_by_strategy_id(strategy_id)
        if row is None or not row.enabled:
            raise BizError("STRATEGY_NOT_FOUND", f"策略不存在或未启用: {strategy_id}")

        cls = get_strategy_class(strategy_id)
        params = dict(row.parameters)
        if parameters:
            params.update(parameters)
        if symbols:
            params["symbols"] = symbols
        validated = cls.param_schema(**params).model_dump(mode="json")

        system_status = svc["system"].get_status()["status"]
        if system_status == SystemStatus.READY.value:
            svc["system"].transition(SystemStatus.TRADING, reason=f"启动策略 {strategy_id}")
        elif system_status != SystemStatus.TRADING.value:
            raise BizError(
                "RISK_SYSTEM_STOPPED",
                f"系统状态 {system_status} 不允许启动策略",
            )

        run = svc["run_repo"].create_run(
            strategy_id=strategy_id,
            status=StrategyRunStatus.RUNNING,
            parameters=validated,
        )
        interval = validated.get("interval", "1m")
        symbol_set = set(validated.get("symbols", []))

        def signal_sink(**kwargs):
            self._on_signal(run.id, correlation_id=correlation_id, **kwargs)

        def strategy_logger(level, sid, message, extra):
            logger.log(getattr(logging, level.upper(), logging.INFO), "[%s] %s %s", sid, message, extra)

        ctx = StrategyContext(
            strategy_id=strategy_id,
            run_id=str(run.id),
            parameters=validated,
            market_data_reader=_MarketDataReader(db),
            account_reader=_AccountReader(),
            signal_sink=signal_sink,
            logger=strategy_logger,
        )
        instance = cls(validated)
        instance.on_start(ctx)

        builders = {
            sym: _BarBuilder(symbol=sym, market=_guess_market(sym), interval=interval)
            for sym in symbol_set
        }
        self._running[strategy_id] = _RunningStrategy(
            instance=instance,
            context=ctx,
            run_id=run.id,
            symbols=symbol_set,
            interval=interval,
            bar_builders=builders,
        )

        svc["audit"].log(
            action="strategy_start",
            module="strategy",
            object_type="strategy_run",
            object_id=str(run.id),
            result="success",
            request_summary={"strategy_id": strategy_id, "parameters": validated},
        )
        return {"run_id": str(run.id), "status": "running", "strategy_id": strategy_id}

    def stop(
        self,
        db: Session,
        strategy_id: str,
        *,
        reason: str = "用户停止",
        correlation_id: str = "",
    ) -> dict:
        running = self._running.pop(strategy_id, None)
        if running is None:
            raise BizError("STRATEGY_NOT_RUNNING", "策略未运行")

        running.instance.on_stop()
        svc = self._get_db_services(db, correlation_id)
        svc["run_repo"].finish_run(running.run_id, status=StrategyRunStatus.STOPPED, reason=reason)
        svc["audit"].log(
            action="strategy_stop",
            module="strategy",
            object_type="strategy",
            object_id=strategy_id,
            result="success",
            reason=reason,
        )
        return {"status": "stopped", "strategy_id": strategy_id}

    def dispatch_quote(self, quote: QuoteSnapshot) -> None:
        if not self._running:
            return
        db = SessionLocal()
        try:
            for strategy_id, running in list(self._running.items()):
                try:
                    running.instance.on_quote(quote)
                except Exception as exc:
                    logger.exception("策略 %s on_quote 异常", strategy_id)
                    running.context.log("error", f"on_quote 异常: {exc}")

                if quote.symbol not in running.symbols:
                    continue
                builder = running.bar_builders.get(quote.symbol)
                if builder is None:
                    continue
                finished = builder.update(quote)
                if finished is not None:
                    try:
                        running.instance.on_bar(finished)
                    except Exception as exc:
                        logger.exception("策略 %s on_bar 异常", strategy_id)
                        running.context.log("error", f"on_bar 异常: {exc}")
            db.commit()
        except Exception:
            logger.exception("dispatch_quote 失败")
            db.rollback()
        finally:
            db.close()

    def _on_signal(
        self,
        run_id: UUID,
        *,
        correlation_id: str = "",
        signal_id: str,
        strategy_id: str,
        symbol: str,
        market,
        side,
        action,
        price_type,
        price,
        quantity,
        reason: str,
        signal_time: datetime,
        metadata: dict | None = None,
    ) -> None:
        from app.schemas.enums import Market as MarketEnum, OrderSide, PriceType, SignalAction

        db = SessionLocal()
        try:
            if isinstance(market, str):
                market = MarketEnum(market)
            if isinstance(side, str):
                side = OrderSide(side)
            if isinstance(action, str):
                action = SignalAction(action)
            if isinstance(price_type, str):
                price_type = PriceType(price_type)

            sid = UUID(signal_id) if isinstance(signal_id, str) else signal_id
            signal_repo = SignalRepository(db)
            sig = signal_repo.add_signal(
                signal_id=sid,
                strategy_id=strategy_id,
                symbol=symbol,
                market=market,
                side=side,
                action=action,
                price_type=price_type,
                price=Decimal(str(price)),
                quantity=Decimal(str(quantity)),
                reason=reason,
                signal_time=signal_time if signal_time.tzinfo else signal_time.replace(tzinfo=timezone.utc),
                metadata=metadata,
            )
            db.flush()

            audit = AuditService(db, correlation_id=correlation_id)
            audit.log(
                action="strategy_signal",
                module="strategy",
                object_type="signal",
                object_id=str(sig.signal_id),
                result="success",
                request_summary={
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "side": side.value,
                    "action": action.value,
                },
            )
            broadcast_sync(
                "strategy.signal",
                {
                    "signal_id": str(sig.signal_id),
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "market": market.value,
                    "side": side.value,
                    "action": action.value,
                    "price": _decimal_str(sig.price),
                    "quantity": _decimal_str(sig.quantity),
                    "reason": reason,
                    "signal_time": sig.signal_time.isoformat(),
                },
                correlation_id=correlation_id,
            )

            client_order_id = f"lh_{sig.signal_time:%Y%m%d}_{sig.signal_id.hex[:8]}"
            request = PlaceOrderRequest(
                client_order_id=client_order_id,
                account_id=ZERO_ACCOUNT_ID,
                market=market,
                symbol=symbol,
                side=side,
                action=action,
                price_type=price_type,
                price=Decimal(str(sig.price)) if sig.price else None,
                quantity=Decimal(str(sig.quantity)),
                metadata={"strategy_id": strategy_id, "run_id": str(run_id)},
            )
            risk = RiskService(db, correlation_id=correlation_id)
            passed, results = risk.check(request, signal_id=sig.signal_id, exclude_signal_id=sig.signal_id)
            db.commit()
            if passed:
                from app.services.order_service import order_service

                order_service.create_from_signal(db, sig, request, correlation_id=correlation_id)
                logger.info("信号 %s 风控通过，已创建订单", sig.signal_id)
            else:
                hit = next((r for r in results if r.result == "rejected"), None)
                logger.info(
                    "信号 %s 风控拒绝: %s",
                    sig.signal_id,
                    hit.reason if hit else "unknown",
                )
        except Exception:
            logger.exception("处理策略信号失败")
            db.rollback()
        finally:
            db.close()


strategy_service = StrategyService()
