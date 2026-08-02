import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.api.ws_hub import broadcast_sync
from app.core.time import to_utc_iso
from app.db.models.order import Order
from app.db import session as db_session
from app.repositories.order_repo import OrderRepository
from app.repositories.risk_repo import RiskRepository
from app.repositories.trade_repo import TradeRepository
from app.schemas.enums import OrderStatus
from app.schemas.error_codes import ErrorCode
from app.broker import manager as broker_manager
from app.sdk.base import AdapterError
from app.sdk.models import CancelOrderRequest, PlaceOrderRequest, TradeUpdateEvent
from app.services.audit_service import AuditService
from app.services.order_service import order_service, order_to_dict
from app.services import runtime_metrics

logger = logging.getLogger(__name__)


def _decimal_str(value: Decimal | float | None) -> str:
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return str(value)
    return str(Decimal(str(value)))


def trade_to_dict(row) -> dict:
    return {
        "id": str(row.id),
        "sdk_trade_id": row.sdk_trade_id,
        "client_order_id": row.client_order_id,
        "sdk_order_id": row.sdk_order_id,
        "account_id": str(row.account_id),
        "strategy_id": row.strategy_id,
        "symbol": row.symbol,
        "market": row.market.value,
        "side": row.side.value,
        "price": _decimal_str(row.price),
        "quantity": _decimal_str(row.quantity),
        "fee": _decimal_str(row.fee),
        "trade_time": to_utc_iso(row.trade_time),
        "created_at": to_utc_iso(row.created_at),
    }


