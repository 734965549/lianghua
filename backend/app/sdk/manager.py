from app.core.config import settings
from app.schemas.enums import Market
from app.sdk.base import TradingAdapter
from app.sdk.factory import get_adapter

_stock_adapter: TradingAdapter | None = None
_futures_adapter: TradingAdapter | None = None


def _sdk_config() -> dict:
    config = {
        "mode": settings.sdk_mode,
        "sdk_driver": settings.sdk_driver,
        "quote_provider": settings.quote_provider,
        "akshare_poll_seconds": settings.akshare_poll_seconds,
        "tdx_endpoint": settings.tdx_endpoint,
        "tdx_poll_seconds": settings.tdx_poll_seconds,
        "ifind_username": settings.ifind_username,
        "ifind_password": settings.ifind_password,
        "ifind_poll_seconds": settings.ifind_poll_seconds,
        "stock_sdk_path": settings.stock_sdk_path,
        "futures_sdk_path": settings.futures_sdk_path,
        "stock_account": settings.stock_account,
        "futures_account": settings.futures_account,
        # 专业行情数据源配置
        "tushare_token": settings.tushare_token,
        "tushare_poll_seconds": settings.tushare_poll_seconds,
        "rqdata_username": settings.rqdata_username,
        "rqdata_password": settings.rqdata_password,
        "rqdata_poll_seconds": settings.rqdata_poll_seconds,
        "wind_poll_seconds": settings.wind_poll_seconds,
    }
    try:
        from app.db.session import SessionLocal
        from app.services.settings_service import SettingsService

        db = SessionLocal()
        try:
            config.update(SettingsService(db).get_market_data_runtime_config())
        finally:
            db.close()
    except Exception:
        # 数据库尚未就绪时保留环境变量配置，避免启动阶段循环依赖。
        pass
    return config


def get_stock_adapter() -> TradingAdapter:
    global _stock_adapter
    if _stock_adapter is None:
        _stock_adapter = get_adapter(Market.STOCK, _sdk_config())
    return _stock_adapter


def get_futures_adapter() -> TradingAdapter:
    global _futures_adapter
    if _futures_adapter is None:
        _futures_adapter = get_adapter(Market.FUTURES, _sdk_config())
    return _futures_adapter


def get_adapter_for_market(market: Market | str) -> TradingAdapter:
    if isinstance(market, str):
        market = Market(market)
    if market == Market.STOCK:
        return get_stock_adapter()
    return get_futures_adapter()


def ensure_connected() -> None:
    get_stock_adapter().connect()
    get_futures_adapter().connect()


def is_adapter_connected(adapter: TradingAdapter) -> bool:
    connected = getattr(adapter, "_connected", None)
    if isinstance(connected, bool):
        return connected
    return True


def sdk_healthy() -> bool:
    """股票/期货适配器均已连接视为健康。"""
    return is_adapter_connected(get_stock_adapter()) and is_adapter_connected(get_futures_adapter())


def refresh_sdk_connection_metrics() -> None:
    """根据适配器连接状态刷新断线计时。"""
    from app.services.runtime_metrics import mark_sdk_connected, mark_sdk_disconnected

    if sdk_healthy():
        mark_sdk_connected()
    else:
        mark_sdk_disconnected()


def reset_adapters() -> None:
    """测试辅助：重置单例。"""
    global _stock_adapter, _futures_adapter
    if _stock_adapter is not None:
        try:
            _stock_adapter.disconnect()
        except Exception:
            pass
    if _futures_adapter is not None:
        try:
            _futures_adapter.disconnect()
        except Exception:
            pass
    _stock_adapter = None
    _futures_adapter = None
