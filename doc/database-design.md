# 数据库设计

## 设计原则

1. PostgreSQL 是交易事实来源，内存状态只做缓存。
2. 订单、成交、持仓、资金、风控和审计必须可追溯。
3. SDK 原始响应保存在 JSONB 字段，便于排查。
4. 审计日志只追加，不更新、不删除。
5. 所有时间字段使用带时区时间 `timestamptz`，业务展示按 Asia/Shanghai。

## 通用字段

建议核心业务表包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | uuid | 主键 |
| created_at | timestamptz | 创建时间 |
| updated_at | timestamptz | 更新时间 |
| raw_payload | jsonb | SDK 或外部原始数据，可为空 |

## 枚举建议

| 枚举 | 值 |
| --- | --- |
| market | `stock`, `futures` |
| order_side | `buy`, `sell` |
| signal_action | `open`, `close`, `reduce`, `increase` |
| price_type | `limit`, `market` |
| order_status | `pending_risk`, `risk_rejected`, `submitting`, `submitted`, `partially_filled`, `filled`, `cancelled`, `failed`, `unknown` |
| system_status | `initializing`, `ready`, `trading`, `paused`, `circuit_breaker`, `emergency_stopped`, `degraded`, `offline` |
| risk_result | `passed`, `rejected`, `warning` |

## 核心表

### accounts

交易账户。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | uuid | 主键 |
| account_no | varchar(64) | 交易账号标识 |
| account_name | varchar(128) | 账户名称 |
| market | market | 股票或期货 |
| broker_name | varchar(128) | 券商或期货公司 |
| sdk_account_ref | varchar(128) | SDK 侧账号引用 |
| status | varchar(32) | active、disabled |

约束：`unique(market, account_no)`。

### instruments

股票、期货合约基础信息。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| symbol | varchar(64) | 标的代码 |
| market | market | 市场类型 |
| name | varchar(128) | 名称 |
| exchange | varchar(32) | 交易所 |
| price_tick | numeric(20, 8) | 最小价格变动 |
| lot_size | numeric(20, 8) | 最小交易单位 |
| is_active | boolean | 是否可用 |

约束：`unique(market, symbol)`。

### market_snapshots

实时行情快照。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| symbol | varchar(64) | 标的 |
| market | market | 市场 |
| quote_time | timestamptz | 行情时间 |
| last_price | numeric(20, 8) | 最新价 |
| change_rate | numeric(12, 6) | 涨跌幅 |
| volume | numeric(24, 8) | 成交量 |
| bid_price | numeric(20, 8) | 买一价 |
| ask_price | numeric(20, 8) | 卖一价 |

索引：`(market, symbol, quote_time desc)`。

### kline_bars

历史 K 线。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| symbol | varchar(64) | 标的 |
| market | market | 市场 |
| interval | varchar(16) | 1m、5m、1d 等 |
| bar_time | timestamptz | K 线时间 |
| open | numeric(20, 8) | 开盘价 |
| high | numeric(20, 8) | 最高价 |
| low | numeric(20, 8) | 最低价 |
| close | numeric(20, 8) | 收盘价 |
| volume | numeric(24, 8) | 成交量 |

约束：`unique(market, symbol, interval, bar_time)`。

### strategies

策略定义。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| strategy_id | varchar(64) | 策略 ID |
| name | varchar(128) | 策略名称 |
| description | text | 说明 |
| enabled | boolean | 是否启用 |
| parameters | jsonb | 参数配置 |
| supported_markets | jsonb | 支持市场 |

约束：`unique(strategy_id)`。

### strategy_runs

策略运行实例。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| strategy_id | varchar(64) | 策略 ID |
| status | varchar(32) | running、stopped、failed |
| started_at | timestamptz | 启动时间 |
| stopped_at | timestamptz | 停止时间 |
| stop_reason | text | 停止原因 |
| metrics | jsonb | 运行指标 |

### strategy_signals

策略信号。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| signal_id | uuid | 信号 ID |
| strategy_id | varchar(64) | 策略 ID |
| symbol | varchar(64) | 标的代码 |
| market | market | 市场 |
| side | order_side | 买卖方向 |
| action | signal_action | 开平仓动作 |
| price_type | price_type | 价格类型 |
| price | numeric(20, 8) | 委托价 |
| quantity | numeric(24, 8) | 数量 |
| reason | text | 触发原因 |
| signal_time | timestamptz | 信号时间 |

