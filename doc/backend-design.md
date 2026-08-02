# 后端设计

## 技术栈

| 类型 | 选型 |
| --- | --- |
| Web 框架 | FastAPI |
| 数据校验 | Pydantic |
| ORM | SQLAlchemy 2.x |
| 数据库迁移 | Alembic |
| 数据库 | PostgreSQL 15+ |
| 调度 | APScheduler，后续可切换 Celery |
| 日志 | Python logging + 结构化 JSON 日志 |

## 推荐目录结构

```text
backend/
  app/
    main.py
    api/
      routes/
      dependencies.py
      response.py
    core/
      config.py
      logging.py
      security.py
      time.py
    db/
      session.py
      models/
      migrations/
    schemas/
    repositories/
    services/
      system_service.py
      market_service.py
      strategy_service.py
      risk_service.py
      order_service.py
      trade_service.py
      ai_report_service.py
      ai_strategy_service.py             AI 自然语言策略定义生成
      strategy_builder_service.py        规则策略 CRUD / 发布 / 校验
      audit_service.py
    sdk/
      base.py
      mock_adapter.py
      stock_adapter.py
      futures_adapter.py
    strategies/
      base.py
      samples/
    workers/
      scheduler.py
      recovery.py
      sync_jobs.py
    tests/
```

## 分层规则

1. `api` 只做 HTTP/WebSocket 入参、响应和错误转换。
2. `services` 负责业务编排和事务边界。
3. `repositories` 只封装数据库读写。
4. `sdk` 只处理 SDK 差异和标准模型转换。
5. `strategies` 只生成标准交易信号，不依赖订单服务和 SDK。
6. `workers` 只调用服务层，不直接写库。

## 配置管理

配置来源优先级从高到低：

1. Windows 环境变量。
2. 本地加密配置文件。
3. 数据库中的非敏感配置。
4. 默认配置。

敏感字段包括 SDK 账号、密码、Token、密钥和数据库密码。前端保存配置时，敏感字段只允许写入后端安全存储，不在接口响应中回显明文。

## 事务边界

| 场景 | 事务要求 |
| --- | --- |
| 创建策略信号 | 保存信号和事件通知在同一业务操作内完成 |
| 风控检查 | 风控结果、拒绝原因、审计日志必须一起提交 |
| 创建订单 | `orders`、`risk_checks` 关联和审计日志必须一致 |
| SDK 下单结果 | SDK 返回后更新订单状态，失败也必须记录 |
| 成交回报 | `trades` 写入、订单成交数量更新、持仓/资金同步事件必须幂等 |
| 熔断 | 系统状态、熔断事件、审计日志必须一起提交 |

外部 SDK 调用不应包在长数据库事务中。推荐先写入本地意图状态，再调用 SDK，最后写入结果状态。

## 幂等设计

1. 每笔委托必须生成 `client_order_id`。
2. `orders.client_order_id` 建唯一约束。
3. SDK 成交编号写入 `trades.sdk_trade_id` 并建立唯一约束。
4. 撤单请求使用 `cancel_request_id` 或审计日志事件 ID 做幂等。
5. 后台轮询和 SDK 回调可能重复到达，写入时必须使用 upsert 或唯一约束捕获。

## 后台任务

| 任务 | 频率 | 职责 |
| --- | --- | --- |
| SDK 健康检查 | 5-10 秒 | 检查连接状态，异常时记录事件 |
| 行情超时检测 | 1-5 秒 | 检查关注标的是否长时间无更新 |
| 订单同步 | 3-10 秒 | 查询未完结委托状态 |
| 成交同步 | 3-10 秒 | 拉取增量成交并幂等落库 |
| 资金持仓同步 | 10-30 秒 | 刷新账户资金和持仓 |
| 风控指标刷新 | 5-30 秒 | 计算当日亏损、频率、仓位阈值 |
| 盘前检查 | 交易日前 | 校验 SDK、数据库、配置和策略 |
| 盘后汇总 | 收盘后 | 计算策略表现和风险指标 |

## 错误模型

