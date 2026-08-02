from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIANGHUA_", env_file=".env", extra="ignore")

    # 数据库
    database_url: str = "postgresql+psycopg://lianghua:lianghua_dev@127.0.0.1:5432/lianghua"
    # 专用测试库（pytest）；未配置时默认将库名改为 *_test，禁止与开发库同库
    test_database_url: str = ""

    # SDK
    stock_sdk_path: str = ""
    futures_sdk_path: str = ""
    stock_account: str = ""
    futures_account: str = ""
    sdk_mode: str = "mock"  # mock / real
    sdk_driver: str = "auto"  # auto / sim / native

    # 真实交易 Broker（与 SDK 解耦）
    broker_type: str = ""  # 空 / adapter / qmt / ptrade
    # QMT
    qmt_client_key: str = ""
    qmt_account_id: str = ""
    qmt_path: str = ""
    qmt_rpc_url: str = ""  # 例如 http://127.0.0.1:9001
    qmt_poll_seconds: float = 1.0
    # PTrade
    ptrade_client_key: str = ""
    ptrade_account_id: str = ""
    ptrade_path: str = ""
    ptrade_rpc_url: str = ""
    ptrade_poll_seconds: float = 1.0
    
    # 行情源
    quote_provider: str = "mock"  # mock / akshare / tdx / ifind / tushare_pro / rqdata / wind
    akshare_poll_seconds: float = 10.0  # 新浪行情轮询间隔（新浪建议>=10s避免封IP）
    tdx_endpoint: str = "http://127.0.0.1:17709/"
    tdx_poll_seconds: float = 3.0
    ifind_username: str = ""
    ifind_password: str = ""
    ifind_poll_seconds: float = 3.0

    # 专业行情数据源（与 quote_provider 解耦，未来 TradingAdapter 内部可选使用 MarketDataAdapter）
    tushare_token: str = ""
    rqdata_username: str = ""
    rqdata_password: str = ""
    wind_poll_seconds: float = 5.0
    tushare_poll_seconds: float = 10.0
    rqdata_poll_seconds: float = 5.0

    # 安全
    config_key: str = ""
    # WebSocket 连接鉴权令牌；为空时开发环境不鉴权
    ws_token: str = ""

    # AI
    ai_provider: str = ""
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model: str = "gpt-4o-mini"

    # 运行
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    backup_dir: str = "./backups"
    # dev / production；生产环境错误响应不返回 debug
    app_env: str = "dev"

    # 时区
    tz: str = "Asia/Shanghai"
    # 下列配置仅追加交易所临时休市日；常规交易日由离线交易所日历提供。
    stock_market_holidays: str = ""
    futures_market_holidays: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"prod", "production"}


settings = Settings()