索引：`(strategy_id, signal_time desc)`、`(market, symbol, signal_time desc)`。

### risk_checks

风控检查记录。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| check_id | uuid | 检查 ID |
| signal_id | uuid | 策略信号 ID，可为空 |
| client_order_id | varchar(64) | 委托幂等 ID，可为空 |
| result | risk_result | passed、rejected、warning |
| rule_code | varchar(64) | 命中的规则 |
| reason | text | 说明 |
| checked_at | timestamptz | 检查时间 |
| snapshot | jsonb | 检查时使用的资金、持仓、配置快照 |

索引：`(checked_at desc)`、`(client_order_id)`。

### orders

委托订单。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| client_order_id | varchar(64) | 本地幂等 ID |
| sdk_order_id | varchar(128) | SDK 委托编号 |
| account_id | uuid | 账户 ID |
| strategy_id | varchar(64) | 策略 ID，可为空 |
| signal_id | uuid | 信号 ID，可为空 |
| symbol | varchar(64) | 标的 |
| market | market | 市场 |
| side | order_side | 买卖 |
| action | signal_action | 动作 |
| price_type | price_type | 价格类型 |
| price | numeric(20, 8) | 委托价格 |
| quantity | numeric(24, 8) | 委托数量 |
| filled_quantity | numeric(24, 8) | 已成交数量 |
| status | order_status | 订单状态 |
| submitted_at | timestamptz | 提交时间 |
| last_event_at | timestamptz | 最近状态时间 |
| fail_reason | text | 失败原因 |

约束：`unique(client_order_id)`，建议 `unique(market, sdk_order_id)` where `sdk_order_id is not null`。

### trades

成交记录。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| sdk_trade_id | varchar(128) | SDK 成交编号 |
| client_order_id | varchar(64) | 本地订单 ID |
| sdk_order_id | varchar(128) | SDK 委托编号 |
| account_id | uuid | 账户 ID |
| strategy_id | varchar(64) | 策略 ID |
| symbol | varchar(64) | 标的 |
| market | market | 市场 |
| side | order_side | 买卖 |
| price | numeric(20, 8) | 成交价 |
| quantity | numeric(24, 8) | 成交数量 |
| fee | numeric(20, 8) | 手续费 |
| trade_time | timestamptz | 成交时间 |

约束：`unique(market, sdk_trade_id)`。

### positions

持仓快照或当前持仓。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| account_id | uuid | 账户 ID |
| symbol | varchar(64) | 标的 |
| market | market | 市场 |
| direction | varchar(16) | long、short、net |
| quantity | numeric(24, 8) | 当前数量 |
| available_quantity | numeric(24, 8) | 可用数量 |
| avg_cost | numeric(20, 8) | 成本 |
| market_value | numeric(24, 8) | 市值 |
| pnl | numeric(24, 8) | 浮动盈亏 |
| snapshot_time | timestamptz | 快照时间 |

索引：`(account_id, market, symbol, snapshot_time desc)`。

### account_assets

账户资金快照。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| account_id | uuid | 账户 ID |
| total_asset | numeric(24, 8) | 总资产 |
| available_cash | numeric(24, 8) | 可用资金 |
| frozen_cash | numeric(24, 8) | 冻结资金 |
| market_value | numeric(24, 8) | 持仓市值 |
| pnl | numeric(24, 8) | 盈亏 |
| snapshot_time | timestamptz | 快照时间 |

索引：`(account_id, snapshot_time desc)`。

### audit_logs

审计日志。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| event_time | timestamptz | 事件时间 |
| action | varchar(64) | 操作 |
| module | varchar(64) | 模块 |
| object_type | varchar(64) | 对象类型 |
| object_id | varchar(128) | 对象 ID |
| result | varchar(32) | success、failed、rejected |
| reason | text | 原因 |
| request_summary | jsonb | 请求摘要 |
| correlation_id | varchar(64) | 链路 ID |

索引：`(event_time desc)`、`(module, event_time desc)`。

### ai_reports

AI 复盘报告。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| report_id | uuid | 报告 ID |
| range_start | timestamptz | 数据开始 |
| range_end | timestamptz | 数据结束 |
| scope | jsonb | 策略、标的、市场范围 |
| metrics | jsonb | 指标快照 |
| content | text | 报告正文 |
| model_name | varchar(128) | AI 模型 |
| generated_at | timestamptz | 生成时间 |