class TradeService:
    def submit(self, order_id: UUID, *, correlation_id: str = "") -> Order:
        db = db_session.SessionLocal()
        try:
            repo = OrderRepository(db)
            order = repo.get_by_id(order_id)
            if order is None:
                raise BizError(ErrorCode.ORDER_NOT_FOUND, f"订单不存在: {order_id}", status=404)
            if order.status != OrderStatus.SUBMITTING:
                logger.warning("订单非 submitting 状态，跳过提交: %s %s", order.client_order_id, order.status.value)
                db.commit()
                return order

            # 强制关口：必须有对应 passed 的 risk_checks，防止绕过风控直达 SDK
            passed_check = RiskRepository(db).get_passed_by_client_order_id(order.client_order_id)
            if passed_check is None:
                order.fail_reason = "缺少通过的风控记录，禁止提交"
                order_service.transition(order, OrderStatus.FAILED)
                runtime_metrics.record_order_submit_result(False)
                AuditService(db, correlation_id=correlation_id).log(
                    action="order_submit",
                    module="trade",
                    object_type="order",
                    object_id=order.client_order_id,
                    result="rejected",
                    reason=order.fail_reason,
                )
                db.commit()
                broadcast_sync("order.update", order_to_dict(order), correlation_id=correlation_id)
                logger.warning("订单缺少 passed 风控记录，拒绝提交: %s", order.client_order_id)
                return order

            place_req = PlaceOrderRequest(
                client_order_id=order.client_order_id,
                account_id=order.account_id,
                market=order.market,
                symbol=order.symbol,
                side=order.side,
                action=order.action,
                price_type=order.price_type,
                price=Decimal(str(order.price)) if order.price else None,
                quantity=Decimal(str(order.quantity)),
                metadata={
                    "strategy_id": order.strategy_id or "",
                    "signal_id": str(order.signal_id or ""),
                    "check_id": str(passed_check.check_id),
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        broker = broker_manager.get_broker(place_req.market)
        result = None
        error_msg = ""
        try:
            result = broker.place_order(place_req)
        except AdapterError as exc:
            error_msg = exc.message
            logger.warning("SDK 下单失败: %s %s", place_req.client_order_id, error_msg)
        except Exception as exc:
            error_msg = str(exc)
            logger.exception("SDK 下单异常: %s", place_req.client_order_id)

        db = db_session.SessionLocal()
        try:
            repo = OrderRepository(db)
            order = repo.get_by_client_order_id(place_req.client_order_id)
            if order is None:
                raise BizError(ErrorCode.ORDER_NOT_FOUND, f"订单不存在: {place_req.client_order_id}", status=404)

            audit = AuditService(db, correlation_id=correlation_id)
            now = datetime.now(timezone.utc)

            if result and result.success:
                order.sdk_order_id = result.sdk_order_id
                order_service.transition(order, OrderStatus.SUBMITTED)
                order.submitted_at = now
                if result.raw_payload:
                    order.raw_payload = result.raw_payload
                runtime_metrics.record_order_submit_result(True)
                audit.log(
                    action="order_submit",
                    module="trade",
                    object_type="order",
                    object_id=order.client_order_id,
                    result="success",
                    request_summary={"sdk_order_id": result.sdk_order_id},
                )
            else:
                order.fail_reason = error_msg or (result.message if result else "unknown error")
                order_service.transition(order, OrderStatus.FAILED)
                runtime_metrics.record_order_submit_result(False)
                audit.log(
                    action="order_submit",
                    module="trade",
                    object_type="order",
                    object_id=order.client_order_id,
                    result="failed",
                    reason=order.fail_reason,
                )

            db.commit()
            broadcast_sync("order.update", order_to_dict(order), correlation_id=correlation_id)
            return order
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def cancel(
        self,
        client_order_id: str,
        reason: str = "user_cancel",
        *,
        correlation_id: str = "",
    ) -> Order:
        db = db_session.SessionLocal()
        try:
            repo = OrderRepository(db)
            order = repo.get_by_client_order_id(client_order_id)
            if order is None:
                raise BizError(ErrorCode.ORDER_NOT_FOUND, f"订单不存在: {client_order_id}", status=404)

            cancel_req = CancelOrderRequest(
                client_order_id=client_order_id,
                sdk_order_id=order.sdk_order_id,
                market=order.market,
                reason=reason,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        broker = broker_manager.get_broker(cancel_req.market)
        result = None
        error_msg = ""
        try:
            result = broker.cancel_order(cancel_req)
        except AdapterError as exc:
            error_msg = exc.message
            logger.warning("SDK 撤单失败: %s %s", client_order_id, error_msg)
        except Exception as exc:
            error_msg = str(exc)
            logger.exception("SDK 撤单异常: %s", client_order_id)

        db = db_session.SessionLocal()
        try:
            repo = OrderRepository(db)
            order = repo.get_by_client_order_id(client_order_id)
            if order is None:
                raise BizError(ErrorCode.ORDER_NOT_FOUND, f"订单不存在: {client_order_id}", status=404)

            audit = AuditService(db, correlation_id=correlation_id)
            if result and result.success:
                order_service.transition(order, OrderStatus.CANCELLED)
                audit.log(
                    action="order_cancel",
                    module="trade",
                    object_type="order",
                    object_id=client_order_id,
                    result="success",
                    reason=reason,
                )
            else:
                audit.log(
                    action="order_cancel",
                    module="trade",
                    object_type="order",
                    object_id=client_order_id,
                    result="failed",
                    reason=error_msg or "cancel failed",
                )
                raise BizError(ErrorCode.ORDER_CANCEL_FAILED, error_msg or "撤单失败")

            db.commit()
            broadcast_sync("order.update", order_to_dict(order), correlation_id=correlation_id)
            return order
        except BizError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def on_trade_update(self, event: TradeUpdateEvent) -> None:
        db = db_session.SessionLocal()
        try:
            trade_repo = TradeRepository(db)
            existing = trade_repo.get_by_sdk_trade_id(event.market, event.sdk_trade_id)
            if existing is not None:
                logger.debug("成交已存在，跳过: %s", event.sdk_trade_id)
                return

            order_repo = OrderRepository(db)
            order = None
            if event.client_order_id:
                order = order_repo.get_by_client_order_id(event.client_order_id)
            if order is None and event.sdk_order_id:
                order = (
                    db.query(Order)
                    .filter(Order.sdk_order_id == event.sdk_order_id)
                    .first()
                )
            if order is None:
                logger.warning("成交回报未找到订单: %s / %s", event.client_order_id, event.sdk_order_id)
                return

            trade = trade_repo.create_trade(
                sdk_trade_id=event.sdk_trade_id,
                client_order_id=order.client_order_id,
                sdk_order_id=event.sdk_order_id or order.sdk_order_id,
                account_id=order.account_id,
                strategy_id=order.strategy_id,
                symbol=event.symbol,
                market=event.market,
                side=event.side,
                price=Decimal(str(event.price)),
                quantity=Decimal(str(event.quantity)),
                fee=Decimal(str(event.fee)),
                trade_time=event.trade_time,
                raw_payload=event.raw_payload,
            )

            # 以成交汇总为权威值，避免轮询与回调双通道重复累加
            new_filled = trade_repo.sum_quantity_by_client_order_id(order.client_order_id)
            order.filled_quantity = new_filled
            order.last_event_at = event.trade_time

            qty = Decimal(str(order.quantity))
            if new_filled >= qty:
                if order.status != OrderStatus.FILLED:
                    try:
                        order_service.transition(order, OrderStatus.FILLED)
                    except BizError:
                        logger.warning(
                            "成交后迁移至 FILLED 失败，标记 UNKNOWN: %s (%s)",
                            order.status.value,
                            order.client_order_id,
                        )
                        try:
                            order_service.transition(order, OrderStatus.UNKNOWN)
                        except BizError:
                            logger.warning(
                                "无法标记 UNKNOWN，保持原状态: %s (%s)",
                                order.status.value,
                                order.client_order_id,
                            )
            elif new_filled > Decimal("0") and order.status == OrderStatus.SUBMITTED:
                try:
                    order_service.transition(order, OrderStatus.PARTIALLY_FILLED)
                except BizError:
                    logger.warning(
                        "成交后迁移至 PARTIALLY_FILLED 失败，标记 UNKNOWN: %s (%s)",
                        order.status.value,
                        order.client_order_id,
                    )
                    try:
                        order_service.transition(order, OrderStatus.UNKNOWN)
                    except BizError:
                        logger.warning(
                            "无法标记 UNKNOWN，保持原状态: %s (%s)",
                            order.status.value,
                            order.client_order_id,
                        )

            db.commit()
            broadcast_sync("trade.update", trade_to_dict(trade))
            broadcast_sync("order.update", order_to_dict(order))
        except Exception:
            logger.exception("处理成交回报失败")
            db.rollback()
        finally:
            db.close()


trade_service = TradeService()