后端内部错误应包含：

| 字段 | 说明 |
| --- | --- |
| code | 稳定错误码 |
| user_message | 前端可展示的中文信息 |
| debug_message | 内部调试信息，默认不返回前端 |
| module | 发生模块 |
| retryable | 是否可重试 |
| correlation_id | 请求链路 ID |

常用错误码前缀：

| 前缀 | 含义 |
| --- | --- |
| SYS | 系统、配置、数据库 |
| SDK | 同花顺 SDK 连接或返回异常 |
| RISK | 风控拒绝或熔断 |
| ORDER | 委托创建、撤单、同步异常 |
| STRATEGY | 策略加载、运行、信号异常 |
| AI | AI 报告生成异常 |

## 审计日志

所有写操作必须调用 `audit_service`。审计日志至少包含：

1. 时间。
2. 操作类型。
3. 模块。
4. 对象类型和对象 ID。
5. 请求摘要。
6. 结果。
7. 失败原因。
8. correlation_id。

审计日志只追加，不提供普通更新接口。

## 启动恢复

后端启动时必须执行恢复流程：

1. 检查数据库迁移版本。
2. 加载系统配置。
3. 读取最近系统状态。
4. 将未确认订单加入同步队列。
5. 恢复熔断或紧急停止状态，不自动解除。
6. 对上次运行中的策略按配置决定是否恢复，默认不自动交易，需用户确认。
7. 记录系统启动审计日志。

---

## 完整目录文件清单

> 阶段 0 先建空骨架，后续阶段按需填充。`✅` 表示阶段 0 必须有，其余分阶段补。

