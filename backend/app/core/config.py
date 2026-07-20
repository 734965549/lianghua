from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIANGHUA_", env_file=".env", extra="ignore")

    # 数据库
    database_url: str = "postgresql+psycopg://lianghua:lianghua_dev@127.0.0.1:5432/lianghua"

    # SDK
    stock_sdk_path: str = ""
    futures_sdk_path: str = ""
    stock_account: str = ""
    futures_account: str = ""
    sdk_mode: str = "mock"  # mock / real
    sdk_driver: str = "auto"  # auto / sim / native

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

    # 时区
    tz: str = "Asia/Shanghai"


settings = Settings()
