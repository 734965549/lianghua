import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.response import BizError
from app.api.ws_hub import broadcast_sync
from app.core.config import settings
from app.core.time import to_utc_iso
from app.db.models.account_asset import AccountAsset
from app.db.models.order import Order
from app.db.models.trade import Trade
from app.db.session import check_database
from app.repositories.account_repo import AccountRepository
from app.repositories.asset_repo import AssetRepository
from app.repositories.market_repo import MarketRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.position_repo import PositionRepository
from app.repositories.risk_repo import RiskRepository
from app.repositories.signal_repo import SignalRepository
from app.repositories.system_event_repo import SystemEventRepository
from app.schemas.enums import Market, OrderStatus, RiskResult, Severity, SystemStatus
from app.schemas.error_codes import ErrorCode
from app.sdk import manager as sdk_manager
from app.sdk.models import PlaceOrderRequest
from app.services.audit_service import AuditService
from app.services.account_snapshot_service import AccountSnapshotService
from app.services.quote_health_service import assess_quote_health
from app.services.risk_rules import RULES_ORDERED, RiskContext, RuleResult
from app.services import runtime_metrics
from app.services.system_service import SystemStateService
from app.workers.data_quality import evaluate_data_quality_gate

logger = logging.getLogger(__name__)

ZERO_ACCOUNT_ID = UUID(int=0)

STOPPED_STATUSES = {
    SystemStatus.CIRCUIT_BREAKER.value,
    SystemStatus.EMERGENCY_STOPPED.value,
}


