"""pytest fixtures：强制使用独立测试库，避免污染开发库。"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.system_state import SystemState
from app.db import session as db_session
from app.main import app
from app.schemas.enums import SystemStatus

# 业务数据表：每用例前清空，避免 trades 等残留触发风控
_VOLATILE_TABLES = (
    "ai_reports",
    "trades",
    "orders",
    "risk_checks",
    "strategy_signals",
    "strategy_runs",
    "positions",
    "account_assets",
    "audit_logs",
    "system_events",
    "market_snapshots",
    "kline_bars",
    "watchlist",
    "data_sync_log",
)


def _derive_test_database_url(prod_url: str) -> str:
    """未配置时：将库名改为 *_test（如 lianghua → lianghua_test）。"""
    url = make_url(prod_url)
    name = url.database or "lianghua"
    if name.endswith("_test"):
        return prod_url
    return url.set(database=f"{name}_test").render_as_string(hide_password=False)


def resolve_test_database_url() -> str:
    configured = (settings.test_database_url or os.environ.get("LIANGHUA_TEST_DATABASE_URL") or "").strip()
    url = configured or _derive_test_database_url(settings.database_url)
    prod = make_url(settings.database_url)
    test = make_url(url)
    if (prod.host, prod.port, prod.database) == (test.host, test.port, test.database):
        raise RuntimeError(
            "测试库不能与开发库相同。请设置 LIANGHUA_TEST_DATABASE_URL "
            f"（当前开发库={settings.database_url}）"
        )
    return url


def _ensure_database_exists(url: str) -> None:
    """通过已有开发库连接创建测试库（Docker 镜像未必开放 postgres 维护库）。"""
    u = make_url(url)
    dbname = u.database
    if not dbname:
        raise RuntimeError(f"无效的测试库 URL: {url}")
    # 用开发库作管理连接；勿连 postgres（部分部署会拒或行为异常）
    admin_url = make_url(settings.database_url)
    admin = create_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": dbname},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        admin.dispose()


def _run_alembic_upgrade(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "app" / "db" / "migrations"))
    prev = os.environ.get("LIANGHUA_ALEMBIC_DATABASE_URL")
    os.environ["LIANGHUA_ALEMBIC_DATABASE_URL"] = url
    try:
        command.upgrade(cfg, "head")
    finally:
        if prev is None:
            os.environ.pop("LIANGHUA_ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["LIANGHUA_ALEMBIC_DATABASE_URL"] = prev


def _truncate_volatile(engine: Engine) -> None:
    tables = ", ".join(_VOLATILE_TABLES)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


def _reset_singletons(engine: Engine) -> None:
    """恢复 system_state / risk_configs 为迁移种子默认，隔离用例间配置污染。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE system_state
                SET status = 'ready', status_reason = 'test reset', updated_at = NOW()
                WHERE id = 1
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE risk_configs SET
                    allowed_symbols = '["600000.SH", "IF2509"]'::jsonb,
                    blocked_symbols = '["ST001.SH"]'::jsonb,
                    trading_sessions = '[]'::jsonb,
                    max_order_amount = 1000000,
                    max_order_quantity = 10000,
                    max_symbol_position = 100000,
                    max_total_position = 1000000,
                    daily_loss_limit = 50000,
                    daily_trade_count_limit = 100,
                    sdk_disconnect_timeout_seconds = 30,
                    quote_stale_timeout_seconds = 10,
                    consecutive_order_fail_limit = 5,
                    duplicate_signal_window_seconds = 3,
                    auto_cancel_on_breaker = true,
                    updated_at = NOW()
                WHERE id = 1
                """
            )
        )


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    """会话级：确保独立测试库存在、迁移到 head，并重绑全局 SessionLocal。"""
    url = resolve_test_database_url()
    _ensure_database_exists(url)
    _run_alembic_upgrade(url)

    engine = create_engine(
        url,
        pool_pre_ping=True,
        echo=False,
        connect_args={"connect_timeout": 3},
    )

    # 原地切换 bind：各模块 `from app.db.session import SessionLocal` 仍指向同一 sessionmaker
    previous_engine = db_session.engine
    previous_engine.dispose()
    db_session.engine = engine
    db_session.SessionLocal.configure(bind=engine)

    yield engine

    engine.dispose()
    db_session.engine = previous_engine
    db_session.SessionLocal.configure(bind=previous_engine)


@pytest.fixture(autouse=True)
def _isolate_db(test_engine: Engine) -> Generator[None, None, None]:
    """每个用例前清空业务表并重置单例配置，杜绝开发库/用例间污染。"""
    _truncate_volatile(test_engine)
    _reset_singletons(test_engine)
    yield


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(test_engine: Engine) -> Generator[Session, None, None]:
    session = db_session.SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def reset_system_state(db: Session):
    """测试前后将 system_state 重置为 ready。"""

    def _reset():
        row = db.get(SystemState, 1)
        if row is None:
            row = SystemState(id=1, status=SystemStatus.READY, status_reason="test reset")
            db.add(row)
        else:
            row.status = SystemStatus.READY
            row.status_reason = "test reset"
        db.commit()
        return row

    row = _reset()
    yield row
    _reset()
