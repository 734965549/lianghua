import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.api.ws_hub import broadcast_sync
from app.db.models.order import Order
from app.db.session import SessionLocal
from app.repositories.order_repo import OrderRepository
from app.repositories.trade_repo import TradeRepository
from app.schemas.enums import OrderStatus
from app.sdk import manager as sdk_manager
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
        "trade_time": row.trade_time.isoformat(),
        "created_at": row.created_at.isoformat(),
    }


class TradeService:
    def submit(self, order_id: UUID, *, correlation_id: str = "") -> Order:
        db = SessionLocal()
        try:
            repo = OrderRepository(db)
            order = repo.get_by_id(order_id)
            if order is None:
                raise BizError("ORDER_NOT_FOUND", f"订单不存在: {order_id}", status=404)
            if order.status != OrderStatus.SUBMITTING:
                logger.warning("订单非 submitting 状态，跳过提交: %s %s", order.client_order_id, order.status.value)
                db.commit()
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
                metadata={"strategy_id": order.strategy_id or "", "signal_id": str(order.signal_id or "")},
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        adapter = sdk_manager.get_adapter_for_market(place_req.market)
        result = None
        error_msg = ""
        try:
            result = adapter.place_order(place_req)
        except AdapterError as exc:
            error_msg = exc.message
            logger.warning("SDK 下单失败: %s %s", place_req.client_order_id, error_msg)
        except Exception as exc:
            error_msg = str(exc)
            logger.exception("SDK 下单异常: %s", place_req.client_order_id)

        db = SessionLocal()
        try:
            repo = OrderRepository(db)
            order = repo.get_by_client_order_id(place_req.client_order_id)
            if order is None:
                raise BizError("ORDER_NOT_FOUND", f"订单不存在: {place_req.client_order_id}", status=404)

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
        db = SessionLocal()
        try:
            repo = OrderRepository(db)
            order = repo.get_by_client_order_id(client_order_id)
            if order is None:
                raise BizError("ORDER_NOT_FOUND", f"订单不存在: {client_order_id}", status=404)

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

        adapter = sdk_manager.get_adapter_for_market(cancel_req.market)
        result = None
        error_msg = ""
        try:
            result = adapter.cancel_order(cancel_req)
        except AdapterError as exc:
            error_msg = exc.message
            logger.warning("SDK 撤单失败: %s %s", client_order_id, error_msg)
        except Exception as exc:
            error_msg = str(exc)
            logger.exception("SDK 撤单异常: %s", client_order_id)

        db = SessionLocal()
        try:
            repo = OrderRepository(db)
            order = repo.get_by_client_order_id(client_order_id)
            if order is None:
                raise BizError("ORDER_NOT_FOUND", f"订单不存在: {client_order_id}", status=404)

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
                raise BizError("ORDER_CANCEL_FAILED", error_msg or "撤单失败")

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
        db = SessionLocal()
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

            new_filled = Decimal(str(order.filled_quantity)) + Decimal(str(event.quantity))
            order.filled_quantity = new_filled
            order.last_event_at = event.trade_time

            qty = Decimal(str(order.quantity))
            if new_filled >= qty:
                if order.status != OrderStatus.FILLED:
                    try:
                        order_service.transition(order, OrderStatus.FILLED)
                    except BizError:
                        order.status = OrderStatus.FILLED
                        order.last_event_at = event.trade_time
            elif new_filled > Decimal("0") and order.status == OrderStatus.SUBMITTED:
                try:
                    order_service.transition(order, OrderStatus.PARTIALLY_FILLED)
                except BizError:
                    order.status = OrderStatus.PARTIALLY_FILLED
                    order.last_event_at = event.trade_time

            db.commit()
            broadcast_sync("trade.update", trade_to_dict(trade))
            broadcast_sync("order.update", order_to_dict(order))
        except Exception:
            logger.exception("处理成交回报失败")
            db.rollback()
        finally:
            db.close()


trade_service = TradeService()
