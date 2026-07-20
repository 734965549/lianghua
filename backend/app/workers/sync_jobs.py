import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.api.ws_hub import broadcast_sync
from app.db.models.system_event import SystemEvent
from app.db.models.system_state import SystemState
from app.repositories.account_repo import AccountRepository
from app.repositories.asset_repo import AssetRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.position_repo import PositionRepository
from app.repositories.system_event_repo import SystemEventRepository
from app.schemas.enums import Market, OrderStatus, Severity, SystemStatus
from app.sdk import manager as sdk_manager
from app.sdk.models import PositionSnapshot
from app.services.market_service import STALE_THRESHOLD_SECONDS, market_service
from app.services.system_service import SystemStateService

logger = logging.getLogger(__name__)


def _has_unresolved_quote_stale(db: Session) -> bool:
    return (
        db.query(SystemEvent)
        .filter(
            SystemEvent.event_code == "quote_stale",
            SystemEvent.resolved.is_(False),
        )
        .first()
        is not None
    )


def check_quote_stale(db: Session) -> None:
    """检查已订阅标的行情是否停更，必要时写事件并降级系统状态。"""
    if not market_service.started:
        return

    subscribed = market_service.get_subscribed()
    if not subscribed:
        return

    from app.repositories.market_repo import MarketRepository

    repo = MarketRepository(db)
    now = datetime.now(timezone.utc)
    stale_items: list[dict] = []

    for market, symbol in subscribed:
        row = repo.get_latest_quote(market, symbol)
        if row is None:
            stale_items.append({"market": market.value, "symbol": symbol, "reason": "no_quote"})
            continue
        age = (now - row.quote_time).total_seconds()
        if age > STALE_THRESHOLD_SECONDS:
            stale_items.append(
                {
                    "market": market.value,
                    "symbol": symbol,
                    "quote_time": row.quote_time.isoformat(),
                    "age_seconds": age,
                }
            )

    if not stale_items:
        return

    state_row = db.get(SystemState, SystemStateService.SINGLETON_ID)
    current_status = state_row.status if state_row else SystemStatus.READY

    if current_status == SystemStatus.DEGRADED:
        return

    if _has_unresolved_quote_stale(db):
        return

    events = SystemEventRepository(db)
    events.add(
        module="market",
        event_code="quote_stale",
        message=f"行情停更：{len(stale_items)} 个标的超过 {STALE_THRESHOLD_SECONDS}s 未更新",
        severity=Severity.WARNING,
        payload={"stale_items": stale_items},
    )

    if current_status in {SystemStatus.READY, SystemStatus.TRADING}:
        svc = SystemStateService(db, correlation_id="quote_stale_check")
        svc.transition(SystemStatus.DEGRADED, reason="行情停更")
        logger.warning("系统已降级：行情停更 %s", stale_items)

    db.commit()


def sync_positions(db: Session) -> None:
    """同步各市场持仓快照。"""
    if not market_service.started:
        return
    account_repo = AccountRepository(db)
    position_repo = PositionRepository(db)
    for market in (Market.STOCK, Market.FUTURES):
        try:
            account = account_repo.get_or_create_default(market)
            adapter = sdk_manager.get_adapter_for_market(market)
            positions = adapter.get_positions()
            now = datetime.now(timezone.utc)
            if not positions:
                continue
            for pos in positions:
                snap = pos if isinstance(pos, PositionSnapshot) else pos
                if snap.account_id != account.id:
                    snap = PositionSnapshot(
                        account_id=account.id,
                        symbol=snap.symbol,
                        market=snap.market,
                        direction=snap.direction,
                        quantity=snap.quantity,
                        available_quantity=snap.available_quantity,
                        avg_cost=snap.avg_cost,
                        market_value=snap.market_value,
                        pnl=snap.pnl,
                        snapshot_time=snap.snapshot_time or now,
                        raw_payload=snap.raw_payload,
                    )
                position_repo.insert_snapshot(snap)
        except Exception:
            logger.exception("sync_positions 失败: %s", market.value)
    db.commit()


def sync_assets(db: Session) -> None:
    """同步各市场账户资金快照。"""
    if not market_service.started:
        return
    account_repo = AccountRepository(db)
    asset_repo = AssetRepository(db)
    for market in (Market.STOCK, Market.FUTURES):
        try:
            account = account_repo.get_or_create_default(market)
            adapter = sdk_manager.get_adapter_for_market(market)
            snap = adapter.get_account()
            asset_repo.insert_snapshot(account.id, snap)
        except Exception:
            logger.exception("sync_assets 失败: %s", market.value)
    db.commit()


KNOWN_ORDER_STATUSES = {s.value for s in OrderStatus}


def _parse_sdk_order_status(raw) -> OrderStatus | None:
    """将 SDK 返回状态映射为本地枚举；无法映射返回 None（调用方置 unknown）。"""
    if raw is None:
        return None
    if isinstance(raw, OrderStatus):
        return raw
    value = str(raw).strip().lower()
    if value in KNOWN_ORDER_STATUSES:
        return OrderStatus(value)
    # 兼容常见别名
    aliases = {
        "partial": OrderStatus.PARTIALLY_FILLED,
        "partial_filled": OrderStatus.PARTIALLY_FILLED,
        "canceled": OrderStatus.CANCELLED,
        "reject": OrderStatus.FAILED,
        "rejected": OrderStatus.FAILED,
        "new": OrderStatus.SUBMITTED,
        "live": OrderStatus.SUBMITTED,
    }
    return aliases.get(value)


