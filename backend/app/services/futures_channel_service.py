"""期货直连通道（CTP / TqSdk）的统一交易就绪判定。"""

from __future__ import annotations

from app.broker import manager as broker_manager
from app.schemas.enums import Market


def ctp_futures_readiness() -> tuple[bool, str]:
    """兼容旧名：等价于 futures_channel_readiness()。"""
    return futures_channel_readiness()


def futures_channel_readiness() -> tuple[bool, str]:
    """返回期货直连通道是否可交易及可呈现给用户的原因。

    非 CTP/TqSdk 的期货适配保留既有行为；一旦路由到直连通道，必须同时满足
    连接、READY 状态和首次对账完成，不能仅凭策略进程存活继续发送委托。
    """
    try:
        broker = broker_manager.get_broker(Market.FUTURES)
        broker_name = getattr(broker, "name", "")
        if broker_name not in {"ctp", "tqsdk"}:
            return True, ""
        health = getattr(broker, "health", lambda: {})()
        health = health if isinstance(health, dict) else {}
        connected = bool(broker.is_connected())
        state = str(health.get("trader_state") or "unknown")
        reconciled = bool(health.get("reconciled"))
        if connected and state == "ready" and reconciled:
            return True, ""
        label = "CTP" if broker_name == "ctp" else "TqSdk"
        detail = (
            f"{label} 通道不可交易：state={state}，"
            f"connected={str(connected).lower()}，reconciled={str(reconciled).lower()}"
        )
        return False, detail
    except Exception as exc:
        return False, f"期货通道状态获取失败：{exc}"