### system_events

系统事件和异常。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| event_time | timestamptz | 事件时间 |
| severity | varchar(16) | info、warning、error、critical |
| module | varchar(64) | 模块 |
| event_code | varchar(64) | 事件码 |
| message | text | 描述 |
| resolved | boolean | 是否已处理 |
| payload | jsonb | 事件上下文 |

索引：`(event_time desc)`、`(severity, resolved)`。

## 迁移顺序

1. 基础枚举和通用扩展。
2. 账户、标的、策略配置。
3. 行情、K 线。
4. 策略运行和策略信号。
5. 风控、订单、成交。
6. 持仓、资金。
7. 审计日志、系统事件、AI 报告。

## 数据保留策略

| 数据 | 保留策略 |
| --- | --- |
| 订单、成交、持仓、资金、审计日志 | 默认永久保留 |
| 行情快照 | 默认 1 年，可配置 |
| K 线 | 长期保留 |
| AI 报告 | 长期保留 |
| 系统异常日志 | 默认 180 天 |

归档和清理必须写入审计日志。

---

## 完整 DDL（可直接执行）

> 以下 DDL 按"迁移顺序"组织，每个 `-- 迁移 N` 块对应一个 Alembic 迁移文件。建库后可整体执行一遍，也可拆成多个迁移逐步上。
>
> 约定：
> - 所有主键 `id` 用 `uuid`，默认 `gen_random_uuid()`（PostgreSQL 13+ 内置，需 `pgcrypto` 或 PG13+ 默认开启）。
> - 所有时间用 `timestamptz`，应用层按 `Asia/Shanghai` 展示。
> - 金额/数量用 `numeric`，**禁止 float**。
> - `raw_payload` 用 `jsonb`，存 SDK 原始返回。

### 迁移 1：枚举类型

```sql
-- 市场类型
CREATE TYPE market_type AS ENUM ('stock', 'futures');

-- 买卖方向
CREATE TYPE order_side_type AS ENUM ('buy', 'sell');

-- 开平仓动作
CREATE TYPE signal_action_type AS ENUM ('open', 'close', 'reduce', 'increase');

-- 价格类型
CREATE TYPE price_type AS ENUM ('limit', 'market');

-- 订单状态
CREATE TYPE order_status_type AS ENUM (
  'pending_risk', 'risk_rejected', 'submitting', 'submitted',
  'partially_filled', 'filled', 'cancelled', 'failed', 'unknown'
);

-- 系统状态
CREATE TYPE system_status_type AS ENUM (
  'initializing', 'ready', 'trading', 'paused',
  'circuit_breaker', 'emergency_stopped', 'degraded', 'offline'
);

-- 风控结果
CREATE TYPE risk_result_type AS ENUM ('passed', 'rejected', 'warning');

-- 严重程度
CREATE TYPE severity_type AS ENUM ('info', 'warning', 'error', 'critical');

-- 策略运行状态
CREATE TYPE strategy_run_status_type AS ENUM ('running', 'paused', 'stopped', 'failed', 'pending_confirm');

-- 账户状态
CREATE TYPE account_status_type AS ENUM ('active', 'disabled');
```

### 迁移 2：账户、标的、系统配置

