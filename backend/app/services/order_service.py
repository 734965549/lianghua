import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.api.ws_hub import broadcast_sync
from app.core.time import to_utc_iso
from app.db.models.order import Order
from app.db.models.strategy_signal import StrategySignal
from app.db import session as db_session
from app.repositories.account_repo import AccountRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.risk_repo import RiskRepository
from app.schemas.enums import OrderStatus, RiskResult, Severity
from app.schemas.error_codes import ErrorCode
from app.sdk.models import OrderUpdateEvent, PlaceOrderRequest
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING_RISK: {OrderStatus.RISK_REJECTED, OrderStatus.SUBMITTING},
    OrderStatus.SUBMITTING: {OrderStatus.SUBMITTED, OrderStatus.FAILED, OrderStatus.UNKNOWN},
    OrderStatus.SUBMITTED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.UNKNOWN,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.UNKNOWN,
    },
    OrderStatus.UNKNOWN: {
        OrderStatus.CANCELLED,
        OrderStatus.FILLED,
        OrderStatus.FAILED,
    },
}

CANCELLABLE = {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}

UNKNOWN_RESOLVABLE = {
    OrderStatus.CANCELLED,
    OrderStatus.FILLED,
    OrderStatus.FAILED,
}


def _decimal_str(value: Decimal | float | None) -> str:
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return str(value)
    return str(Decimal(str(value)))


def order_to_dict(row: Order) -> dict:
    return {
        "id": str(row.id),
        "client_order_id": row.client_order_id,
        "sdk_order_id": row.sdk_order_id,
        "account_id": str(row.account_id),
        "strategy_id": row.strategy_id,
        "signal_id": str(row.signal_id) if row.signal_id else None,
        "symbol": row.symbol,
        "market": row.market.value,
        "side": row.side.value,
        "action": row.action.value,
        "price_type": row.price_type.value,
        "price": _decimal_str(row.price),
        "quantity": _decimal_str(row.quantity),
        "filled_quantity": _decimal_str(row.filled_quantity),
        "status": row.status.value,
        "submitted_at": to_utc_iso(row.submitted_at),
        "last_event_at": to_utc_iso(row.last_event_at),
        "fail_reason": row.fail_reason,
        "created_at": to_utc_iso(row.created_at),
        "updated_at": to_utc_iso(row.updated_at),
    }


