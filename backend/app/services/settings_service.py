from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.response import BizError
from app.core.config import settings
from app.repositories.system_config_repo import SystemConfigRepository
from app.schemas.error_codes import ErrorCode
from app.services.audit_service import AuditService

SENSITIVE_FIELD_NAMES = [
    "database.url",
    "stock_sdk.password",
    "futures_sdk.password",
    "ai.api_key",
]


class SettingsService:
    def __init__(self, db: Session, correlation_id: str = ""):
        self.repo = SystemConfigRepository(db)
        self.audit = AuditService(db, correlation_id=correlation_id)
        self.correlation_id = correlation_id

    def _env_defaults(self) -> dict[str, str]:
        return {
            "database_url": settings.database_url,
            "stock_sdk_path": settings.stock_sdk_path,
            "stock_sdk_account": settings.stock_account,
            "futures_sdk_path": settings.futures_sdk_path,
            "futures_sdk_account": settings.futures_account,
            "ai_provider": settings.ai_provider,
            "ai_api_key": settings.ai_api_key,
            "ai_base_url": settings.ai_base_url,
            "ai_model": settings.ai_model,
            "backup_dir": settings.backup_dir,
        }

    def _parse_database_url(self, url: str) -> dict:
        parsed = urlparse(url.replace("postgresql+psycopg", "postgresql"))
        host = parsed.hostname or ""
        port = parsed.port or 5432
        dbname = parsed.path.lstrip("/") if parsed.path else ""
        configured = bool(host and dbname)
        return {
            "configured": configured,
            "host": host,
            "port": port,
            "dbname": dbname,
        }

    def get_settings(self) -> dict:
        env = self._env_defaults()
        db_url = self.repo.get_value("database_url", env["database_url"])
        if not self.repo.is_configured("database_url"):
            db_url = env["database_url"]

        stock_path = self.repo.get_value("stock_sdk_path", env["stock_sdk_path"]) or env["stock_sdk_path"]
        stock_account = self.repo.get_value("stock_sdk_account", env["stock_sdk_account"]) or env["stock_sdk_account"]
        futures_path = self.repo.get_value("futures_sdk_path", env["futures_sdk_path"]) or env["futures_sdk_path"]
        futures_account = (
            self.repo.get_value("futures_sdk_account", env["futures_sdk_account"]) or env["futures_sdk_account"]
        )
        ai_provider = self.repo.get_value("ai_provider", env["ai_provider"]) or env["ai_provider"]
        backup_dir = self.repo.get_value("backup_dir", env["backup_dir"]) or env["backup_dir"]

        return {
            "database": self._parse_database_url(db_url),
            "stock_sdk": {
                "configured": bool(stock_path or self.repo.is_configured("stock_sdk_password")),
                "path": stock_path,
                "account_ref": stock_account,
            },
            "futures_sdk": {
                "configured": bool(futures_path or self.repo.is_configured("futures_sdk_password")),
                "path": futures_path,
                "account_ref": futures_account,
            },
            "ai": {
                "provider": ai_provider,
                "configured": bool(ai_provider and self.repo.is_configured("ai_api_key")),
            },
            "backup_dir": backup_dir,
            "sdk_mode": settings.sdk_mode,
            "sensitive_fields": SENSITIVE_FIELD_NAMES,
        }

    def update_settings(self, payload: dict, correlation_id: str = "") -> dict:
        flat_updates: dict[str, str] = {}

        if database := payload.get("database"):
            if url := database.get("url"):
                flat_updates["database_url"] = url

        if stock := payload.get("stock_sdk"):
            if "path" in stock:
                flat_updates["stock_sdk_path"] = stock["path"] or ""
            if "account" in stock:
                flat_updates["stock_sdk_account"] = stock["account"] or ""
            if "password" in stock and stock["password"]:
                flat_updates["stock_sdk_password"] = stock["password"]

        if futures := payload.get("futures_sdk"):
            if "path" in futures:
                flat_updates["futures_sdk_path"] = futures["path"] or ""
            if "account" in futures:
                flat_updates["futures_sdk_account"] = futures["account"] or ""
            if "password" in futures and futures["password"]:
                flat_updates["futures_sdk_password"] = futures["password"]

        if ai := payload.get("ai"):
            if "provider" in ai:
                flat_updates["ai_provider"] = ai["provider"] or ""
            if "api_key" in ai and ai["api_key"]:
                flat_updates["ai_api_key"] = ai["api_key"]
            if "base_url" in ai:
                flat_updates["ai_base_url"] = ai["base_url"] or ""
            if "model" in ai:
                flat_updates["ai_model"] = ai["model"] or ""

        if "backup_dir" in payload:
            flat_updates["backup_dir"] = payload["backup_dir"] or ""

        sensitive_storage_keys = {
            "database_url",
            "stock_sdk_password",
            "futures_sdk_password",
            "ai_api_key",
        }

        for key, value in flat_updates.items():
            self.repo.upsert(
                config_key=key,
                value=value,
                is_sensitive=key in sensitive_storage_keys,
            )

        self.audit.log(
            action="update_settings",
            module="settings",
            object_type="system_config",
            object_id="",
            result="success",
            reason="更新系统配置",
            request_summary={"keys": list(flat_updates.keys())},
        )
        return self.get_settings()

    def test_database(self, url: str | None = None) -> dict:
        test_url = url or self.repo.get_value("database_url", settings.database_url) or settings.database_url
        try:
            engine = create_engine(test_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
            with engine.connect() as conn:
                version = conn.execute(text("SELECT version()")).scalar()
            engine.dispose()
            return {"ok": True, "server_version": str(version)}
        except Exception as exc:
            raise BizError(ErrorCode.SYS_DATABASE_UNAVAILABLE, f"数据库连接失败: {exc}") from exc

    def test_sdk(self, market: str) -> dict:
        if settings.sdk_mode == "mock":
            account = settings.stock_account if market == "stock" else settings.futures_account
            return {"ok": True, "account_no": account or "mock_account", "latency_ms": 0}

        from app.sdk.base import AdapterError
        from app.sdk import manager as sdk_manager
        from app.schemas.enums import Market as M

        m = M.STOCK if market == "stock" else M.FUTURES
        adapter = sdk_manager.get_adapter_for_market(m)
        try:
            status = adapter.connect()
            account_snap = adapter.get_account()
            return {
                "ok": status.connected,
                "account_no": account_snap.account_no,
                "latency_ms": status.latency_ms or 0,
            }
        except AdapterError as exc:
            raise BizError(exc.code, exc.message) from exc
        except Exception as exc:
            raise BizError(ErrorCode.SDK_CONNECTION_FAILED, f"SDK 连接测试失败: {exc}") from exc