```text
backend/
  requirements.txt                    ✅ 阶段0
  alembic.ini                         ✅ 阶段0
  pytest.ini                          ✅ 阶段0
  .env.example                        ✅ 阶段0（不提交 .env）
  app/
    __init__.py                       ✅
    main.py                           ✅ FastAPI app + lifespan + 路由注册
    api/
      __init__.py                     ✅
      dependencies.py                 ✅ 依赖注入（db session、correlation_id、当前用户）
      response.py                     ✅ 统一响应（见 api-spec.md §统一响应骨架）
      error_handler.py                ✅ 全局异常处理
      routes/
        __init__.py                   ✅
        health.py                     ✅ 阶段0
        dashboard.py                  ✅ 阶段1
        settings.py                   ✅ 阶段1
        system.py                     ✅ 阶段1（系统状态）
        quotes.py                       阶段2
        klines.py                       阶段2
        strategies.py                   阶段3
        signals.py                      阶段3
        risk.py                         阶段3/5
        orders.py                       阶段4
        trades.py                       阶段4
        positions.py                    阶段4
        assets.py                       阶段4
        history.py                      阶段7
        ai_reports.py                   阶段7
        ai_strategies.py                阶段7 AI 策略定义生成
        logs.py                         阶段1（审计日志、系统事件）
        ws.py                           阶段2（WebSocket）
    core/
      __init__.py
      config.py                        ✅ 阶段0 Settings
      logging.py                       ✅ 阶段0 结构化日志
      correlation.py                   ✅ 阶段0 中间件
      security.py                      ✅ 阶段1 敏感字段加密
      time.py                          ✅ 阶段0 时区工具
      enums.py                         ✅ 阶段1 枚举
    db/
      __init__.py
      session.py                       ✅ 阶段0 engine + sessionmaker
      models/
        __init__.py                    ✅ 导出所有模型供 alembic 发现
        base.py                        ✅ 阶段0 Base + mixin
        account.py                     ✅ 阶段1
        instrument.py                  ✅ 阶段1
        system_config.py               ✅ 阶段1
        system_state.py                ✅ 阶段1
        audit_log.py                   ✅ 阶段1
        system_event.py                ✅ 阶段1
        market_snapshot.py               阶段2
        kline_bar.py                     阶段2
        strategy.py                     阶段3
        strategy_run.py                 阶段3
        strategy_signal.py              阶段3
        risk_check.py                   阶段3
        risk_config.py                  阶段3
        order.py                        阶段4
        trade.py                        阶段4
        position.py                     阶段4
        account_asset.py                阶段4
        ai_report.py                    阶段7
      migrations/
        env.py                         ✅ 阶段0
        script.py.mako                 ✅ 阶段0
        versions/                      ✅ 各迁移文件
    schemas/
      __init__.py
      enums.py                         ✅ 阶段1
      common.py                        ✅ 分页、统一响应 schema
      quote.py                           阶段2
      strategy.py                        阶段3
      signal.py                          阶段3
      risk.py                            阶段3
      order.py                           阶段4
      trade.py                           阶段4
      ai_report.py                       阶段7
    repositories/
      __init__.py
      base.py                          ✅ 阶段0 通用 CRUD 基类
      account_repo.py                    阶段1
      audit_repo.py                      阶段1
      system_event_repo.py               阶段1
      market_repo.py                     阶段2
      strategy_repo.py                   阶段3
      signal_repo.py                     阶段3
      risk_repo.py                       阶段3
      order_repo.py                      阶段4
      trade_repo.py                      阶段4
      position_repo.py                   阶段4
      asset_repo.py                      阶段4
      ai_report_repo.py                  阶段7
    services/
      __init__.py
      system_service.py                  阶段1 系统状态机
      audit_service.py                   阶段1 审计日志
      settings_service.py                阶段1 配置管理
      market_service.py                  阶段2 行情订阅与落库
      strategy_service.py                阶段3 策略生命周期
      risk_service.py                    阶段3/5 风控规则与熔断
      order_service.py                   阶段4 订单状态机
      trade_service.py                   阶段4 交易执行
      metrics_service.py                 阶段7 指标计算
      ai_report_service.py               阶段7 报告生成
      ai_strategy_service.py             阶段7 AI 自然语言策略定义
      strategy_builder_service.py        规则策略构建 / 发布
    sdk/
      __init__.py
      base.py                            阶段2 适配器基类
      models.py                          阶段2 标准模型
      mock_adapter.py                    阶段2 Mock
      stock_adapter.py                   阶段6 真实股票
      futures_adapter.py                 阶段6 真实期货
      factory.py                         阶段2 适配器工厂
    strategies/
      __init__.py
      base.py                            阶段3 Strategy 基类
      context.py                         阶段3 StrategyContext
      registry.py                        阶段3 策略注册表
      samples/
        ma_cross.py                      阶段3 双均线示例
    workers/
      __init__.py
      scheduler.py                       阶段2 APScheduler 初始化
      recovery.py                        阶段5 启动恢复
      sync_jobs.py                       阶段2/4 同步任务
      breaker_monitor.py                 阶段5 熔断监控
    tests/
      __init__.py
      conftest.py                        ✅ 阶段0 pytest fixtures
      test_health.py                     ✅ 阶段0
      test_system_state.py                 阶段1
      test_audit.py                        阶段1
      sdk/
        test_models.py                     阶段2
        test_mock_adapter.py               阶段2
      services/
        test_risk_service.py               阶段3
        test_order_service.py              阶段4
        test_trade_service.py              阶段4
      e2e/
        test_signal_to_trade.py            阶段4
        test_emergency_stop.py             阶段5
        test_restart_recovery.py           阶段5
```

## 配置骨架

> 放 `backend/app/core/config.py`。

```python
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

    # 安全
    config_key: str = ""  # 敏感字段加密密钥（32 字节 base64）

    # AI
    ai_provider: str = ""  # openai / azure / "" 表示规则化
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
```

## 数据库会话骨架

> 放 `backend/app/db/session.py`。

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 依赖：每请求一个 session。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

## Alembic 配置骨架

> `app/db/migrations/env.py` 关键片段：

```python
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.core.config import settings
from app.db.models.base import Base
# 重要：导入所有模型，让 alembic 能发现
from app.db.models import (account, instrument, system_config, system_state,
                           audit_log, system_event, market_snapshot, kline_bar,
                           strategy, strategy_run, strategy_signal,
                           risk_check, risk_config, order, trade,
                           position, account_asset, ai_report)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
```

