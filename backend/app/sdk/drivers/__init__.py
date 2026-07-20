from app.schemas.enums import Market
from app.sdk.drivers.native import NativeThsDriver
from app.sdk.drivers.simulated import SimulatedThsDriver
from app.sdk.drivers.unconfigured import UnconfiguredDriver


def create_driver(*, market: Market, config: dict):
    """根据 sdk_driver 配置创建原生驱动实例。"""
    mode = (config.get("sdk_driver") or "auto").lower()
    path_key = "stock_sdk_path" if market == Market.STOCK else "futures_sdk_path"
    acct_key = "stock_account" if market == Market.STOCK else "futures_account"
    sdk_path = (config.get(path_key) or "").strip()
    account = (config.get(acct_key) or "").strip()

    if mode == "sim":
        return SimulatedThsDriver(market=market, config=config)
    if mode == "native":
        return NativeThsDriver(market=market, config=config)
    # auto: 路径/账号缺失 → unconfigured；已配置 → native 占位
    if not sdk_path or not account:
        return UnconfiguredDriver(market=market, config=config)
    return NativeThsDriver(market=market, config=config)
