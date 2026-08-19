"""TqSdkBroker：经独立运行时适配现有 Broker 接口。"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable
from uuid import UUID

from app.broker.base import Broker
from app.broker.errors import (
    BrokerCancelRejected,
    BrokerConfigurationError,
    BrokerNotReady,
    BrokerReconciliationError,
    BrokerSubmitRejected,
    BrokerSubmitOutcomeUnknown,
)
from app.broker.tqsdk_mapping import (
    as_decimal,
    client_order_id_to_tq_order_id,
    ensure_limit_only,
    filled_quantity,
    from_tq_symbol,
    map_offset,
    map_offset_flag_from_tq,
    map_order_status,
    map_side,
    map_side_from_tq,
    mask_account_id,
    normalize_exchange_id,
    remaining_quantity,
    to_tq_symbol,
)
from app.broker.tqsdk_runtime import TqSdkRuntime
from app.db import session as db_session
from app.schemas.enums import HedgeFlag, Market, OrderStatus
from app.sdk.models import (
    AccountSnapshot,
    CancelOrderRequest,
    CancelOrderResult,
    ConnectionEvent,
    OrderQuery,
    OrderSnapshot,
    OrderUpdateEvent,
    PlaceOrderRequest,
    PlaceOrderResult,
    PositionSnapshot,
    TradeQuery,
    TradeSnapshot,
    TradeUpdateEvent,
)

logger = logging.getLogger(__name__)


def _dec(value: Any) -> Decimal:
    return as_decimal(value)


class TqSdkBroker(Broker):
    """天勤 TqSdk 期货通道。FastAPI 线程不直接碰 TqApi。"""

    name = "tqsdk"
    market = Market.FUTURES

    def __init__(
        self,
        config: dict | None = None,
        *,
        runtime_factory: Callable[..., TqSdkRuntime] | None = None,
    ):
        super().__init__()
        self.config = dict(config or {})
        self._live_enabled = bool(self.config.get("live_enabled", False))
        self._live_armed = False
        self._live_arm_token = str(self.config.get("live_arm_token") or "")
        self._broker_id = str(self.config.get("broker_id") or "").strip()
        self._account_id = str(self.config.get("account_id") or "").strip()
        self._connected = False
        self._reconciled = False
        self._trading_day: str | None = None
        self._lock = threading.RLock()

        factory = runtime_factory or TqSdkRuntime
        self._runtime = factory(
            self.config,
            on_order_change=self._handle_order_change,
            on_trade_change=self._handle_trade_change,
            on_connection_change=self._handle_connection_change,
        )

    def connect(self) -> dict:
        if not self._broker_id or not self._account_id:
            raise BrokerConfigurationError(
                "TqSdk 缺少 TQSDK_BROKER_ID / TQSDK_ACCOUNT_ID"
            )
        health = self._runtime.start()
        self._connected = True
        # 启动后做一次只读查询，确认通道可用
        try:
            account = self.get_account()
            positions = self.get_positions()
            orders = self.query_orders()
            trades = self.query_trades()
            self._reconciled = True
            logger.info(
                "TqSdk 初始对账完成: account=%s positions=%s orders=%s trades=%s",
                mask_account_id(self._account_id),
                len(positions),
                len(orders),
                len(trades),
            )
            _ = account
        except Exception as exc:
            self._reconciled = False
            raise BrokerReconciliationError(f"TqSdk 初始对账失败: {exc}") from exc
        self._emit_connection(True, "connected")
        return {**health, **self.health()}

    def disconnect(self) -> None:
        try:
            self._runtime.stop()
        finally:
            self._connected = False
            self._reconciled = False
            self._live_armed = False
            self._emit_connection(False, "disconnected")

    def is_connected(self) -> bool:
        return self._connected and self._runtime.is_ready()

    def arm_live_trading(self, token: str) -> dict:
        """第二道实盘确认：live_enabled 之外再校验 arm token。"""
        if not self._live_enabled:
            raise BrokerConfigurationError("TQSDK_LIVE_ENABLED=false，无法 arm 实盘")
        expected = self._live_arm_token
        if not expected:
            raise BrokerConfigurationError("未配置 TQSDK_LIVE_ARM_TOKEN")
        if token != expected:
            raise BrokerConfigurationError("TqSdk live arm token 不正确")
        self._live_armed = True
        logger.warning(
            "TqSdk 实盘已 arm：account=%s broker_id=%s",
            mask_account_id(self._account_id),
            self._broker_id,
        )
        return {"armed": True, "live_enabled": True}

    def get_account(self) -> AccountSnapshot:
        self._ensure_ready_for_query()
        raw = self._runtime.call("get_account")
        balance = _dec(getattr(raw, "balance", None) or getattr(raw, "ctp_balance", None))
        available = _dec(
            getattr(raw, "available", None) or getattr(raw, "ctp_available", None)
        )
        frozen_margin = _dec(getattr(raw, "frozen_margin", 0))
        margin = _dec(getattr(raw, "margin", 0))
        commission = _dec(getattr(raw, "commission", 0))
        close_profit = _dec(getattr(raw, "close_profit", 0))
        position_profit = _dec(getattr(raw, "position_profit", 0))
        risk_ratio = getattr(raw, "risk_ratio", None)
        return AccountSnapshot(
            account_id=self._account_uuid(),
            account_no=mask_account_id(self._account_id) or self._account_id,
            total_asset=balance,
            available_cash=available,
            frozen_cash=frozen_margin,
            market_value=Decimal("0"),
            pnl=position_profit + close_profit,
            snapshot_time=datetime.now(timezone.utc),
            balance=balance,
            curr_margin=margin,
            frozen_margin=frozen_margin,
            commission=commission,
            close_profit=close_profit,
            position_profit=position_profit,
            risk_ratio=_dec(risk_ratio) if risk_ratio is not None else None,
            trading_day=self._trading_day,
            raw_payload=self._safe_raw(raw),
        )

    def get_positions(self) -> list[PositionSnapshot]:
        self._ensure_ready_for_query()
        entity = self._runtime.call("get_positions")
        out: list[PositionSnapshot] = []
        account_uuid = self._account_uuid()
        now = datetime.now(timezone.utc)
        for _key, pos in self._iter_entity(entity):
            exchange_id = normalize_exchange_id(getattr(pos, "exchange_id", "") or "")
            instrument = str(getattr(pos, "instrument_id", "") or "")
            if not instrument and _key:
                instrument, parsed_ex = from_tq_symbol(str(_key))
                exchange_id = exchange_id or parsed_ex
            symbol = instrument
            for direction, qty, today, yesterday, frozen_today, frozen_yesterday, avg, margin, pnl in (
                (
                    "long",
                    _dec(getattr(pos, "pos_long", 0)),
                    _dec(getattr(pos, "pos_long_today", 0)),
                    _dec(getattr(pos, "pos_long_his", 0)),
                    _dec(getattr(pos, "pos_long_today_frozen", getattr(pos, "long_today_frozen", 0))),
                    _dec(getattr(pos, "pos_long_his_frozen", getattr(pos, "long_his_frozen", 0))),
                    _dec(getattr(pos, "open_price_long", getattr(pos, "position_price_long", 0))),
                    _dec(getattr(pos, "margin_long", 0)),
                    _dec(getattr(pos, "position_profit_long", getattr(pos, "float_profit_long", 0))),
                ),
                (
                    "short",
                    _dec(getattr(pos, "pos_short", 0)),
                    _dec(getattr(pos, "pos_short_today", 0)),
                    _dec(getattr(pos, "pos_short_his", 0)),
                    _dec(getattr(pos, "pos_short_today_frozen", getattr(pos, "short_today_frozen", 0))),
                    _dec(getattr(pos, "pos_short_his_frozen", getattr(pos, "short_his_frozen", 0))),
                    _dec(getattr(pos, "open_price_short", getattr(pos, "position_price_short", 0))),
                    _dec(getattr(pos, "margin_short", 0)),
                    _dec(getattr(pos, "position_profit_short", getattr(pos, "float_profit_short", 0))),
                ),
            ):
                if qty <= 0:
                    continue
                frozen = frozen_today + frozen_yesterday
                out.append(
                    PositionSnapshot(
                        account_id=account_uuid,
                        symbol=symbol,
                        market=Market.FUTURES,
                        direction=direction,
                        quantity=qty,
                        available_quantity=max(Decimal("0"), qty - frozen),
                        avg_cost=avg,
                        market_value=Decimal("0"),
                        pnl=pnl,
                        snapshot_time=now,
                        exchange_id=exchange_id,
                        position_direction=direction,
                        quantity_today=today,
                        quantity_yesterday=yesterday,
                        frozen_quantity=frozen,
                        frozen_today=frozen_today,
                        frozen_yesterday=frozen_yesterday,
                        available_today=max(Decimal("0"), today - frozen_today),
                        available_yesterday=max(Decimal("0"), yesterday - frozen_yesterday),
                        margin=margin,
                        position_profit=pnl,
                        trading_day=self._trading_day,
                        raw_payload=self._safe_raw(pos),
                    )
                )
        return out

    def query_orders(self, request: OrderQuery | None = None) -> list[OrderSnapshot]:
        self._ensure_ready_for_query()
        entity = self._runtime.call("get_orders")
        out: list[OrderSnapshot] = []
        for order_id, order in self._iter_entity(entity):
            snap = self._order_to_snapshot(order, order_id=order_id)
            if request is not None:
                if request.client_order_id and snap.client_order_id != request.client_order_id:
                    continue
                if request.sdk_order_id and snap.sdk_order_id != request.sdk_order_id:
                    continue
                if request.symbol and snap.symbol != request.symbol:
                    continue
                if request.status and str(snap.status) != str(request.status):
                    continue
            out.append(snap)
        return out

    def query_trades(self, request: TradeQuery | None = None) -> list[TradeSnapshot]:
        self._ensure_ready_for_query()
        entity = self._runtime.call("get_trades")
        out: list[TradeSnapshot] = []
        for trade_id, trade in self._iter_entity(entity):
            snap = self._trade_to_snapshot(trade, trade_id=trade_id)
            if request is not None:
                if getattr(request, "client_order_id", None) and snap.client_order_id != request.client_order_id:
                    continue
                if getattr(request, "sdk_order_id", None) and snap.sdk_order_id != request.sdk_order_id:
                    continue
                if getattr(request, "symbol", None) and snap.symbol != request.symbol:
                    continue
            out.append(snap)
        return out

    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        self._ensure_ready_for_query()
        self._ensure_live_for_place()

        try:
            ensure_limit_only(request.price_type)
        except ValueError as exc:
            raise BrokerSubmitRejected(str(exc)) from exc
        if request.price is None:
            raise BrokerSubmitRejected("限价单缺少价格")

        qty_dec = Decimal(str(request.quantity))
        if qty_dec != qty_dec.to_integral_value() or qty_dec <= 0:
            raise BrokerSubmitRejected(f"手数必须为正整数，收到 {request.quantity}")
        volume = int(qty_dec)

        hedge = request.hedge_flag
        hedge_value = (
            hedge.value if isinstance(hedge, HedgeFlag) else str(hedge or HedgeFlag.SPECULATION.value)
        ).lower()
        if hedge_value and hedge_value != HedgeFlag.SPECULATION.value:
            raise BrokerSubmitRejected("TqSdkBroker 首版仅支持投机单，不支持套保/套利静默降级")

        exchange_id = normalize_exchange_id(request.exchange_id)
        try:
            tq_symbol = to_tq_symbol(request.symbol, exchange_id)
            direction = map_side(request.side)
            offset = map_offset(request.offset_flag, exchange_id or tq_symbol.split(".", 1)[0])
            order_id = client_order_id_to_tq_order_id(request.client_order_id)
        except ValueError as exc:
            raise BrokerSubmitRejected(str(exc)) from exc

        logger.info(
            "TqSdk 报单: client=%s symbol=%s side=%s offset=%s qty=%s",
            request.client_order_id,
            tq_symbol,
            direction,
            offset,
            volume,
        )
        try:
            order = self._runtime.call(
                "insert_order",
                symbol=tq_symbol,
                direction=direction,
                offset=offset,
                volume=volume,
                limit_price=float(request.price),
                order_id=order_id,
            )
        except BrokerSubmitOutcomeUnknown:
            raise
        except Exception as exc:
            raise BrokerSubmitOutcomeUnknown(f"TqSdk 报单结果未知: {exc}") from exc

        status = map_order_status(order)
        sdk_order_id = str(getattr(order, "order_id", "") or order_id)
        success = status not in {OrderStatus.FAILED, OrderStatus.UNKNOWN}
        return PlaceOrderResult(
            success=success,
            client_order_id=request.client_order_id,
            sdk_order_id=sdk_order_id,
            status=status,
            message="TqSdk 委托已受理" if success else str(getattr(order, "last_msg", "") or "委托失败"),
            raw_payload=self._safe_raw(order),
        )

    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult:
        """关闭实盘开关后仍允许撤单；仅禁止新开仓/普通下单。"""
        self._ensure_ready_for_query()
        order_id = (request.sdk_order_id or "").strip()
        if not order_id and request.client_order_id:
            try:
                order_id = client_order_id_to_tq_order_id(request.client_order_id)
            except ValueError as exc:
                raise BrokerCancelRejected(str(exc)) from exc
        if not order_id:
            raise BrokerCancelRejected("撤单缺少 sdk_order_id / client_order_id")

        try:
            order = self._runtime.call("cancel_order", order_id=order_id)
        except BrokerSubmitOutcomeUnknown:
            raise
        except Exception as exc:
            raise BrokerSubmitOutcomeUnknown(f"TqSdk 撤单结果未知: {exc}") from exc

        status = map_order_status(order)
        return CancelOrderResult(
            success=status in {OrderStatus.CANCELLED, OrderStatus.FILLED},
            client_order_id=request.client_order_id,
            sdk_order_id=str(getattr(order, "order_id", "") or order_id),
            status=status,
            message="TqSdk 撤单已确认" if status == OrderStatus.CANCELLED else f"撤单后状态={status.value}",
            raw_payload=self._safe_raw(order),
        )

    def health(self) -> dict:
        runtime_health = {}
        try:
            runtime_health = self._runtime.health()
        except Exception:
            runtime_health = {}
        return {
            "broker": self.name,
            "connected": self.is_connected(),
            "reconciled": self._reconciled,
            "trader_state": "ready" if self.is_connected() and self._reconciled else self._runtime.state,
            "trading_day": self._trading_day,
            "live_enabled": self._live_enabled,
            "live_armed": self._live_armed,
            "broker_id": self._broker_id,
            "account_masked": mask_account_id(self._account_id),
            **runtime_health,
        }

    def _ensure_ready_for_query(self) -> None:
        if not self.is_connected():
            raise BrokerNotReady(f"TqSdk 通道未就绪: state={self._runtime.state}")

    def _ensure_live_for_place(self) -> None:
        if not self._live_enabled:
            raise BrokerConfigurationError(
                "TQSDK_LIVE_ENABLED=false，禁止新开仓/普通下单（仍允许撤单与查询）"
            )
        if not self._live_armed:
            raise BrokerConfigurationError(
                "TqSdk 实盘未 arm：请先调用 arm_live_trading() 完成第二道确认"
            )

    def _order_to_snapshot(self, order: Any, *, order_id: str = "") -> OrderSnapshot:
        sdk_order_id = str(getattr(order, "order_id", "") or order_id)
        instrument = str(getattr(order, "instrument_id", "") or "")
        exchange_id = normalize_exchange_id(getattr(order, "exchange_id", "") or "")
        if not instrument:
            instrument, parsed = from_tq_symbol(str(getattr(order, "symbol", "") or ""))
            exchange_id = exchange_id or parsed
        return OrderSnapshot(
            client_order_id=sdk_order_id or None,
            sdk_order_id=sdk_order_id or None,
            status=map_order_status(order),
            filled_quantity=filled_quantity(order),
            remaining_quantity=remaining_quantity(order),
            symbol=instrument or None,
            market=Market.FUTURES,
            exchange_id=exchange_id,
            offset_flag=map_offset_flag_from_tq(getattr(order, "offset", None)),
            hedge_flag=HedgeFlag.SPECULATION,
            trading_day=self._trading_day,
            order_sys_id=str(getattr(order, "exchange_order_id", "") or "") or None,
            raw_payload=self._safe_raw(order),
        )

    def _trade_to_snapshot(self, trade: Any, *, trade_id: str = "") -> TradeSnapshot:
        sdk_trade_id = str(getattr(trade, "trade_id", "") or trade_id)
        sdk_order_id = str(getattr(trade, "order_id", "") or "") or None
        instrument = str(getattr(trade, "instrument_id", "") or "")
        exchange_id = normalize_exchange_id(getattr(trade, "exchange_id", "") or "")
        side = map_side_from_tq(getattr(trade, "direction", None))
        trade_time = self._ns_to_dt(getattr(trade, "trade_date_time", None))
        raw = self._safe_raw(trade)
        if raw is not None:
            raw.setdefault("broker_type", "tqsdk")
            raw.setdefault("exchange_trade_id", getattr(trade, "exchange_trade_id", None))
        return TradeSnapshot(
            sdk_trade_id=sdk_trade_id,
            client_order_id=sdk_order_id,
            sdk_order_id=sdk_order_id,
            symbol=instrument,
            market=Market.FUTURES,
            side=side,
            price=_dec(getattr(trade, "price", 0)),
            quantity=_dec(getattr(trade, "volume", 0)),
            fee=Decimal("0"),
            trade_time=trade_time,
            exchange_id=exchange_id,
            trading_day=self._trading_day,
            raw_payload=raw,
        )

    def _handle_order_change(self, order: Any) -> None:
        if not self._on_order_update:
            return
        snap = self._order_to_snapshot(order)
        event = OrderUpdateEvent(
            client_order_id=snap.client_order_id,
            sdk_order_id=snap.sdk_order_id,
            status=snap.status if isinstance(snap.status, OrderStatus) else OrderStatus(str(snap.status)),
            filled_quantity=snap.filled_quantity,
            remaining_quantity=snap.remaining_quantity,
            event_time=datetime.now(timezone.utc),
            exchange_id=snap.exchange_id,
            offset_flag=snap.offset_flag,
            hedge_flag=snap.hedge_flag,
            trading_day=snap.trading_day,
            broker_type=self.name,
            raw_payload=snap.raw_payload,
        )
        try:
            self._on_order_update(event)
        except Exception:
            logger.exception("TqSdk 订单更新回调失败")

    def _handle_trade_change(self, trade: Any) -> None:
        if not self._on_trade_update:
            return
        snap = self._trade_to_snapshot(trade)
        side = snap.side
        if side is None:
            return
        from app.schemas.enums import OrderSide

        if not isinstance(side, OrderSide):
            try:
                side = OrderSide(str(side))
            except ValueError:
                return
        event = TradeUpdateEvent(
            sdk_trade_id=snap.sdk_trade_id,
            client_order_id=snap.client_order_id,
            sdk_order_id=snap.sdk_order_id,
            symbol=snap.symbol,
            market=Market.FUTURES,
            side=side,
            price=snap.price,
            quantity=snap.quantity,
            fee=snap.fee,
            trade_time=snap.trade_time or datetime.now(timezone.utc),
            exchange_id=snap.exchange_id,
            trading_day=snap.trading_day,
            broker_type=self.name,
            raw_payload=snap.raw_payload,
        )
        try:
            self._on_trade_update(event)
        except Exception:
            logger.exception("TqSdk 成交更新回调失败")

    def _handle_connection_change(self, connected: bool, reason: str) -> None:
        self._connected = bool(connected) and self._runtime.is_ready()
        if not connected:
            self._reconciled = False
        self._emit_connection(connected, reason)

    def _emit_connection(self, connected: bool, reason: str) -> None:
        if not self._on_connection_change:
            return
        try:
            self._on_connection_change(
                ConnectionEvent(
                    market=Market.FUTURES,
                    connected=connected,
                    reason=reason,
                    event_time=datetime.now(timezone.utc),
                )
            )
        except Exception:
            logger.exception("TqSdk 连接状态回调失败")

    def _account_uuid(self) -> UUID:
        from app.repositories.account_repo import AccountRepository

        db = db_session.SessionLocal()
        try:
            account = AccountRepository(db).get_or_create_default(Market.FUTURES)
            return account.id
        finally:
            db.close()

    @staticmethod
    def _iter_entity(entity: Any) -> list[tuple[str, Any]]:
        if entity is None:
            return []
        if isinstance(entity, dict):
            return [(str(k), v) for k, v in entity.items()]
        try:
            return [(str(k), v) for k, v in entity.items()]
        except Exception:
            order_id = getattr(entity, "order_id", None)
            trade_id = getattr(entity, "trade_id", None)
            instrument = getattr(entity, "instrument_id", None)
            if trade_id is not None:
                return [(str(trade_id), entity)]
            if order_id is not None:
                return [(str(order_id), entity)]
            if instrument is not None:
                return [(str(instrument), entity)]
            return [("0", entity)]

    @staticmethod
    def _safe_raw(obj: Any) -> dict | None:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return dict(obj)
        out: dict[str, Any] = {}
        for key in (
            "order_id",
            "trade_id",
            "exchange_order_id",
            "exchange_trade_id",
            "exchange_id",
            "instrument_id",
            "direction",
            "offset",
            "volume_orign",
            "volume_left",
            "volume",
            "limit_price",
            "price",
            "status",
            "is_error",
            "is_dead",
            "last_msg",
            "balance",
            "available",
            "margin",
            "frozen_margin",
            "commission",
            "close_profit",
            "position_profit",
            "risk_ratio",
            "pos_long",
            "pos_short",
            "pos_long_today",
            "pos_long_his",
            "pos_short_today",
            "pos_short_his",
        ):
            if hasattr(obj, key):
                value = getattr(obj, key)
                if isinstance(value, (str, int, float, bool)) or value is None:
                    out[key] = value
                else:
                    try:
                        out[key] = float(value)
                    except Exception:
                        out[key] = str(value)
        return out or None

    @staticmethod
    def _ns_to_dt(value: Any) -> datetime | None:
        try:
            ns = int(value)
        except Exception:
            return None
        if ns <= 0:
            return None
        return datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc)