```sql
-- 交易账户
CREATE TABLE accounts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_no      varchar(64)  NOT NULL,
  account_name    varchar(128) NOT NULL DEFAULT '',
  market          market_type  NOT NULL,
  broker_name     varchar(128) NOT NULL DEFAULT '',
  sdk_account_ref varchar(128) NOT NULL DEFAULT '',
  status          account_status_type NOT NULL DEFAULT 'active',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  raw_payload     jsonb,
  CONSTRAINT uk_accounts_market_no UNIQUE (market, account_no)
);
COMMENT ON TABLE accounts IS '交易账户';

-- 标的基础信息
CREATE TABLE instruments (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol       varchar(64)    NOT NULL,
  market       market_type    NOT NULL,
  name         varchar(128)   NOT NULL DEFAULT '',
  exchange     varchar(32)    NOT NULL DEFAULT '',
  price_tick   numeric(20, 8) NOT NULL DEFAULT 0,
  lot_size     numeric(20, 8) NOT NULL DEFAULT 1,
  multiplier   numeric(20, 8) NOT NULL DEFAULT 1,  -- 合约乘数（期货）
  is_active    boolean        NOT NULL DEFAULT true,
  created_at   timestamptz    NOT NULL DEFAULT now(),
  updated_at   timestamptz    NOT NULL DEFAULT now(),
  raw_payload  jsonb,
  CONSTRAINT uk_instruments_market_symbol UNIQUE (market, symbol)
);
COMMENT ON TABLE instruments IS '股票/期货合约基础信息';

-- 系统配置（敏感字段加密后存 encrypted_value）
CREATE TABLE system_configs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  config_key      varchar(128) NOT NULL,
  config_value    text         NOT NULL DEFAULT '',   -- 非敏感明文
  encrypted_value bytea,                               -- 敏感字段加密后
  is_sensitive    boolean      NOT NULL DEFAULT false,
  description     text         NOT NULL DEFAULT '',
  updated_at      timestamptz  NOT NULL DEFAULT now(),
  CONSTRAINT uk_system_configs_key UNIQUE (config_key)
);
COMMENT ON TABLE system_configs IS '系统配置，敏感字段加密存储';

-- 系统当前状态（单行表）
CREATE TABLE system_state (
  id              smallint PRIMARY KEY DEFAULT 1,
  status          system_status_type NOT NULL DEFAULT 'initializing',
  status_reason   text NOT NULL DEFAULT '',
  status_since    timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_system_state_singleton CHECK (id = 1)
);
INSERT INTO system_state (id) VALUES (1);
```

### 迁移 3：行情、K 线

```sql
-- 行情快照
CREATE TABLE market_snapshots (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol        varchar(64)    NOT NULL,
  market        market_type    NOT NULL,
  quote_time    timestamptz    NOT NULL,
  last_price    numeric(20, 8) NOT NULL,
  change_rate   numeric(12, 6) NOT NULL DEFAULT 0,
  volume        numeric(24, 8) NOT NULL DEFAULT 0,
  bid_price     numeric(20, 8),
  ask_price     numeric(20, 8),
  bid_volume    numeric(24, 8),
  ask_volume    numeric(24, 8),
  raw_payload   jsonb,
  created_at    timestamptz    NOT NULL DEFAULT now()
);
CREATE INDEX idx_market_snapshots_lookup ON market_snapshots (market, symbol, quote_time DESC);
COMMENT ON TABLE market_snapshots IS '实时行情快照';

-- 历史 K 线
CREATE TABLE kline_bars (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol       varchar(64)    NOT NULL,
  market       market_type    NOT NULL,
  interval     varchar(16)    NOT NULL,  -- 1m/5m/1d 等
  bar_time     timestamptz    NOT NULL,
  open         numeric(20, 8) NOT NULL,
  high         numeric(20, 8) NOT NULL,
  low          numeric(20, 8) NOT NULL,
  close        numeric(20, 8) NOT NULL,
  volume       numeric(24, 8) NOT NULL DEFAULT 0,
  raw_payload  jsonb,
  created_at   timestamptz    NOT NULL DEFAULT now(),
  CONSTRAINT uk_kline_bars UNIQUE (market, symbol, interval, bar_time)
);
CREATE INDEX idx_kline_bars_lookup ON kline_bars (market, symbol, interval, bar_time DESC);
COMMENT ON TABLE kline_bars IS '历史 K 线';
```

### 迁移 4：策略

