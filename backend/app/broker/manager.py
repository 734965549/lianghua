from app.broker.adapter_broker import AdapterBroker
from app.broker.base import Broker
from app.broker.ptrade_broker import PTradeBroker
from app.broker.qmt_broker import QMTBroker
from app.core.config import settings
from app.schemas.enums import Market
from app.sdk import manager as sdk_manager

_stock_broker: Broker | None = None
_futures_broker: Broker | None = None


def _broker_config() -> dict:
    """汇总 broker 相关配置。"""
    return {
        "qmt_client_key": settings.qmt_client_key,
        "qmt_account_id": settings.qmt_account_id,
        "qmt_path": settings.qmt_path,
        "qmt_rpc_url": settings.qmt_rpc_url,
        "qmt_poll_seconds": settings.qmt_poll_seconds,
        "ptrade_client_key": settings.ptrade_client_key,
        "ptrade_account_id": settings.ptrade_account_id,
        "ptrade_path": settings.ptrade_path,
        "ptrade_rpc_url": settings.ptrade_rpc_url,
        "ptrade_poll_seconds": settings.ptrade_poll_seconds,
    }


def _create_broker(market: Market) -> Broker:
    """根据 broker_type 配置创建真实 Broker 或包装 SDK Adapter。"""
    broker_type = settings.broker_type.lower()
    config = _broker_config()

    if broker_type == "qmt" and market == Market.STOCK:
        return QMTBroker(config)
    if broker_type == "ptrade" and market == Market.STOCK:
        return PTradeBroker(config)

    # 默认：基于现有 SDK Adapter 包装
    adapter_factory = (
        sdk_manager.get_stock_adapter if market == Market.STOCK else sdk_manager.get_futures_adapter
    )
    return AdapterBroker(adapter_factory())


def _ensure_broker(
    current_broker: Broker | None,
    market: Market,
) -> Broker:
    """在配置或 adapter 单例变更后自动重建 broker。"""
    expected_type = settings.broker_type.lower()
    if current_broker is not None:
        current_name = getattr(current_broker, "name", "")
        if expected_type == "qmt" and current_name == "qmt":
            return current_broker
        if expected_type == "ptrade" and current_name == "ptrade":
            return current_broker
        if expected_type in ("", "adapter") and isinstance(current_broker, AdapterBroker):
            current_adapter = getattr(current_broker, "adapter", None)
            expected_adapter = (
                sdk_manager.get_stock_adapter() if market == Market.STOCK else sdk_manager.get_futures_adapter()
            )
            if current_adapter is expected_adapter:
                return current_broker

    return _create_broker(market)


def get_broker(market: Market | str) -> Broker:
    """获取指定市场的 Broker。支持 QMT / PTrade / SDK Adapter。"""
    global _stock_broker, _futures_broker
    if isinstance(market, str):
        market = Market(market)

    if market == Market.STOCK:
        _stock_broker = _ensure_broker(_stock_broker, Market.STOCK)
        return _stock_broker

    _futures_broker = _ensure_broker(_futures_broker, Market.FUTURES)
    return _futures_broker


def reset_brokers() -> None:
    """测试辅助：重置 Broker 单例。"""
    global _stock_broker, _futures_broker
    _stock_broker = None
    _futures_broker = None
