"""TqSdk 字段映射：合约、开平、订单状态。"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from typing import Any

from app.schemas.enums import OffsetFlag, OrderSide, OrderStatus, PriceType

_SHFE_INE = {"SHFE", "INE"}
_EXCHANGE_ALIASES = {
    "SHF": "SHFE",
    "SHFE": "SHFE",
    "INE": "INE",
    "DCE": "DCE",
    "CZC": "CZCE",
    "CZCE": "CZCE",
    "CFX": "CFFEX",
    "CFFEX": "CFFEX",
    "GFE": "GFEX",
    "GFEX": "GFEX",
}


def mask_account_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f"***{text[-4:]}" if len(text) > 4 else "***"


def normalize_exchange_id(exchange_id: str | None) -> str:
    raw = str(exchange_id or "").strip().upper()
    return _EXCHANGE_ALIASES.get(raw, raw)


def parse_symbol_exchange(symbol: str, exchange_id: str = "") -> tuple[str, str]:
    """把项目合约拆成 (instrument_id, exchange_id)。

    支持：
    - rb2610 + exchange_id=SHFE
    - SHFE.rb2610
    - RB2610.SHF / rb2610.SHFE
    """
    text = str(symbol or "").strip()
    exchange = normalize_exchange_id(exchange_id)
    if not text:
        return "", exchange

    if "." in text:
        left, right = text.split(".", 1)
        left_u, right_u = left.strip().upper(), right.strip().upper()
        # SHFE.rb2610
        if left_u in _EXCHANGE_ALIASES or left_u in {"SHFE", "INE", "DCE", "CZCE", "CFFEX", "GFEX"}:
            return right.strip(), normalize_exchange_id(left_u)
        # rb2610.SHFE / RB2610.SHF
        if right_u in _EXCHANGE_ALIASES or right_u in {"SHFE", "INE", "DCE", "CZCE", "CFFEX", "GFEX", "SHF", "CZC", "CFX", "GFE"}:
            return left.strip(), normalize_exchange_id(right_u)
    return text, exchange


def to_tq_symbol(symbol: str, exchange_id: str = "") -> str:
    instrument, exchange = parse_symbol_exchange(symbol, exchange_id)
    if not instrument or not exchange:
        raise ValueError(f"合约缺少明确交易所代码: symbol={symbol!r} exchange_id={exchange_id!r}")
    return f"{exchange}.{instrument}"


def from_tq_symbol(tq_symbol: str) -> tuple[str, str]:
    text = str(tq_symbol or "").strip()
    if "." in text:
        exchange, instrument = text.split(".", 1)
        return instrument, normalize_exchange_id(exchange)
    return text, ""


def client_order_id_to_tq_order_id(client_order_id: str) -> str:
    """把本地 client_order_id 转成稳定、可重连匹配的 TqSdk order_id。"""
    raw = str(client_order_id or "").strip()
    if not raw:
        raise ValueError("client_order_id 不能为空")
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"lh_{cleaned}"
    if len(cleaned) > 64:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:40]
        cleaned = f"lh_{digest}"
    return cleaned


def map_side(side: OrderSide | str) -> str:
    value = side.value if isinstance(side, OrderSide) else str(side or "").strip().lower()
    if value == OrderSide.BUY.value:
        return "BUY"
    if value == OrderSide.SELL.value:
        return "SELL"
    raise ValueError(f"不支持的买卖方向: {side}")


def map_offset(offset: OffsetFlag | str | None, exchange_id: str) -> str:
    """映射开平标志；不支持的组合明确拒绝，不静默降级。"""
    if offset is None:
        raise ValueError("期货委托必须明确指定 offset_flag")
    value = offset.value if isinstance(offset, OffsetFlag) else str(offset).strip().lower()
    exchange = normalize_exchange_id(exchange_id)

    if value == OffsetFlag.OPEN.value:
        return "OPEN"
    if value == OffsetFlag.CLOSE.value:
        return "CLOSE"
    if value == OffsetFlag.CLOSE_TODAY.value:
        if exchange not in _SHFE_INE:
            raise ValueError(f"{exchange or '未知交易所'} 不支持 CLOSE_TODAY，请使用 CLOSE")
        return "CLOSETODAY"
    if value == OffsetFlag.CLOSE_YESTERDAY.value:
        # 上期所/能源：平昨用 CLOSE；其他交易所统一 CLOSE
        return "CLOSE"
    raise ValueError(f"不支持的开平标志: {offset}")


def map_offset_flag_from_tq(offset: str | None) -> OffsetFlag | None:
    value = str(offset or "").strip().upper()
    if value == "OPEN":
        return OffsetFlag.OPEN
    if value == "CLOSE":
        return OffsetFlag.CLOSE
    if value == "CLOSETODAY":
        return OffsetFlag.CLOSE_TODAY
    return None


def map_side_from_tq(direction: str | None) -> OrderSide | None:
    value = str(direction or "").strip().upper()
    if value == "BUY":
        return OrderSide.BUY
    if value == "SELL":
        return OrderSide.SELL
    return None


def map_order_status(order: Any) -> OrderStatus:
    status = str(getattr(order, "status", "") or "").upper()
    volume_orign = _as_int(getattr(order, "volume_orign", 0))
    volume_left = _as_int(getattr(order, "volume_left", 0))
    filled = max(0, volume_orign - volume_left)
    is_error = bool(getattr(order, "is_error", False))

    if status == "ALIVE":
        if filled > 0:
            return OrderStatus.PARTIALLY_FILLED
        return OrderStatus.SUBMITTED
    if status == "FINISHED":
        if is_error:
            return OrderStatus.FAILED
        if volume_left == 0 and volume_orign > 0:
            return OrderStatus.FILLED
        if volume_left > 0:
            return OrderStatus.CANCELLED
        # volume_orign==0 的异常完结
        return OrderStatus.FAILED if is_error else OrderStatus.CANCELLED
    return OrderStatus.UNKNOWN


def filled_quantity(order: Any) -> Decimal:
    volume_orign = _as_int(getattr(order, "volume_orign", 0))
    volume_left = _as_int(getattr(order, "volume_left", 0))
    return Decimal(max(0, volume_orign - volume_left))


def remaining_quantity(order: Any) -> Decimal:
    return Decimal(_as_int(getattr(order, "volume_left", 0)))


def ensure_limit_only(price_type: PriceType | str | None) -> None:
    value = price_type.value if isinstance(price_type, PriceType) else str(price_type or "").strip().lower()
    if value != PriceType.LIMIT.value:
        raise ValueError("TqSdkBroker 首版仅支持限价单（LIMIT），不支持市价/套利等静默降级")


def _as_int(value: Any) -> int:
    try:
        return int(Decimal(str(value or 0)))
    except Exception:
        return 0


def as_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        if value is None:
            return Decimal(default)
        return Decimal(str(value))
    except Exception:
        return Decimal(default)