```sql
-- 策略定义
CREATE TABLE strategies (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  strategy_id       varchar(64)  NOT NULL,
  name              varchar(128) NOT NULL,
  description       text         NOT NULL DEFAULT '',
  enabled           boolean      NOT NULL DEFAULT false,
  parameters        jsonb        NOT NULL DEFAULT '{}'::jsonb,
  supported_markets jsonb        NOT NULL DEFAULT '[]'::jsonb,
  created_at        timestamptz  NOT NULL DEFAULT now(),
  updated_at        timestamptz  NOT NULL DEFAULT now(),
  CONSTRAINT uk_strategies_id UNIQUE (strategy_id)
);
COMMENT ON TABLE strategies IS '策略定义';

-- 策略运行实例
CREATE TABLE strategy_runs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  strategy_id   varchar(64) NOT NULL,
  status        strategy_run_status_type NOT NULL DEFAULT 'pending_confirm',
  started_at    timestamptz,
  stopped_at    timestamptz,
  stop_reason   text NOT NULL DEFAULT '',
  parameters    jsonb NOT NULL DEFAULT '{}'::jsonb,
  metrics       jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_strategy_runs_strategy ON strategy_runs (strategy_id, started_at DESC);
COMMENT ON TABLE strategy_runs IS '策略运行实例';

-- 策略信号
CREATE TABLE strategy_signals (
  signal_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  strategy_id   varchar(64)       NOT NULL,
  symbol        varchar(64)       NOT NULL,
  market        market_type       NOT NULL,
  side          order_side_type   NOT NULL,
  action        signal_action_type NOT NULL,
  price_type    price_type        NOT NULL,
  price         numeric(20, 8)    NOT NULL DEFAULT 0,
  quantity      numeric(24, 8)    NOT NULL,
  reason        text              NOT NULL DEFAULT '',
  signal_time   timestamptz       NOT NULL,
  metadata      jsonb             NOT NULL DEFAULT '{}'::jsonb,
  created_at    timestamptz       NOT NULL DEFAULT now()
);
CREATE INDEX idx_signals_strategy ON strategy_signals (strategy_id, signal_time DESC);
CREATE INDEX idx_signals_symbol   ON strategy_signals (market, symbol, signal_time DESC);
COMMENT ON TABLE strategy_signals IS '策略信号';
```

### 迁移 5：风控、订单、成交

```sql
-- 风控配置（单行表）
CREATE TABLE risk_configs (
  id                                   smallint PRIMARY KEY DEFAULT 1,
  allowed_symbols                      jsonb NOT NULL DEFAULT '[]'::jsonb,
  blocked_symbols                      jsonb NOT NULL DEFAULT '[]'::jsonb,
  trading_sessions                     jsonb NOT NULL DEFAULT '[]'::jsonb,
  max_order_amount                     numeric(24, 8) NOT NULL DEFAULT 1000000,
  max_order_quantity                   numeric(24, 8) NOT NULL DEFAULT 10000,
  max_symbol_position                  numeric(24, 8) NOT NULL DEFAULT 100000,
  max_total_position                   numeric(24, 8) NOT NULL DEFAULT 1000000,
  daily_loss_limit                     numeric(24, 8) NOT NULL DEFAULT 50000,
  daily_trade_count_limit              int   NOT NULL DEFAULT 100,
  sdk_disconnect_timeout_seconds       int   NOT NULL DEFAULT 30,
  quote_stale_timeout_seconds          int   NOT NULL DEFAULT 10,
  consecutive_order_fail_limit         int   NOT NULL DEFAULT 5,
  duplicate_signal_window_seconds      int   NOT NULL DEFAULT 3,
  auto_cancel_on_breaker               boolean NOT NULL DEFAULT true,
  updated_at                           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_risk_configs_singleton CHECK (id = 1)
);
INSERT INTO risk_configs (id) VALUES (1);

-- 风控检查记录
CREATE TABLE risk_checks (
  check_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_id        uuid,
  client_order_id  varchar(64),
  result           risk_result_type NOT NULL,
  rule_code        varchar(64) NOT NULL DEFAULT '',
  reason           text NOT NULL DEFAULT '',
  checked_at       timestamptz NOT NULL DEFAULT now(),
  snapshot         jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_risk_checks_time     ON risk_checks (checked_at DESC);
CREATE INDEX idx_risk_checks_order    ON risk_checks (client_order_id);
CREATE INDEX idx_risk_checks_signal   ON risk_checks (signal_id);
COMMENT ON TABLE risk_checks IS '风控检查记录';

-- 委托订单
CREATE TABLE orders (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_order_id   varchar(64)        NOT NULL,
  sdk_order_id      varchar(128),
  account_id        uuid               NOT NULL REFERENCES accounts(id),
  strategy_id       varchar(64),
  signal_id         uuid,
  symbol            varchar(64)        NOT NULL,
  market            market_type        NOT NULL,
  side              order_side_type    NOT NULL,
  action            signal_action_type NOT NULL,
  price_type        price_type         NOT NULL,
  price             numeric(20, 8)     NOT NULL DEFAULT 0,
  quantity          numeric(24, 8)     NOT NULL,
  filled_quantity   numeric(24, 8)     NOT NULL DEFAULT 0,
  status            order_status_type  NOT NULL DEFAULT 'pending_risk',
  submitted_at      timestamptz,
  last_event_at     timestamptz,
  fail_reason       text NOT NULL DEFAULT '',
  raw_payload       jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uk_orders_client_id UNIQUE (client_order_id)
);
CREATE UNIQUE INDEX uk_orders_sdk_id ON orders (market, sdk_order_id) WHERE sdk_order_id IS NOT NULL;
CREATE INDEX idx_orders_status     ON orders (status, created_at DESC);
CREATE INDEX idx_orders_strategy   ON orders (strategy_id, created_at DESC);
CREATE INDEX idx_orders_symbol     ON orders (market, symbol, created_at DESC);
COMMENT ON TABLE orders IS '委托订单';

-- 成交记录
CREATE TABLE trades (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sdk_trade_id     varchar(128)     NOT NULL,
  client_order_id  varchar(64)      NOT NULL,
  sdk_order_id     varchar(128),
  account_id       uuid             NOT NULL REFERENCES accounts(id),
  strategy_id      varchar(64),
  symbol           varchar(64)      NOT NULL,
  market           market_type      NOT NULL,
  side             order_side_type  NOT NULL,
  price            numeric(20, 8)   NOT NULL,
  quantity         numeric(24, 8)   NOT NULL,
  fee              numeric(20, 8)   NOT NULL DEFAULT 0,
  trade_time       timestamptz      NOT NULL,
  raw_payload      jsonb,
  created_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uk_trades_sdk_id UNIQUE (market, sdk_trade_id)
);
CREATE INDEX idx_trades_order   ON trades (client_order_id);
CREATE INDEX idx_trades_time    ON trades (trade_time DESC);
CREATE INDEX idx_trades_symbol  ON trades (market, symbol, trade_time DESC);
COMMENT ON TABLE trades IS '成交记录';
```