class OrderService:
    def transition(self, order: Order, new_status: OrderStatus) -> None:
        allowed = VALID_TRANSITIONS.get(order.status, set())
        if new_status not in allowed and order.status != new_status:
            raise BizError(
                ErrorCode.ORDER_INVALID_TRANSITION,
                f"非法订单状态迁移: {order.status.value} -> {new_status.value}",
            )
        order.status = new_status
        order.last_event_at = datetime.now(timezone.utc)

    def create_from_signal(
        self,
        db: Session,
        signal_row: StrategySignal,
        place_req: PlaceOrderRequest,
        *,
        check_id: UUID,
        correlation_id: str = "",
    ) -> Order:
        account_repo = AccountRepository(db)
        account = account_repo.get_or_create_default(signal_row.market)

        now = datetime.now(timezone.utc)
        client_order_id = place_req.client_order_id or f"lh_{now:%Y%m%d}_{uuid4().hex[:8]}"

        risk_check = RiskRepository(db).get_check(check_id)
        if risk_check is None:
            raise BizError(ErrorCode.RISK_CHECK_REQUIRED, f"风控记录不存在: {check_id}", status=400)
        if risk_check.result != RiskResult.PASSED:
            raise BizError(
                ErrorCode.RISK_CHECK_NOT_PASSED,
                f"风控未通过，禁止建单: {risk_check.result.value}",
                status=400,
            )
        if risk_check.client_order_id and risk_check.client_order_id != client_order_id:
            raise BizError(
                ErrorCode.RISK_CHECK_MISMATCH,
                "风控记录与订单 client_order_id 不匹配",
                status=400,
            )

        order_repo = OrderRepository(db)
        existing = order_repo.get_by_client_order_id(client_order_id)
        if existing is not None:
            logger.warning("订单已存在，跳过重复创建: %s", client_order_id)
            return existing

        order = order_repo.create_order(
            client_order_id=client_order_id,
            account_id=account.id,
            strategy_id=signal_row.strategy_id,
            signal_id=signal_row.signal_id,
            symbol=signal_row.symbol,
            market=signal_row.market,
            side=signal_row.side,
            action=signal_row.action,
            price_type=signal_row.price_type,
            price=Decimal(str(signal_row.price)),
            quantity=Decimal(str(signal_row.quantity)),
            status=OrderStatus.PENDING_RISK,
            submitted_at=now,
        )
        # 风控已通过：PENDING_RISK → SUBMITTING，再交由 trade_service 下单
        self.transition(order, OrderStatus.SUBMITTING)

        audit = AuditService(db, correlation_id=correlation_id)
        audit.log(
            action="order_create",
            module="order",
            object_type="order",
            object_id=client_order_id,
            result="success",
            request_summary={
                "signal_id": str(signal_row.signal_id),
                "strategy_id": signal_row.strategy_id,
                "symbol": signal_row.symbol,
                "side": signal_row.side.value,
                "quantity": _decimal_str(signal_row.quantity),
            },
        )
        db.commit()

        from app.services.trade_service import trade_service

        trade_service.submit(order.id, correlation_id=correlation_id)
        return order

    def get(self, db: Session, client_order_id: str) -> Order | None:
        return OrderRepository(db).get_by_client_order_id(client_order_id)

    def list(
        self,
        db: Session,
        *,
        market=None,
        symbol: str | None = None,
        status=None,
        statuses: set[OrderStatus] | None = None,
        strategy_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Order], int]:
        return OrderRepository(db).list_orders(
            market=market,
            symbol=symbol,
            status=status,
            statuses=statuses,
            strategy_id=strategy_id,
            start=start,
            end=end,
            offset=offset,
            limit=limit,
        )

    def cancel(
        self,
        db: Session,
        client_order_id: str,
        *,
        reason: str = "user_cancel",
        correlation_id: str = "",
    ) -> Order:
        order = OrderRepository(db).get_by_client_order_id(client_order_id)
        if order is None:
            raise BizError(ErrorCode.ORDER_NOT_FOUND, f"订单不存在: {client_order_id}", status=404)
        if order.status not in CANCELLABLE:
            raise BizError(
                ErrorCode.ORDER_NOT_CANCELLABLE,
                f"当前状态不可撤单: {order.status.value}",
            )
        db.commit()

        from app.services.trade_service import trade_service

        return trade_service.cancel(client_order_id, reason, correlation_id=correlation_id)

    def confirm_unknown(
        self,
        db: Session,
        client_order_id: str,
        *,
        resolved_status: OrderStatus,
        reason: str = "",
        correlation_id: str = "",
    ) -> Order:
        from app.db.models.system_event import SystemEvent
        from app.repositories.system_event_repo import SystemEventRepository

        order = OrderRepository(db).get_by_client_order_id(client_order_id)
        if order is None:
            raise BizError(ErrorCode.ORDER_NOT_FOUND, f"订单不存在: {client_order_id}", status=404)
        if order.status != OrderStatus.UNKNOWN:
            raise BizError(
                ErrorCode.ORDER_NOT_UNKNOWN,
                f"仅 unknown 状态订单可人工确认，当前: {order.status.value}",
            )
        if resolved_status not in UNKNOWN_RESOLVABLE:
            raise BizError(
                ErrorCode.ORDER_INVALID_RESOLVED_STATUS,
                f"resolved_status 必须为 cancelled/filled/failed，收到: {resolved_status.value}",
            )

        self.transition(order, resolved_status)
        order.fail_reason = reason or f"人工确认 unknown → {resolved_status.value}"

        events = (
            db.query(SystemEvent)
            .filter(
                SystemEvent.event_code == "ORDER_UNKNOWN",
                SystemEvent.resolved.is_(False),
                SystemEvent.message.contains(client_order_id),
            )
            .all()
        )
        for ev in events:
            ev.resolved = True

        audit = AuditService(db, correlation_id=correlation_id)
        audit.log(
            action="order_confirm_unknown",
            module="order",
            object_type="order",
            object_id=client_order_id,
            result="success",
            reason=reason,
            request_summary={
                "resolved_status": resolved_status.value,
                "previous_status": "unknown",
            },
        )
        SystemEventRepository(db).add(
            module="order",
            event_code="ORDER_UNKNOWN_CONFIRMED",
            message=f"订单 {client_order_id} 已人工确认 → {resolved_status.value}",
            severity=Severity.INFO,
            resolved=True,
            payload={
                "client_order_id": client_order_id,
                "resolved_status": resolved_status.value,
                "reason": reason,
            },
        )
        db.flush()
        broadcast_sync("order.update", order_to_dict(order))
        return order

    def on_order_update(self, event: OrderUpdateEvent) -> None:
        db = db_session.SessionLocal()
        try:
            repo = OrderRepository(db)
            order = None
            if event.client_order_id:
                order = repo.get_by_client_order_id(event.client_order_id)
            if order is None and event.sdk_order_id:
                order = (
                    db.query(Order)
                    .filter(Order.sdk_order_id == event.sdk_order_id)
                    .first()
                )
            if order is None:
                logger.warning("订单更新未找到订单: %s / %s", event.client_order_id, event.sdk_order_id)
                return

            if event.sdk_order_id and not order.sdk_order_id:
                order.sdk_order_id = event.sdk_order_id

            filled = Decimal(str(event.filled_quantity))
            if filled > Decimal(str(order.filled_quantity)):
                order.filled_quantity = filled

            current = order.status
            target = event.status
            if current != target:
                try:
                    self.transition(order, target)
                except BizError:
                    logger.warning(
                        "订单状态迁移失败，标记 UNKNOWN: %s -> %s (%s)",
                        current.value,
                        target.value,
                        order.client_order_id,
                    )
                    try:
                        self.transition(order, OrderStatus.UNKNOWN)
                    except BizError:
                        logger.warning(
                            "无法标记 UNKNOWN，保持原状态: %s (%s)",
                            order.status.value,
                            order.client_order_id,
                        )

            order.last_event_at = event.event_time
            if event.raw_payload:
                order.raw_payload = event.raw_payload
            db.commit()

            broadcast_sync("order.update", order_to_dict(order))
        except Exception:
            logger.exception("处理订单更新失败")
            db.rollback()
        finally:
            db.close()


order_service = OrderService()