def _mark_order_unknown(db: Session, order, *, raw_status, reason: str) -> None:
    from app.services.order_service import order_service, order_to_dict

    if order.status != OrderStatus.UNKNOWN:
        try:
            order_service.transition(order, OrderStatus.UNKNOWN)
        except Exception:
            order.status = OrderStatus.UNKNOWN
            order.last_event_at = datetime.now(timezone.utc)
    order.fail_reason = reason
    payload = dict(order.raw_payload or {})
    payload["unknown_sdk_status"] = str(raw_status)
    order.raw_payload = payload

    events = SystemEventRepository(db)
    existing = (
        db.query(SystemEvent)
        .filter(
            SystemEvent.event_code == "ORDER_UNKNOWN",
            SystemEvent.resolved.is_(False),
            SystemEvent.message.contains(order.client_order_id),
        )
        .first()
    )
    if existing is None:
        events.add(
            module="order",
            event_code="ORDER_UNKNOWN",
            message=f"订单 {order.client_order_id} 状态未知，需人工处理",
            severity=Severity.CRITICAL,
            payload={
                "client_order_id": order.client_order_id,
                "sdk_order_id": order.sdk_order_id,
                "raw_status": str(raw_status),
                "reason": reason,
            },
        )
    broadcast_sync(
        "order.update",
        {**order_to_dict(order), "alert": "unknown"},
    )
    broadcast_sync(
        "risk.event",
        {
            "event": "order_unknown",
            "client_order_id": order.client_order_id,
            "reason": reason,
        },
    )


def sync_orders_trades(db: Session) -> None:
    """同步未完结订单：轮询 SDK，无法映射的状态置 unknown。"""
    from app.services import runtime_metrics
    from app.services.order_service import order_service, order_to_dict

    if not market_service.started:
        return

    repo = OrderRepository(db)
    queued = set(runtime_metrics.list_sync_queue())
    open_orders = repo.list_open_orders(limit=100)
    # 优先同步队列中的订单，并并入当前未完结
    by_id = {o.client_order_id: o for o in open_orders}
    for cid in list(queued):
        if cid not in by_id:
            row = repo.get_by_client_order_id(cid)
            if row is not None:
                by_id[cid] = row

    if not by_id:
        return

    # 按市场批量查询 SDK
    sdk_maps: dict[Market, dict[str, dict]] = {}
    for market in (Market.STOCK, Market.FUTURES):
        try:
            adapter = sdk_manager.get_adapter_for_market(market)
            rows = adapter.query_orders({})
            mapping: dict[str, dict] = {}
            for item in rows:
                cid = item.get("client_order_id")
                if cid:
                    mapping[str(cid)] = item
            sdk_maps[market] = mapping
        except Exception:
            logger.exception("query_orders 失败: %s", market.value)
            sdk_maps[market] = {}

    changed = False
    for client_order_id, order in by_id.items():
        sdk_row = sdk_maps.get(order.market, {}).get(client_order_id)
        if sdk_row is None:
            # 仍在 submitting 且尚无 SDK 映射：保留，等待回调
            continue

        raw_status = sdk_row.get("status")
        mapped = _parse_sdk_order_status(raw_status)
        if mapped is None:
            _mark_order_unknown(
                db,
                order,
                raw_status=raw_status,
                reason=f"SDK 返回无法映射的状态: {raw_status}",
            )
            changed = True
            runtime_metrics.dequeue_order_sync(client_order_id)
            continue

        if order.status == OrderStatus.UNKNOWN:
            # 人工处理前不同步覆盖
            continue

        filled = sdk_row.get("filled") or sdk_row.get("filled_quantity")
        if filled is not None:
            try:
                fv = Decimal(str(filled))
                if fv > Decimal(str(order.filled_quantity)):
                    order.filled_quantity = fv
                    changed = True
            except Exception:
                pass

        if mapped != order.status:
            try:
                order_service.transition(order, mapped)
                changed = True
            except Exception:
                if mapped == OrderStatus.UNKNOWN or str(raw_status).lower() not in KNOWN_ORDER_STATUSES:
                    _mark_order_unknown(
                        db,
                        order,
                        raw_status=raw_status,
                        reason=f"状态迁移失败且无法映射: {order.status.value} -> {raw_status}",
                    )
                    changed = True
                else:
                    logger.warning(
                        "同步忽略非法迁移: %s %s -> %s",
                        client_order_id,
                        order.status.value,
                        mapped.value,
                    )
            else:
                broadcast_sync("order.update", order_to_dict(order))

        # 终态移出同步队列
        if order.status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.FAILED,
            OrderStatus.UNKNOWN,
        }:
            runtime_metrics.dequeue_order_sync(client_order_id)

    if changed:
        db.commit()
