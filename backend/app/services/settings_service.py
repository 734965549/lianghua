import importlib.util
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.response import BizError
from app.core.time import to_utc_iso
from app.core.config import settings
from app.repositories.system_config_repo import SystemConfigRepository
from app.schemas.error_codes import ErrorCode
from app.services.audit_service import AuditService

SENSITIVE_FIELD_NAMES = [
    "database.url",
    "stock_sdk.password",
    "futures_sdk.password",
    "market_data.ifind_password",
    "market_data.tushare_token",
    "market_data.rqdata_password",
    "ai.api_key",
]

MARKET_DATA_PROVIDERS = [
    {
        "id": "ifind",
        "label": "同花顺 iFinD",
        "tier": "专业",
        "coverage": "股票 · 期货",
        "mode": "实时",
        "description": "官方数据接口，支持全市场目录和实时买卖盘。",
    },
    {
        "id": "tdx",
        "label": "通达信 TQ",
        "tier": "免费接入",
        "coverage": "股票 · 期货",
        "mode": "准实时",
        "description": "通过通达信官方本地 HTTP 接口读取行情，需开启 TQ 客户端。",
    },
    {
        "id": "akshare",
        "label": "AKShare 聚合",
        "tier": "免费",
        "coverage": "股票 · 期货",
        "mode": "轮询",
        "description": "免密钥聚合公开财经网站数据，适合研究和行情浏览。",
    },
    {
        "id": "tushare_pro",
        "label": "Tushare Pro",
        "tier": "免费注册",
        "coverage": "股票 · 期货",
        "mode": "日频/分钟",
        "description": "使用个人 Token 和积分权限，适合历史数据与研究。",
    },
    {
        "id": "rqdata",
        "label": "RQData",
        "tier": "授权",
        "coverage": "股票 · 期货",
        "mode": "轮询",
        "description": "米筐统一行情接口，适合研究和回测。",
    },
    {
        "id": "wind",
        "label": "Wind",
        "tier": "专业",
        "coverage": "股票 · 期货",
        "mode": "实时",
        "description": "连接本机 Wind 终端和 WindPy。",
    },
    {
        "id": "mock",
        "label": "Mock 模拟行情",
        "tier": "内置",
        "coverage": "股票 · 期货",
        "mode": "模拟",
        "description": "离线开发和功能演示，不代表真实市场。",
    },
]

REALTIME_PROVIDERS = {"ifind", "tdx", "akshare", "rqdata", "wind"}
CATALOG_SYNC_PROVIDERS = {"ifind", "akshare"}