### 迁移 6：持仓、资金

```sql
-- 持仓快照（每次同步追加一行，最新行即当前持仓）
CREATE TABLE positions (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id          uuid             NOT NULL REFERENCES accounts(id),
  symbol              varchar(64)      NOT NULL,
  market              market_type      NOT NULL,
  direction           varchar(16)      NOT NULL DEFAULT 'net',  -- long/short/net
  quantity            numeric(24, 8)   NOT NULL DEFAULT 0,
  available_quantity  numeric(24, 8)   NOT NULL DEFAULT 0,
  avg_cost            numeric(20, 8)   NOT NULL DEFAULT 0,
  market_value        numeric(24, 8)   NOT NULL DEFAULT 0,
  pnl                 numeric(24, 8)   NOT NULL DEFAULT 0,
  snapshot_time       timestamptz      NOT NULL,
  raw_payload         jsonb,
  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_positions_lookup ON positions (account_id, market, symbol, snapshot_time DESC);
COMMENT ON TABLE positions IS '持仓快照';

-- 账户资金快照
CREATE TABLE account_assets (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id      uuid             NOT NULL REFERENCES accounts(id),
  total_asset     numeric(24, 8)   NOT NULL DEFAULT 0,
  available_cash  numeric(24, 8)   NOT NULL DEFAULT 0,
  frozen_cash     numeric(24, 8)   NOT NULL DEFAULT 0,
  market_value    numeric(24, 8)   NOT NULL DEFAULT 0,
  pnl             numeric(24, 8)   NOT NULL DEFAULT 0,
  snapshot_time   timestamptz      NOT NULL,
  raw_payload     jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_assets_lookup ON account_assets (account_id, snapshot_time DESC);
COMMENT ON TABLE account_assets IS '账户资金快照';
```

### 迁移 7：审计、系统事件、AI 报告

