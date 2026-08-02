import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.models.base import Base
from app.db.models import (  # noqa: F401 — 供 Alembic 发现 metadata
    account,
    account_asset,
    audit_log,
    backtest_run,
    instrument,
    kline_bar,
    market_snapshot,
    order,
    position,
    risk_check,
    risk_config,
    strategy,
    strategy_run,
    strategy_signal,
    strategy_version,
    system_config,
    system_event,
    system_state,
    trade,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 测试/CI 可通过 LIANGHUA_ALEMBIC_DATABASE_URL 覆盖目标库，避免误迁开发库
_alembic_url = os.environ.get("LIANGHUA_ALEMBIC_DATABASE_URL") or settings.database_url
config.set_main_option("sqlalchemy.url", _alembic_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