class SettingsService:
    def __init__(self, db: Session, correlation_id: str = ""):
        self.repo = SystemConfigRepository(db)
        self.audit = AuditService(db, correlation_id=correlation_id)
        self.correlation_id = correlation_id

    def _env_defaults(self) -> dict[str, Any]:
        return {
            "database_url": settings.database_url,
            "stock_sdk_path": settings.stock_sdk_path,
            "stock_sdk_account": settings.stock_account,
            "futures_sdk_path": settings.futures_sdk_path,
            "futures_sdk_account": settings.futures_account,
            "quote_provider": settings.quote_provider,
            "akshare_poll_seconds": settings.akshare_poll_seconds,
            "tdx_endpoint": settings.tdx_endpoint,
            "tdx_poll_seconds": settings.tdx_poll_seconds,
            "ifind_username": settings.ifind_username,
            "ifind_password": settings.ifind_password,
            "ifind_poll_seconds": settings.ifind_poll_seconds,
            "tushare_token": settings.tushare_token,
            "tushare_poll_seconds": settings.tushare_poll_seconds,
            "rqdata_username": settings.rqdata_username,
            "rqdata_password": settings.rqdata_password,
            "rqdata_poll_seconds": settings.rqdata_poll_seconds,
            "wind_poll_seconds": settings.wind_poll_seconds,
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

    def _resolved_value(self, key: str, env_value: str) -> str:
        """数据库配置优先；没有数据库记录时回退环境变量。"""
        row = self.repo.get_by_key(key)
        if row is None:
            return env_value
        return self.repo.get_value(key, "")

    def get_ai_runtime_config(self, overrides: dict[str, Any] | None = None) -> dict[str, str]:
        env = self._env_defaults()
        config = {
            "provider": self._resolved_value("ai_provider", env["ai_provider"]),
            "api_key": self._resolved_value("ai_api_key", env["ai_api_key"]),
            "base_url": self._resolved_value("ai_base_url", env["ai_base_url"]),
            "model": self._resolved_value("ai_model", env["ai_model"]) or "gpt-4o-mini",
        }
        if overrides:
            if "provider" in overrides:
                config["provider"] = str(overrides["provider"] or "").strip()
            if overrides.get("api_key"):
                config["api_key"] = str(overrides["api_key"]).strip()
            if "base_url" in overrides:
                config["base_url"] = str(overrides["base_url"] or "").strip()
            if "model" in overrides:
                config["model"] = str(overrides["model"] or "").strip() or "gpt-4o-mini"
        config["provider"] = config["provider"].lower()
        return config

    def get_market_data_runtime_config(
        self,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        env = self._env_defaults()
        config: dict[str, Any] = {
            "quote_provider": self._resolved_value(
                "quote_provider", str(env["quote_provider"])
            ).strip().lower(),
            "akshare_poll_seconds": float(
                self._resolved_value(
                    "akshare_poll_seconds", str(env["akshare_poll_seconds"])
                )
                or 10.0
            ),
            "tdx_endpoint": self._resolved_value(
                "tdx_endpoint", str(env["tdx_endpoint"])
            ).strip(),
            "tdx_poll_seconds": float(
                self._resolved_value(
                    "tdx_poll_seconds", str(env["tdx_poll_seconds"])
                )
                or 3.0
            ),
            "ifind_username": self._resolved_value(
                "ifind_username", str(env["ifind_username"])
            ).strip(),
            "ifind_password": self._resolved_value(
                "ifind_password", str(env["ifind_password"])
            ),
            "ifind_poll_seconds": float(
                self._resolved_value(
                    "ifind_poll_seconds", str(env["ifind_poll_seconds"])
                )
                or 3.0
            ),
            "tushare_token": self._resolved_value(
                "tushare_token", str(env["tushare_token"])
            ).strip(),
            "tushare_poll_seconds": float(
                self._resolved_value(
                    "tushare_poll_seconds", str(env["tushare_poll_seconds"])
                )
                or 10.0
            ),
            "rqdata_username": self._resolved_value(
                "rqdata_username", str(env["rqdata_username"])
            ).strip(),
            "rqdata_password": self._resolved_value(
                "rqdata_password", str(env["rqdata_password"])
            ),
            "rqdata_poll_seconds": float(
                self._resolved_value(
                    "rqdata_poll_seconds", str(env["rqdata_poll_seconds"])
                )
                or 5.0
            ),
            "wind_poll_seconds": float(
                self._resolved_value(
                    "wind_poll_seconds", str(env["wind_poll_seconds"])
                )
                or 5.0
            ),
        }
        if overrides:
            if "provider" in overrides:
                config["quote_provider"] = str(overrides["provider"] or "mock").strip().lower()
            if "ifind_username" in overrides:
                config["ifind_username"] = str(overrides["ifind_username"] or "").strip()
            if overrides.get("ifind_password"):
                config["ifind_password"] = str(overrides["ifind_password"])
            if "ifind_poll_seconds" in overrides:
                config["ifind_poll_seconds"] = max(
                    1.0, float(overrides["ifind_poll_seconds"] or 3.0)
                )
            for key, default in (
                ("akshare_poll_seconds", 10.0),
                ("tdx_poll_seconds", 3.0),
                ("tushare_poll_seconds", 10.0),
                ("rqdata_poll_seconds", 5.0),
                ("wind_poll_seconds", 5.0),
            ):
                if key in overrides:
                    config[key] = max(1.0, float(overrides[key] or default))
            if "tdx_endpoint" in overrides:
                config["tdx_endpoint"] = str(
                    overrides["tdx_endpoint"] or "http://127.0.0.1:17709/"
                ).strip()
            if overrides.get("tushare_token"):
                config["tushare_token"] = str(overrides["tushare_token"]).strip()
            if "rqdata_username" in overrides:
                config["rqdata_username"] = str(
                    overrides["rqdata_username"] or ""
                ).strip()
            if overrides.get("rqdata_password"):
                config["rqdata_password"] = str(overrides["rqdata_password"])
        return config

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
        market_data_config = self.get_market_data_runtime_config()
        ai_config = self.get_ai_runtime_config()
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
            "market_data": {
                "provider": market_data_config["quote_provider"],
                "configured": self._market_data_configured(market_data_config),
                "realtime": market_data_config["quote_provider"]
                in REALTIME_PROVIDERS,
                "catalog_sync_supported": market_data_config["quote_provider"]
                in CATALOG_SYNC_PROVIDERS,
                "providers": [
                    {
                        **item,
                        "component_installed": self._provider_component_installed(
                            item["id"]
                        ),
                    }
                    for item in MARKET_DATA_PROVIDERS
                ],
                "akshare_poll_seconds": market_data_config[
                    "akshare_poll_seconds"
                ],
                "tdx_endpoint": market_data_config["tdx_endpoint"],
                "tdx_poll_seconds": market_data_config["tdx_poll_seconds"],
                "ifind_username_ref": market_data_config["ifind_username"],
                "ifind_credentials_configured": bool(
                    market_data_config["ifind_username"]
                    and market_data_config["ifind_password"]
                ),
                "ifind_component_installed": self._ifind_component_installed(),
                "ifind_poll_seconds": market_data_config["ifind_poll_seconds"],
                "tushare_token_configured": bool(
                    market_data_config["tushare_token"]
                ),
                "tushare_poll_seconds": market_data_config[
                    "tushare_poll_seconds"
                ],
                "rqdata_username_ref": market_data_config["rqdata_username"],
                "rqdata_credentials_configured": bool(
                    market_data_config["rqdata_username"]
                    and market_data_config["rqdata_password"]
                ),
                "rqdata_poll_seconds": market_data_config[
                    "rqdata_poll_seconds"
                ],
                "wind_poll_seconds": market_data_config["wind_poll_seconds"],
            },
            "ai": {
                "provider": ai_config["provider"],
                "base_url": ai_config["base_url"],
                "model": ai_config["model"],
                "configured": bool(ai_config["provider"] and ai_config["api_key"]),
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

        if market_data := payload.get("market_data"):
            if "provider" in market_data:
                provider = str(market_data["provider"] or "mock").strip().lower()
                if provider not in {
                    item["id"] for item in MARKET_DATA_PROVIDERS
                }:
                    raise BizError(
                        ErrorCode.SYS_INVALID_CONFIG,
                        f"不支持行情源：{provider}",
                    )
                flat_updates["quote_provider"] = provider
            for key, default in (
                ("akshare_poll_seconds", 10.0),
                ("tdx_poll_seconds", 3.0),
                ("tushare_poll_seconds", 10.0),
                ("rqdata_poll_seconds", 5.0),
                ("wind_poll_seconds", 5.0),
            ):
                if key in market_data:
                    flat_updates[key] = str(
                        max(1.0, float(market_data[key] or default))
                    )
            if "tdx_endpoint" in market_data:
                flat_updates["tdx_endpoint"] = (
                    market_data["tdx_endpoint"]
                    or "http://127.0.0.1:17709/"
                )
            if "ifind_username" in market_data:
                flat_updates["ifind_username"] = market_data["ifind_username"] or ""
            if "ifind_password" in market_data and market_data["ifind_password"]:
                flat_updates["ifind_password"] = market_data["ifind_password"]
            if "ifind_poll_seconds" in market_data:
                flat_updates["ifind_poll_seconds"] = str(
                    max(1.0, float(market_data["ifind_poll_seconds"] or 3.0))
                )
            if "tushare_token" in market_data and market_data["tushare_token"]:
                flat_updates["tushare_token"] = market_data["tushare_token"]
            if "rqdata_username" in market_data:
                flat_updates["rqdata_username"] = (
                    market_data["rqdata_username"] or ""
                )
            if "rqdata_password" in market_data and market_data["rqdata_password"]:
                flat_updates["rqdata_password"] = market_data["rqdata_password"]

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
            "ifind_password",
            "tushare_token",
            "rqdata_password",
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

    def test_market_data(self, overrides: dict[str, Any] | None = None) -> dict:
        from app.schemas.enums import Market
        from app.sdk.base import AdapterError
        from app.sdk.market_data.factory import get_market_data_adapter

        config = self.get_market_data_runtime_config(overrides)
        provider = config["quote_provider"]
        if provider == "mock":
            return {
                "ok": True,
                "provider": "mock",
                "realtime": False,
                "message": "Mock 为模拟行情，不连接外部实时数据源",
            }
        supported = {item["id"] for item in MARKET_DATA_PROVIDERS}
        if provider not in supported:
            raise BizError(
                ErrorCode.SYS_INVALID_CONFIG,
                f"暂不支持行情源：{provider}",
            )
        if not self._market_data_configured(config):
            label = self._provider_label(provider)
            raise BizError(
                ErrorCode.SYS_INVALID_CONFIG,
                f"{label} 尚未完成必要配置或本地组件未安装",
            )

        sample_symbol = str((overrides or {}).get("sample_symbol") or "600000.SH").strip()
        if provider == "akshare":
            from app.sdk.akshare_adapter import AkshareAdapter

            # 连接测试只验证单标的轻量接口，禁止同时启动全市场后台同步。
            adapter = AkshareAdapter(
                market=Market.STOCK,
                config={**config, "akshare_background_sync": False},
            )
        else:
            adapter = get_market_data_adapter(Market.STOCK, provider, config)
        started_at = perf_counter()
        try:
            adapter.connect()
            quote = adapter.get_quote(sample_symbol)
        except AdapterError as exc:
            raise BizError(exc.code, exc.message, retryable=exc.retryable) from exc
        except Exception as exc:
            raise BizError(
                ErrorCode.SDK_CONNECTION_FAILED,
                f"{self._provider_label(provider)} 连接测试失败（{type(exc).__name__}）",
            ) from exc
        finally:
            try:
                adapter.disconnect()
            except Exception:
                pass

        latency_ms = round((perf_counter() - started_at) * 1000)
        self.audit.log(
            action="test_market_data_connection",
            module="settings",
            object_type="market_data_provider",
            object_id=provider,
            result="success",
            reason=f"{self._provider_label(provider)} 行情连接测试成功",
            request_summary={"provider": provider, "sample_symbol": sample_symbol},
        )
        return {
            "ok": True,
            "provider": provider,
            "realtime": provider in REALTIME_PROVIDERS,
            "sample_symbol": quote.symbol,
            "sample_price": str(quote.last_price),
            "quote_time": to_utc_iso(quote.quote_time),
            "latency_ms": latency_ms,
        }

    @staticmethod
    def _ifind_component_installed() -> bool:
        from app.sdk.market_data.ifind_adapter import IFindAdapter

        return IFindAdapter.component_installed()

    @staticmethod
    def _provider_label(provider: str) -> str:
        return next(
            (
                str(item["label"])
                for item in MARKET_DATA_PROVIDERS
                if item["id"] == provider
            ),
            provider,
        )

    @classmethod
    def _provider_component_installed(cls, provider: str) -> bool:
        if provider in {"mock", "tdx"}:
            return True
        if provider == "ifind":
            return cls._ifind_component_installed()
        module_name = {
            "akshare": "akshare",
            "tushare_pro": "tushare",
            "rqdata": "rqdatac",
            "wind": "WindPy",
        }.get(provider)
        return bool(module_name and importlib.util.find_spec(module_name))

    def _market_data_configured(self, config: dict[str, Any]) -> bool:
        provider = config["quote_provider"]
        if provider == "ifind":
            return bool(
                config["ifind_username"]
                and config["ifind_password"]
                and self._ifind_component_installed()
            )
        if provider == "tushare_pro":
            return bool(
                config["tushare_token"]
                and self._provider_component_installed(provider)
            )
        if provider == "rqdata":
            return bool(
                config["rqdata_username"]
                and config["rqdata_password"]
                and self._provider_component_installed(provider)
            )
        if provider == "tdx":
            return bool(config["tdx_endpoint"])
        if provider in {"akshare", "wind"}:
            return self._provider_component_installed(provider)
        return provider == "mock"

    def test_ai(self, overrides: dict[str, Any] | None = None) -> dict:
        from openai import APIConnectionError, APITimeoutError, AuthenticationError

        from app.services.ai_client import get_ai_client

        config = self.get_ai_runtime_config(overrides)
        if not config["provider"]:
            raise BizError(ErrorCode.SYS_INVALID_CONFIG, "请先选择 AI Provider")
        if config["provider"] != "openai":
            raise BizError(
                ErrorCode.SYS_INVALID_CONFIG,
                f"暂不支持 AI Provider：{config['provider']}",
            )
        if not config["api_key"]:
            raise BizError(ErrorCode.SYS_INVALID_CONFIG, "请填写 AI API Key")
        if not config["model"]:
            raise BizError(ErrorCode.SYS_INVALID_CONFIG, "请填写模型名称")

        client = get_ai_client(config, timeout=12.0)
        started_at = perf_counter()
        try:
            models = client.models.list()
            available_models = [item.id for item in models.data]
        except AuthenticationError as exc:
            raise BizError(ErrorCode.AI_REPORT_FAILED, "API Key 无效或没有访问权限") from exc
        except APITimeoutError as exc:
            raise BizError(ErrorCode.AI_REPORT_FAILED, "AI 服务连接超时，请检查网络或 Base URL") from exc
        except APIConnectionError as exc:
            raise BizError(ErrorCode.AI_REPORT_FAILED, "无法连接 AI 服务，请检查 Base URL 和网络") from exc
        except Exception as exc:
            raise BizError(
                ErrorCode.AI_REPORT_FAILED,
                f"AI 连接测试失败（{type(exc).__name__}）",
            ) from exc

        latency_ms = round((perf_counter() - started_at) * 1000)
        self.audit.log(
            action="test_ai_connection",
            module="settings",
            object_type="ai_provider",
            object_id=config["provider"],
            result="success",
            reason="AI 连接测试成功",
            request_summary={
                "provider": config["provider"],
                "model": config["model"],
                "base_url_configured": bool(config["base_url"]),
            },
        )
        return {
            "ok": True,
            "provider": config["provider"],
            "model": config["model"],
            "model_available": config["model"] in available_models,
            "latency_ms": latency_ms,
        }

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