```sql
-- 审计日志（只追加）
CREATE TABLE audit_logs (
  id               bigserial PRIMARY KEY,
  event_time       timestamptz NOT NULL DEFAULT now(),
  action           varchar(64) NOT NULL,
  module           varchar(64) NOT NULL,
  object_type      varchar(64) NOT NULL DEFAULT '',
  object_id        varchar(128) NOT NULL DEFAULT '',
  result           varchar(32) NOT NULL,  -- success/failed/rejected
  reason           text NOT NULL DEFAULT '',
  request_summary  jsonb NOT NULL DEFAULT '{}'::jsonb,
  correlation_id   varchar(64) NOT NULL DEFAULT '',
  operator         varchar(64) NOT NULL DEFAULT 'local_user'
);
CREATE INDEX idx_audit_time   ON audit_logs (event_time DESC);
CREATE INDEX idx_audit_module ON audit_logs (module, event_time DESC);
CREATE INDEX idx_audit_object ON audit_logs (object_type, object_id);
COMMENT ON TABLE audit_logs IS '审计日志，只追加不修改';

-- 系统事件
CREATE TABLE system_events (
  id           bigserial PRIMARY KEY,
  event_time   timestamptz   NOT NULL DEFAULT now(),
  severity     severity_type NOT NULL DEFAULT 'info',
  module       varchar(64)   NOT NULL,
  event_code   varchar(64)   NOT NULL,
  message      text          NOT NULL DEFAULT '',
  resolved     boolean       NOT NULL DEFAULT false,
  payload      jsonb         NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_events_time     ON system_events (event_time DESC);
CREATE INDEX idx_events_severity ON system_events (severity, resolved);
COMMENT ON TABLE system_events IS '系统事件和异常';

-- AI 报告
CREATE TABLE ai_reports (
  report_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  range_start   timestamptz NOT NULL,
  range_end     timestamptz NOT NULL,
  scope         jsonb NOT NULL DEFAULT '{}'::jsonb,
  metrics       jsonb NOT NULL DEFAULT '{}'::jsonb,
  content       text NOT NULL,
  content_format varchar(16) NOT NULL DEFAULT 'markdown',
  model_name    varchar(128) NOT NULL DEFAULT 'rule_based',
  generated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_ai_reports_time ON ai_reports (range_start DESC);
COMMENT ON TABLE ai_reports IS 'AI 复盘报告';
```

### 迁移 8：updated_at 自动更新触发器

```sql
-- 通用触发器函数：自动更新 updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 为所有有 updated_at 的表挂触发器
CREATE TRIGGER trg_accounts_updated   BEFORE UPDATE ON accounts   FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_instruments_updated BEFORE UPDATE ON instruments FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_system_configs_updated BEFORE UPDATE ON system_configs FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_system_state_updated   BEFORE UPDATE ON system_state   FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_strategies_updated     BEFORE UPDATE ON strategies     FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_strategy_runs_updated  BEFORE UPDATE ON strategy_runs  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_risk_configs_updated   BEFORE UPDATE ON risk_configs   FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_orders_updated         BEFORE UPDATE ON orders         FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

## 通用基类骨架（SQLAlchemy）

> 放 `backend/app/db/models/base.py`。所有业务模型继承 `Base`，需要通用字段的继承 `TimestampMixin`。

```python
import uuid
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """通用时间戳 mixin。"""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RawPayloadMixin:
    """SDK 原始返回 mixin。"""
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class UUIDPrimaryKey:
    """UUID 主键 mixin。"""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
```

## 模型示例（orders 表）

```python
# backend/app/db/models/order.py
import uuid
from datetime import datetime
from sqlalchemy import String, Numeric, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin, RawPayloadMixin
from ...schemas.enums import OrderStatus, Market, OrderSide, SignalAction, PriceType


class Order(Base, TimestampMixin, RawPayloadMixin):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    sdk_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[Market] = mapped_column(Enum(Market), nullable=False)
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide), nullable=False)
    action: Mapped[SignalAction] = mapped_column(Enum(SignalAction), nullable=False)
    price_type: Mapped[PriceType] = mapped_column(Enum(PriceType), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=0)
    quantity: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    filled_quantity: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, default=0)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING_RISK)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fail_reason: Mapped[str] = mapped_column(String, nullable=False, default="")
```

> 其余表模型按相同模式实现，字段与 DDL 严格对齐。完整模型文件清单见 `backend-design.md` §模型文件清单。

## 数据归档脚本骨架

```sql
-- 归档 180 天前的系统事件（保留 critical）
-- 建议封装为后端定时任务，执行后写审计日志
DELETE FROM system_events
WHERE event_time < now() - interval '180 days'
  AND severity <> 'critical';

-- 归档 1 年前行情快照（可配置）
DELETE FROM market_snapshots
WHERE quote_time < now() - interval '1 year';
```
