"""同花顺原始字段 ↔ 标准模型映射。"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction
from app.sdk.base import (
    AdapterError,
    SDKAuthFailed,
    SDKCancelRejected,
    SDKConnectionFailed,
    SDKOrderRejected,
    SDKResponseInvalid,
    SDKTimeout,
)
from app.sdk.models import (
    AccountSnapshot,
    CancelOrderResult,
    KlineBar,
    OrderUpdateEvent,
    PlaceOrderRequest,
    PlaceOrderResult,
    PositionSnapshot,
    QuoteSnapshot,
    TradeUpdateEvent,
)

# Simulated / 样例 THS 订单状态码 → 标准状态
THS_ORDER_STATUS_MAP: dict[str, OrderStatus] = {
    "0": OrderStatus.SUBMITTED,
    "1": OrderStatus.PARTIALLY_FILLED,
    "2": OrderStatus.FILLED,
    "3": OrderStatus.CANCELLED,
    "4": OrderStatus.FAILED,
    "5": OrderStatus.SUBMITTING,
}

THS_SIDE_TO_STD = {"B": OrderSide.BUY, "S": OrderSide.SELL, "buy": OrderSide.BUY, "sell": OrderSide.SELL}
STD_SIDE_TO_THS = {OrderSide.BUY: "B", OrderSide.SELL: "S"}

THS_PRICE_TYPE_TO_STD = {"0": PriceType.LIMIT, "1": PriceType.MARKET}
STD_PRICE_TYPE_TO_THS = {PriceType.LIMIT: "0", PriceType.MARKET: "1"}

OFFSET_TO_THS = {
    "open": "O",
    "close": "C",
    "close_today": "CT",
    "close_yesterday": "CY",
}

HEDGE_TO_THS = {"speculation": "S", "hedge": "H"}


def _dec(value, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def map_ths_order_status(raw) -> OrderStatus | None:
    if raw is None:
        return None
    if isinstance(raw, OrderStatus):
        return raw
    key = str(raw).strip()
    if key in THS_ORDER_STATUS_MAP:
        return THS_ORDER_STATUS_MAP[key]
    value = key.lower()
    if value in {s.value for s in OrderStatus}:
        return OrderStatus(value)
    aliases = {
        "partial": OrderStatus.PARTIALLY_FILLED,
        "canceled": OrderStatus.CANCELLED,
        "reject": OrderStatus.FAILED,
    }
    return aliases.get(value)


def map_account(raw: dict, *, market: Market, account_id: UUID | None = None) -> AccountSnapshot:
    acct_no = raw.get("AcctNo") or raw.get("account_no") or ""
    if not acct_no:
        raise SDKResponseInvalid("账户返回缺少 AcctNo")
    return AccountSnapshot(
        account_id=account_id or uuid4(),
        account_no=str(acct_no),
        total_asset=_dec(raw.get("TotalAsset")),
        available_cash=_dec(raw.get("AvailCash")),
        frozen_cash=_dec(raw.get("FrozenCash")),
        market_value=_dec(raw.get("MktValue")),
        pnl=_dec(raw.get("Pnl")),
        snapshot_time=datetime.now(timezone.utc),
        raw_payload=dict(raw),
    )


def map_position(raw: dict, *, market: Market, account_id: UUID) -> PositionSnapshot:
    symbol = raw.get("Symbol") or raw.get("symbol") or ""
    qty = _dec(raw.get("Qty") or raw.get("quantity"))
    avail = _dec(raw.get("AvailQty") or raw.get("available_quantity"), str(qty))
    return PositionSnapshot(
        account_id=account_id,
        symbol=str(symbol),
        market=market,
        direction=str(raw.get("Direction") or raw.get("direction") or "net"),
        quantity=qty,
        available_quantity=avail,
        avg_cost=_dec(raw.get("AvgCost") or raw.get("avg_cost")),
        market_value=_dec(raw.get("MktValue") or raw.get("market_value")),
        pnl=_dec(raw.get("Pnl") or raw.get("pnl")),
        snapshot_time=datetime.now(timezone.utc),
        raw_payload=dict(raw),
    )


def map_quote(raw: dict, *, market: Market) -> QuoteSnapshot:
    symbol = raw.get("Symbol") or raw.get("symbol") or ""
    return QuoteSnapshot(
        symbol=str(symbol),
        market=market,
        last_price=_dec(raw.get("LastPrice") or raw.get("last_price"), "0.01"),
        change_rate=_dec(raw.get("ChangeRate") or raw.get("change_rate")),
        volume=_dec(raw.get("Volume") or raw.get("volume")),
        bid_price=_dec(raw.get("BidPrice")) if raw.get("BidPrice") else None,
        ask_price=_dec(raw.get("AskPrice")) if raw.get("AskPrice") else None,
        bid_volume=_dec(raw.get("BidVol")) if raw.get("BidVol") else None,
        ask_volume=_dec(raw.get("AskVol")) if raw.get("AskVol") else None,
        quote_time=_parse_dt(raw.get("QuoteTime") or raw.get("quote_time")),
        raw_payload=dict(raw),
    )


def map_kline(raw: dict, *, market: Market, interval: str) -> KlineBar:
    symbol = raw.get("Symbol") or raw.get("symbol") or ""
    return KlineBar(
        symbol=str(symbol),
        market=market,
        interval=interval,
        bar_time=_parse_dt(raw.get("BarTime") or raw.get("bar_time")),
        open=_dec(raw.get("Open")),
        high=_dec(raw.get("High")),
        low=_dec(raw.get("Low")),
        close=_dec(raw.get("Close")),
        volume=_dec(raw.get("Volume")),
        raw_payload=dict(raw),
    )


def build_place_payload(request: PlaceOrderRequest, *, account_no: str) -> dict:
    """标准下单请求 → THS 原始 payload（不透传 client_order_id 到 SDK 字段）。"""
    offset = "O"
    if request.market == Market.FUTURES:
        meta_offset = (request.metadata or {}).get("offset")
        if request.action == SignalAction.OPEN:
            offset = "O"
        elif meta_offset:
            offset = OFFSET_TO_THS.get(str(meta_offset), "C")
        elif request.action in {SignalAction.CLOSE, SignalAction.REDUCE}:
            offset = "C"
    hedge = HEDGE_TO_THS.get(str((request.metadata or {}).get("hedge", "speculation")), "S")
    return {
        "AcctNo": account_no,
        "Symbol": request.symbol,
        "Side": STD_SIDE_TO_THS[request.side],
        "PriceType": STD_PRICE_TYPE_TO_THS.get(request.price_type, "0"),
        "Price": str(request.price or "0"),
        "Qty": str(request.quantity),
        "OffsetFlag": offset,
        "HedgeFlag": hedge,
        "LocalRef": request.client_order_id,
    }


def map_place_result(raw: dict, *, client_order_id: str) -> PlaceOrderResult:
    sdk_order_id = raw.get("OrderID") or raw.get("sdk_order_id")
    status = map_ths_order_status(raw.get("OrderStatus")) or OrderStatus.SUBMITTED
    success = raw.get("success", True)
    if not success:
        raise SDKOrderRejected(raw.get("Msg") or raw.get("message") or "下单被拒绝")
    return PlaceOrderResult(
        success=True,
        client_order_id=client_order_id,
        sdk_order_id=str(sdk_order_id) if sdk_order_id else None,
        status=status,
        message=str(raw.get("Msg") or raw.get("message") or ""),
        raw_payload=dict(raw),
    )


def map_cancel_result(raw: dict, *, client_order_id: str) -> CancelOrderResult:
    sdk_order_id = raw.get("OrderID") or raw.get("sdk_order_id")
    status = map_ths_order_status(raw.get("OrderStatus")) or OrderStatus.CANCELLED
    if not raw.get("success", True):
        raise SDKCancelRejected(raw.get("Msg") or "撤单被拒绝")
    return CancelOrderResult(
        success=True,
        client_order_id=client_order_id,
        sdk_order_id=str(sdk_order_id) if sdk_order_id else None,
        status=status,
        message=str(raw.get("Msg") or ""),
        raw_payload=dict(raw),
    )


def map_order_update(raw: dict, *, client_order_id: str | None) -> OrderUpdateEvent:
    status = map_ths_order_status(raw.get("OrderStatus"))
    if status is None:
        status = OrderStatus.UNKNOWN
    return OrderUpdateEvent(
        client_order_id=client_order_id,
        sdk_order_id=str(raw.get("OrderID") or raw.get("sdk_order_id") or "") or None,
        status=status,
        filled_quantity=_dec(raw.get("FilledQty") or raw.get("filled_quantity")),
        remaining_quantity=_dec(raw.get("RemainQty") or raw.get("remaining_quantity")),
        event_time=datetime.now(timezone.utc),
        raw_payload=dict(raw),
    )


def map_trade_update(raw: dict, *, market: Market, client_order_id: str | None) -> TradeUpdateEvent:
    side_raw = raw.get("Side") or raw.get("side") or "B"
    side = THS_SIDE_TO_STD.get(str(side_raw).upper(), OrderSide.BUY)
    if str(side_raw).lower() in {"buy", "sell"}:
        side = OrderSide(str(side_raw).lower())
    return TradeUpdateEvent(
        sdk_trade_id=str(raw.get("TradeID") or raw.get("sdk_trade_id") or ""),
        client_order_id=client_order_id,
        sdk_order_id=str(raw.get("OrderID") or raw.get("sdk_order_id") or "") or None,
        symbol=str(raw.get("Symbol") or raw.get("symbol") or ""),
        market=market,
        side=side,
        price=_dec(raw.get("Price") or raw.get("price")),
        quantity=_dec(raw.get("Qty") or raw.get("quantity")),
        fee=_dec(raw.get("Fee") or raw.get("fee")),
        trade_time=_parse_dt(raw.get("TradeTime") or raw.get("trade_time")),
        raw_payload=dict(raw),
    )


def map_query_order_row(raw: dict, *, client_order_id: str | None) -> dict:
    """轮询用 dict，含 client_order_id 供 sync_orders_trades 索引。"""
    status = map_ths_order_status(raw.get("OrderStatus"))
    return {
        "client_order_id": client_order_id or raw.get("LocalRef"),
        "sdk_order_id": raw.get("OrderID"),
        "status": status.value if status else str(raw.get("OrderStatus")),
        "filled": str(raw.get("FilledQty") or "0"),
        "filled_quantity": str(raw.get("FilledQty") or "0"),
        "remaining_quantity": str(raw.get("RemainQty") or "0"),
        "raw_payload": dict(raw),
    }


def map_adapter_error(exc: Exception) -> AdapterError:
    if isinstance(exc, AdapterError):
        return exc
    msg = str(exc)
    lower = msg.lower()
    if "auth" in lower or "授权" in msg or "登录" in msg:
        return SDKAuthFailed(msg)
    if "timeout" in lower or "超时" in msg:
        return SDKTimeout(msg)
    if "cancel" in lower or "撤单" in msg:
        return SDKCancelRejected(msg)
    if "order" in lower or "委托" in msg or "下单" in msg:
        return SDKOrderRejected(msg)
    if "connect" in lower or "连接" in msg:
        return SDKConnectionFailed(msg)
    return SDKResponseInvalid(msg)