## 依赖注入骨架

> 放 `backend/app/api/dependencies.py`。

```python
import uuid
from fastapi import Request, Depends
from sqlalchemy.orm import Session
from .db.session import get_db


def get_correlation_id(request: Request) -> str:
    """每请求生成唯一 correlation_id，挂到 request.state。"""
    if not hasattr(request.state, "correlation_id"):
        request.state.correlation_id = f"req_{uuid.uuid4().hex[:16]}"
    return request.state.correlation_id


DbDep = Depends(get_db)
CidDep = Depends(get_correlation_id)
```

## Repository 基类骨架

> 放 `backend/app/repositories/base.py`。

```python
from typing import Generic, TypeVar, Type
from sqlalchemy.orm import Session
from ..db.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: Type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    def get(self, id) -> ModelT | None:
        return self.db.get(self.model, id)

    def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        self.db.flush()
        return obj

    def list(self, *, offset: int = 0, limit: int = 20, filters: dict | None = None):
        q = self.db.query(self.model)
        if filters:
            for k, v in filters.items():
                if v is not None:
                    q = q.filter(getattr(self.model, k) == v)
        return q.offset(offset).limit(limit).all()
```

## Service 骨架示例（audit_service）

> 放 `backend/app/services/audit_service.py`。

```python
import json
from datetime import datetime, timezone
from ..repositories.audit_repo import AuditRepository
from ..api.dependencies import get_correlation_id


class AuditService:
    def __init__(self, db, correlation_id: str = "", operator: str = "local_user"):
        self.repo = AuditRepository(db)
        self.correlation_id = correlation_id
        self.operator = operator

    def log(self, *, action: str, module: str, object_type: str = "", object_id: str = "",
            result: str, reason: str = "", request_summary: dict | None = None):
        self.repo.add(
            action=action, module=module, object_type=object_type, object_id=object_id,
            result=result, reason=reason,
            request_summary=request_summary or {},
            correlation_id=self.correlation_id, operator=self.operator,
            event_time=datetime.now(timezone.utc),
        )
```

## main.py 骨架

> 放 `backend/app/main.py`。

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .core.logging import setup_logging
from .core.correlation import CorrelationIdMiddleware
from .api.routes import health, dashboard, settings as settings_route, system, logs
from .api.error_handler import register_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    # 阶段5：在此调用 workers.recovery.recover_on_startup()
    # 阶段2：在此启动 workers.scheduler
    yield


app = FastAPI(title="Lianghua Quant", version="0.1.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

register_error_handlers(app)

# 路由注册（分阶段逐步加）
app.include_router(health.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(settings_route.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
```

## pytest 配置骨架

> `backend/pytest.ini`：
```ini
[pytest]
testpaths = app/tests
python_files = test_*.py
addopts = -v --tb=short --strict-markers
markers =
    unit: 单元测试
    integration: 集成测试（需要数据库）
    e2e: 端到端测试
```

> `backend/app/tests/conftest.py`：
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models.base import Base
# 导入所有模型
from app.db.models import (account, instrument, system_config, system_state,
                           audit_log, system_event)  # 按阶段补全


@pytest.fixture
def db():
    """内存 SQLite 测试库（仅单测，集成测试用真实 PG）。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
```

## 依赖清单（requirements.txt）

```text
# Web
fastapi==0.111.*
uvicorn[standard]==0.30.*
pydantic==2.*
pydantic-settings==2.*

# 数据库
sqlalchemy==2.*
alembic==1.13.*
psycopg[binary]==3.*

# 调度
apscheduler==3.10.*

# 工具
python-dotenv==1.*
orjson==3.*
cryptography==43.*       # 敏感字段加密

# AI（可选，阶段7）
httpx==0.27.*             # 调用 AI API
openai==1.*               # 若用 OpenAI 兼容接口

# 测试
pytest==8.*
pytest-asyncio==0.23.*
httpx==0.27.*             # 测试客户端
```