class RiskService:
    def __init__(self, db: Session, correlation_id: str = ""):
        self.db = db
        self.correlation_id = correlation_id
        self.audit = AuditService(db, correlation_id=correlation_id)
        self.repo = RiskRepository(db)
        self.signal_repo = SignalRepository(db)
        self.market_repo = MarketRepository(db)
        self.order_repo = OrderRepository(db)
        self.events = SystemEventRepository(db)
        self.system = SystemStateService(db, correlation_id=correlation_id)

    def check(
        self,
        request: PlaceOrderRequest,
        *,
        signal_id: UUID | None = None,
        exclude_signal_id: UUID | None = None,
    ) -> tuple[bool, list[RuleResult], UUID]:
        """执行风控规则。返回 (是否通过, 规则结果, check_id)。"""
        ctx = self._build_context(request, exclude_signal_id=exclude_signal_id)
        results: list[RuleResult] = []
        passed = True
        for rule_cls in RULES_ORDERED:
            result = rule_cls().check(ctx)
            results.append(result)
            if result.result == "rejected":
                passed = False
                break

        overall = RiskResult.PASSED if passed else RiskResult.REJECTED
        hit_rule = next((r for r in results if r.result == "rejected"), None)
        checked_at = datetime.now(timezone.utc)
        check_row = self.repo.add_check(
            signal_id=signal_id,
            client_order_id=request.client_order_id,
            result=overall,
            rule_code=hit_rule.rule_code if hit_rule else "",
            reason=hit_rule.reason if hit_rule else "all rules passed",
            checked_at=checked_at,
            snapshot={
                "config": ctx.risk_config,
                "system_status": ctx.system_status,
                "asset": ctx.account_asset,
                "positions": ctx.positions[:5],
                "data_quality": ctx.data_quality,
                "results": [{"rule_code": r.rule_code, "result": r.result, "reason": r.reason} for r in results],
            },
        )
        self.audit.log(
            action="risk_check",
            module="risk",
            object_type="signal",
            object_id=str(signal_id or ""),
            result=overall.value,
            reason=hit_rule.reason if hit_rule else "all rules passed",
            request_summary={
                "client_order_id": request.client_order_id,
                "symbol": request.symbol,
                "side": request.side.value,
                "check_id": str(check_row.check_id),
            },
        )
        if not passed:
            broadcast_sync(
                "risk.event",
                {
                    "event": "rejected",
                    "rule_code": hit_rule.rule_code if hit_rule else "",
                    "reason": hit_rule.reason if hit_rule else "",
                    "signal_id": str(signal_id) if signal_id else None,
                    "symbol": request.symbol,
                },
                correlation_id=self.correlation_id,
            )
        return passed, results, check_row.check_id

    def _build_context(
        self,
        request: PlaceOrderRequest,
        *,
        exclude_signal_id: UUID | None = None,
    ) -> RiskContext:
        config_row = self.repo.ensure_config()
        risk_config = self.repo.config_to_dict(config_row)
        status = self.system.get_status()
        now = datetime.now(timezone.utc)

        latest_price = None
        try:
            market = request.market if isinstance(request.market, Market) else Market(request.market)
            quote = self.market_repo.get_latest_quote(market, request.symbol)
            if quote:
                latest_price = Decimal(str(quote.last_price))
        except Exception:
            logger.debug("获取最新行情失败", exc_info=True)

        data_quality = None
        live_trading = settings.sdk_mode.strip().lower() == "real" or settings.broker_type.strip().lower() in {
            "qmt",
            "ptrade",
        }
        if live_trading:
            data_quality = evaluate_data_quality_gate(
                self.db,
                targets=[(Market(request.market), request.symbol)],
                interval="1d",
            )

        window = int(risk_config.get("duplicate_signal_window_seconds", 3))
        strategy_id = request.metadata.get("strategy_id", "")
        side = request.side
        action = request.action
        recent_rows = self.signal_repo.recent_duplicates(
            strategy_id=strategy_id,
            symbol=request.symbol,
            side=side,
            action=action,
            window_seconds=window,
            now=now,
        )
        recent_signals = [
            {
                "strategy_id": row.strategy_id,
                "symbol": row.symbol,
                "side": row.side.value,
                "action": row.action.value,
                "ts": row.signal_time.timestamp(),
            }
            for row in recent_rows
            if exclude_signal_id is None or row.signal_id != exclude_signal_id
        ]

        account_asset = self._latest_account_asset_dict(request.market)
        positions = self._latest_positions(request.market)

        return RiskContext(
            request=request,
            system_status=status["status"],
            risk_config=risk_config,
            account_asset=account_asset,
            positions=positions,
            today_trade_count=self._today_trade_count(),
            # 规则侧用负数表示亏损：today_pnl < 0 且 |pnl| >= limit 时拒绝
            today_pnl=-self._today_loss(),
            recent_signals=recent_signals,
            now=now,
            latest_price=latest_price,
            data_quality=data_quality,
        )

    def _latest_account_asset_dict(self, market: Market | str) -> dict:
        try:
            mkt = market if isinstance(market, Market) else Market(market)
            account = AccountRepository(self.db).get_or_create_default(mkt)
            row = AssetRepository(self.db).get_latest(account.id)
            if row is None:
                return {"available_cash": "0", "total_asset": "0"}
            return {
                "available_cash": str(row.available_cash),
                "total_asset": str(row.total_asset),
            }
        except Exception:
            logger.debug("读取账户资金失败", exc_info=True)
            return {"available_cash": "0", "total_asset": "0"}

    def _latest_positions(self, market: Market | str) -> list[dict]:
        try:
            mkt = market if isinstance(market, Market) else Market(market)
            rows = PositionRepository(self.db).list_latest(market=mkt, limit=50)
            return [
                {
                    "symbol": r.symbol,
                    "quantity": str(r.quantity),
                    "market_value": str(r.market_value),
                    "direction": r.direction.value if hasattr(r.direction, "value") else str(r.direction),
                }
                for r in rows
            ]
        except Exception:
            logger.debug("读取持仓失败", exc_info=True)
            return []

    def _today_start(self) -> datetime:
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _today_trade_count(self) -> int:
        start = self._today_start()
        return (
            self.db.query(func.count(Trade.id))
            .filter(Trade.trade_time >= start)
            .scalar()
            or 0
        )

    def _today_loss(self) -> Decimal:
        """当日亏损 = 当日权益峰值 - 当前权益（多账户合计）。"""
        start = self._today_start()
        accounts = self.db.query(AccountAsset.account_id).distinct().all()
        total_loss = Decimal("0")
        for (account_id,) in accounts:
            rows = (
                self.db.query(AccountAsset)
                .filter(
                    AccountAsset.account_id == account_id,
                    AccountAsset.snapshot_time >= start,
                )
                .order_by(AccountAsset.snapshot_time.asc())
                .all()
            )
            if not rows:
                latest = AssetRepository(self.db).get_latest(account_id)
                if latest is None:
                    continue
                rows = [latest]
            peak = max(Decimal(str(r.total_asset)) for r in rows)
            current = Decimal(str(rows[-1].total_asset))
            loss = peak - current
            if loss > 0:
                total_loss += loss
        return total_loss

    def get_settings(self) -> dict:
        return self.repo.config_to_dict()

    def update_settings(self, updates: dict, *, reason: str = "") -> dict:
        normalized: dict = {}
        decimal_fields = {
            "max_order_amount",
            "max_order_quantity",
            "max_symbol_position",
            "max_total_position",
            "daily_loss_limit",
        }
        for key, value in updates.items():
            if value is None or key == "reason":
                continue
            if key in decimal_fields:
                normalized[key] = Decimal(str(value))
            else:
                normalized[key] = value
        row = self.repo.update_config(normalized)
        self.audit.log(
            action="risk_settings_update",
            module="risk",
            object_type="risk_config",
            object_id="1",
            result="success",
            reason=reason,
            request_summary=updates,
        )
        return self.repo.config_to_dict(row)

    def count_unknown_orders(self) -> int:
        return (
            self.db.query(func.count(Order.id))
            .filter(Order.status == OrderStatus.UNKNOWN)
            .scalar()
            or 0
        )

    def get_status(self) -> dict:
        system = self.system.get_status()
        config = self.repo.config_to_dict()
        status = system["status"]
        breaker_active = status in STOPPED_STATUSES
        daily_loss = self._today_loss()
        return {
            "system_status": status,
            "status_reason": system.get("status_reason", ""),
            "breaker_active": breaker_active,
            "breaker_reason": system.get("breaker_reason") or (
                system.get("status_reason", "") if breaker_active else ""
            ),
            "daily_loss": str(daily_loss),
            "daily_loss_limit": str(config.get("daily_loss_limit", "0")),
            "daily_trade_count": self._today_trade_count(),
            "consecutive_order_fail": runtime_metrics.get_consecutive_order_fail(),
            "unknown_order_count": self.count_unknown_orders(),
            "allowed_symbols": config.get("allowed_symbols", []),
            "blocked_symbols": config.get("blocked_symbols", []),
            "trading_sessions": config.get("trading_sessions", []),
            "limits": {
                "max_order_amount": config.get("max_order_amount"),
                "max_order_quantity": config.get("max_order_quantity"),
                "daily_loss_limit": config.get("daily_loss_limit"),
                "daily_trade_count_limit": config.get("daily_trade_count_limit"),
            },
        }

    def list_checks(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        result: str | None = None,
    ) -> dict:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        offset = (page - 1) * page_size
        risk_result = RiskResult(result) if result else None
        rows, total = self.repo.list_checks(offset=offset, limit=page_size, result=risk_result)
        items = [
            {
                "check_id": str(row.check_id),
                "signal_id": str(row.signal_id) if row.signal_id else None,
                "client_order_id": row.client_order_id,
                "result": row.result.value,
                "rule_code": row.rule_code,
                "reason": row.reason,
                "checked_at": to_utc_iso(row.checked_at),
            }
            for row in rows
        ]
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def _cancel_open_orders(self, *, reason: str) -> int:
        """撤销可撤未成交委托，返回成功笔数。"""
        from app.services.trade_service import trade_service

        open_orders = self.order_repo.list_open_orders(limit=200)
        cancelled = 0
        for order in open_orders:
            if order.status not in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}:
                continue
            try:
                trade_service.cancel(
                    order.client_order_id,
                    reason=reason,
                    correlation_id=self.correlation_id,
                )
                cancelled += 1
            except Exception:
                logger.warning("自动撤单失败: %s", order.client_order_id, exc_info=True)
        return cancelled

    def emergency_stop(self, reason: str, cancel_open_orders: bool = True) -> dict:
        status = self.system.get_status()["status"]
        if status == SystemStatus.EMERGENCY_STOPPED.value:
            raise BizError(ErrorCode.RISK_ALREADY_STOPPED, "系统已处于紧急停止状态")

        self.system.transition(SystemStatus.EMERGENCY_STOPPED, reason=reason)
        self.db.flush()

        cancelled = 0
        if cancel_open_orders:
            cancelled = self._cancel_open_orders(reason="emergency_stop")

        self.events.add(
            module="risk",
            event_code="EMERGENCY_STOP",
            message=reason,
            severity=Severity.CRITICAL,
            payload={"cancel_open_orders": cancel_open_orders, "cancelled_orders": cancelled},
        )
        self.audit.log(
            action="emergency_stop",
            module="risk",
            object_type="system_state",
            object_id="1",
            result="success",
            reason=reason,
            request_summary={"cancel_open_orders": cancel_open_orders, "cancelled_orders": cancelled},
        )
        broadcast_sync(
            "risk.event",
            {"event": "emergency_stop", "reason": reason, "cancelled_orders": cancelled},
            correlation_id=self.correlation_id,
        )
        return {
            "status": SystemStatus.EMERGENCY_STOPPED.value,
            "cancelled_orders": cancelled,
            **self.get_status(),
        }

    def trigger_breaker(self, reason: str) -> dict | None:
        """触发熔断；已处于熔断/紧急停止则跳过。"""
        status = self.system.get_status()["status"]
        if status in STOPPED_STATUSES:
            return None

        self.system.transition(SystemStatus.CIRCUIT_BREAKER, reason=reason)
        self.db.flush()

        config = self.repo.config_to_dict()
        cancelled = 0
        if config.get("auto_cancel_on_breaker", True):
            cancelled = self._cancel_open_orders(reason="circuit_breaker")

        self.events.add(
            module="risk",
            event_code="CIRCUIT_BREAKER",
            message=reason,
            severity=Severity.CRITICAL,
            payload={"cancelled_orders": cancelled},
        )
        self.audit.log(
            action="trigger_breaker",
            module="risk",
            object_type="system_state",
            object_id="1",
            result="success",
            reason=reason,
            request_summary={"cancelled_orders": cancelled},
        )
        broadcast_sync(
            "risk.event",
            {"type": "breaker", "reason": reason, "cancelled_orders": cancelled},
            correlation_id=self.correlation_id,
        )
        logger.warning("熔断触发: %s (撤单 %d)", reason, cancelled)
        return {"status": SystemStatus.CIRCUIT_BREAKER.value, "cancelled_orders": cancelled}

    def _has_unknown_orders(self) -> bool:
        return self.count_unknown_orders() > 0

    def _sdk_healthy(self) -> bool:
        sdk_manager.refresh_sdk_connection_metrics()
        return sdk_manager.sdk_healthy()

    def _db_healthy(self) -> bool:
        return check_database() == "connected"

    def get_resume_checklist(self) -> dict:
        config = self.repo.config_to_dict()
        sdk_healthy = self._sdk_healthy()
        quote_health = assess_quote_health(
            self.db,
            timeout_seconds=int(
                config.get("quote_stale_timeout_seconds", 10) or 10
            ),
        )
        account_snapshot = AccountSnapshotService(self.db).get_snapshot()
        unknown_count = self.count_unknown_orders()
        daily_loss_limit = Decimal(
            str(config.get("daily_loss_limit", "0") or "0")
        )
        fail_limit = int(
            config.get("consecutive_order_fail_limit", 5) or 5
        )
        trade_limit = int(config.get("daily_trade_count_limit", 0) or 0)
        today_loss = self._today_loss()
        consecutive_failures = runtime_metrics.get_consecutive_order_fail()
        today_trade_count = self._today_trade_count()
        checks = [
            {
                "code": "database",
                "label": "数据库连接",
                "passed": self._db_healthy(),
                "detail": "数据库可用",
            },
            {
                "code": "channel",
                "label": "交易通道",
                "passed": sdk_healthy,
                "detail": "SDK 已连接" if sdk_healthy else "SDK 未连接",
            },
            {
                "code": "market_data",
                "label": "行情状态",
                "passed": quote_health["trade_ready"],
                "detail": {
                    "healthy": "交易时段行情有效",
                    "market_closed": "当前为正常休市",
                    "not_monitored": "当前无活动行情订阅",
                    "source_disconnected": "行情源连接中断",
                    "subscription_disconnected": "行情订阅未收到有效数据",
                    "feed_stale": "交易时段行情已停更",
                }.get(quote_health["state"], quote_health["state"]),
                "data": quote_health,
            },
            {
                "code": "unknown_orders",
                "label": "未知订单",
                "passed": unknown_count == 0,
                "detail": (
                    "未知订单已清零"
                    if unknown_count == 0
                    else f"存在 unknown 状态订单未处理：{unknown_count} 笔"
                ),
            },
            {
                "code": "account_reconciliation",
                "label": "账户核对",
                "passed": bool(account_snapshot["reconciled"]),
                "detail": (
                    "无账户资金快照"
                    if not account_snapshot["has_account_snapshot"]
                    else f"账户快照 {account_snapshot['snapshot_id']} 已核平"
                    if account_snapshot["reconciled"]
                    else (
                        "账户资金与持仓未核平，差额 "
                        f"{account_snapshot['market_value_delta']}"
                    )
                ),
                "snapshot_id": account_snapshot["snapshot_id"],
            },
            {
                "code": "daily_loss",
                "label": "当日亏损",
                "passed": (
                    daily_loss_limit <= 0
                    or today_loss < daily_loss_limit
                ),
                "detail": (
                    f"当日亏损 {today_loss:,.2f} / 限制 {daily_loss_limit:,.2f}"
                ),
            },
            {
                "code": "order_failures",
                "label": "连续下单失败",
                "passed": (
                    fail_limit <= 0
                    or consecutive_failures < fail_limit
                ),
                "detail": f"连续失败 {consecutive_failures} / 限制 {fail_limit}",
            },
            {
                "code": "trade_count",
                "label": "当日交易次数",
                "passed": (
                    trade_limit <= 0
                    or today_trade_count < trade_limit
                ),
                "detail": f"当日交易 {today_trade_count} / 限制 {trade_limit}",
            },
        ]
        return {
            "all_passed": all(item["passed"] for item in checks),
            "checks": checks,
            "checked_at": to_utc_iso(datetime.now(timezone.utc)),
        }

    def _collect_resume_blockers(self) -> list[str]:
        checklist = self.get_resume_checklist()
        return [
            item["detail"]
            for item in checklist["checks"]
            if not item["passed"]
        ]

    def resume(self, reason: str) -> dict:
        if not (reason or "").strip():
            raise BizError(ErrorCode.RISK_RESUME_REASON_REQUIRED, "恢复交易必须填写原因")
        status = self.system.get_status()
        current = status["status"]
        if current not in {
            SystemStatus.CIRCUIT_BREAKER.value,
            SystemStatus.EMERGENCY_STOPPED.value,
            SystemStatus.PAUSED.value,
        }:
            raise BizError(ErrorCode.RISK_RESUME_BLOCKED, f"当前状态 {current} 不支持恢复交易")

        blockers = self._collect_resume_blockers()
        if blockers:
            if any("unknown" in b for b in blockers):
                raise BizError(
                    ErrorCode.RISK_UNKNOWN_ORDERS_PENDING,
                    "存在未知订单未处理，禁止恢复交易",
                    debug="; ".join(blockers),
                )
            raise BizError(
                ErrorCode.RISK_RESUME_BLOCKED,
                "恢复被阻止：" + "；".join(blockers),
                debug="; ".join(blockers),
            )

        self.system.transition(SystemStatus.TRADING, reason=reason.strip())
        resumed_at = datetime.now(timezone.utc).isoformat()
        self.audit.log(
            action="risk_resume",
            module="risk",
            object_type="system_state",
            object_id="1",
            result="success",
            reason=reason.strip(),
        )
        broadcast_sync(
            "risk.event",
            {"type": "resume", "reason": reason.strip(), "resumed_at": resumed_at},
            correlation_id=self.correlation_id,
        )
        return {
            "status": SystemStatus.TRADING.value,
            "resumed_at": resumed_at,
            **self.get_status(),
        }

    # ---- 熔断条件检查（供 breaker_monitor 调用）----

    def _today_loss_exceeds_limit(self) -> bool:
        config = self.repo.config_to_dict()
        limit = Decimal(str(config.get("daily_loss_limit", "0") or "0"))
        if limit <= 0:
            return False
        return self._today_loss() >= limit

    def _sdk_disconnected_too_long(self) -> bool:
        sdk_manager.refresh_sdk_connection_metrics()
        since = runtime_metrics.get_sdk_disconnect_since()
        if since is None:
            return False
        config = self.repo.config_to_dict()
        timeout = int(config.get("sdk_disconnect_timeout_seconds", 30) or 30)
        age = (datetime.now(timezone.utc) - since).total_seconds()
        return age >= timeout

    def _quotes_stale(self) -> bool:
        config = self.repo.config_to_dict()
        timeout = int(config.get("quote_stale_timeout_seconds", 10) or 10)
        health = assess_quote_health(
            self.db,
            timeout_seconds=timeout,
        )
        return bool(health["breaker_required"])

    def _consecutive_fail_exceeds(self) -> bool:
        config = self.repo.config_to_dict()
        limit = int(config.get("consecutive_order_fail_limit", 5) or 5)
        return runtime_metrics.get_consecutive_order_fail() >= limit

    def _order_state_inconsistent(self) -> bool:
        """成交回报与订单状态不一致：超量成交、终态数量不符、成交汇总与 filled 不符。"""
        if (
            self.db.query(Order)
            .filter(Order.filled_quantity > Order.quantity)
            .limit(1)
            .first()
        ) is not None:
            return True

        # 已标记 FILLED 但成交量仍不足
        if (
            self.db.query(Order)
            .filter(
                Order.status == OrderStatus.FILLED,
                Order.filled_quantity < Order.quantity,
            )
            .limit(1)
            .first()
        ) is not None:
            return True

        # 非终态却显示已全部成交
        open_statuses = [
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
        ]
        if (
            self.db.query(Order)
            .filter(
                Order.status.in_(open_statuses),
                Order.filled_quantity >= Order.quantity,
                Order.quantity > 0,
            )
            .limit(1)
            .first()
        ) is not None:
            return True

        # 成交汇总与订单 filled_quantity 不一致
        trade_sums = (
            self.db.query(Trade.client_order_id, func.sum(Trade.quantity).label("qty"))
            .group_by(Trade.client_order_id)
            .subquery()
        )
        mismatch = (
            self.db.query(Order)
            .join(trade_sums, Order.client_order_id == trade_sums.c.client_order_id)
            .filter(Order.filled_quantity != trade_sums.c.qty)
            .limit(1)
            .first()
        )
        return mismatch is not None

    def check_breaker_conditions(self) -> str | None:
        """检查熔断条件，命中则触发并返回原因。"""
        status = self.system.get_status()["status"]
        if status in STOPPED_STATUSES:
            return None

        checks = [
            (self._today_loss_exceeds_limit, "当日亏损达到阈值"),
            (self._sdk_disconnected_too_long, "SDK 断线超时"),
            (self._quotes_stale, "行情长时间无更新"),
            (self._consecutive_fail_exceeds, "连续下单失败超过阈值"),
            (self._order_state_inconsistent, "成交回报与订单状态不一致"),
        ]
        for pred, reason in checks:
            try:
                if pred():
                    self.trigger_breaker(reason)
                    return reason
            except Exception:
                logger.exception("熔断条件检查异常: %s", reason)
        return None
