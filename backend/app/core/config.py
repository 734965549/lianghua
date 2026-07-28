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
    
    # 行情源
    quote_provider: str = "mock"  # mock / akshare / ths
    akshare_poll_seconds: float = 10.0  # 新浪行情轮询间隔（新浪建议>=10s避免封IP）

    # 安全
    config_key: str = ""

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

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"prod", "production"}


settings = Settings()
