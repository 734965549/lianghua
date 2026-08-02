# MVP 开发路线（实施主线）

> 本文档是**对照实施的执行主线**。每个阶段拆成可勾选的小步骤，每步都给出：**做什么 / 命令 / 关键代码骨架 / 验证方法**。
> 各设计文档（`database-design.md`、`api-spec.md`、`backend-design.md` 等）是配套的"可查可复制"参考库，遇到字段、DDL、接口出入参等细节去对应文档查。
>
> 阅读约定：
> - 命令默认在 Git Bash（Windows）下执行；PowerShell 命令会单独标注 `pwsh`。
> - 所有路径相对项目根目录 `D:\E盘\BaiduNetdiskDownload\go\lianghua`。
> - `- [ ]` 表示待办，做完改成 `- [x]`。
> - "验证"小节给出**怎么确认这步真做完了**，照着跑一遍即可。

---

## 全局约定（动工前先定）

- [x] 确认 Git 仓库已初始化：`git status`。若未初始化：`git init && git branch -m main`。
- [x] 新增项目根 `.gitignore`（内容见 [附录 A](#附录-a-推荐-gitignore)）。
- [x] 新增 `.env.example`（内容见 `deployment-guide.md` 的环境变量表，**不要提交 `.env`**）。
- [x] 确认 Python 版本：`python --version` 必须 ≥ 3.11。否则安装 3.11+。
- [x] 确认 Node 版本：`node --version` LTS（≥ 20）。
- [x] 确认 PostgreSQL 可用：Docker Compose `postgres:17.10`（`lianghua-pg`）

---

## 阶段 0：开发准备

**目标**：建立可开发、可测试、可运行的项目骨架。结束时 `backend/`、`frontend/` 两个空架子能跑起来，数据库能连上，迁移能执行。

### 0.1 后端工程骨架

- [x] 创建后端目录与虚拟环境
- [x] 写 `backend/requirements.txt` 并安装依赖
- [x] 按目录结构创建空文件骨架
- [x] 写 `app/main.py` + `/api/health`
- [x] **验证**：`http://127.0.0.1:8000/api/health` 返回统一响应

### 0.2 前端工程骨架

- [x] 用 Vite 初始化 React + TS，安装 antd / echarts / react-query / dayjs
- [x] `vite.config.ts` 代理 `/api` → `8000`
- [x] **验证**：`npm run dev`，页面展示健康检查状态卡片

### 0.3 PostgreSQL 数据库与连接

- [x] 用 Docker Compose 起库（`docker compose up -d`，镜像 `postgres:17.10`，用户/库 `lianghua`）
- [x] 在后端 `.env` / `.env.example` 设置 `LIANGHUA_DATABASE_URL`
- [x] **验证**：容器内 `psql` / 健康检查 `database: connected`

### 0.4 Alembic 迁移初始化

- [x] 初始化 Alembic（`alembic.ini` + `env.py` + 空迁移 `0001_init`）
- [x] `sqlalchemy.url` 留空，由 Settings 读取
- [x] `app/db/models/base.py` Base + mixin
- [x] **验证**：`alembic upgrade head` 无报错，可见 `alembic_version` 表

### 0.5 统一响应与审计日志基础

- [x] `app/api/response.py` 统一响应 + `BizError`
- [x] `app/core/config.py` pydantic-settings
- [x] `app/core/logging.py` JSON 日志 + `CorrelationIdMiddleware`
- [x] **验证**：访问不存在接口返回 `{success, data, error, correlation_id}`

### 阶段 0 完成标志

- [x] `backend` 与 `frontend` 都能本地启动。
- [x] `/api/health` 可访问并返回统一响应。
- [x] PostgreSQL 连接成功，Alembic 迁移可执行。
- [ ] Git 提交：`git add -A && git commit -m "phase 0: project skeleton"`。

---

## 阶段 1：数据与系统骨架

**目标**：完成主数据模型、系统状态、审计日志、系统事件、设置页 API 和前端主布局。结束时前端能看到系统状态、能改配置、配置变更进审计日志。

### 1.1 核心数据表 DDL

- [x] 迁移 `0002_phase1_core`：枚举 + `accounts`/`instruments`/`system_configs`/`system_state`/`audit_logs`/`system_events`
- [x] **验证**：`alembic upgrade head` 成功，`\dt` 可见上述表

### 1.2 SQLAlchemy 模型

- [x] 模型文件齐全，字段与 DDL 对齐
- [x] env.py 导入模型供 Alembic 发现

### 1.3 系统状态机

- [x] `SystemStateService` 合法迁移矩阵 + 审计/事件落库
- [x] 启动时 `initializing`/`offline` → `ready`；熔断/紧急停止不自动解除
- [x] **验证**：`test_system_state.py` 通过

### 1.4 审计日志服务

- [x] `AuditService` + `audit_repo` 只追加 + 分页查询
- [x] **验证**：`test_audit.py` 通过

### 1.5 设置页 API

- [x] GET/PUT `/api/settings`，POST `test-database` / `test-sdk`
- [x] GET `/api/dashboard`、`/api/system/status`、`/api/logs/*`
- [x] **验证**：PUT 配置后 `audit_logs` 新增记录

### 1.6 前端主布局与系统设置页

- [x] 路由 + MainLayout + SystemStatusBar
- [x] Dashboard / Settings / Logs；其余页面占位
- [x] **验证**：前端 build 通过；页面可调用后端

### 阶段 1 完成标志

- [x] 数据库主表已建好，模型与 DDL 一致。
- [x] 系统状态机能正确迁移。
- [x] 配置修改写入审计日志。
- [x] 前端仪表盘和设置页可用。
- [ ] Git 提交：`phase 1: data and system skeleton`。

---

## 阶段 2：Mock SDK 与行情

**目标**：不依赖真实 SDK 跑通行情订阅、行情落库、K 线查询、行情停更检测。结束时前端行情看板能看到 Mock 推送的实时价格。

### 2.1 SDK 标准模型与基类

- [x] `app/sdk/models.py` 标准模型 + `app/sdk/base.py` 适配器基类/错误体系
- [x] **验证**：`test_models.py` 通过

### 2.2 Mock 适配器

- [x] `MockTradingAdapter`（daemon Thread 推送行情，可 inject 失败/断线，`stop_quotes`）
- [x] `factory.py` + `manager.py`
- [x] **验证**：`test_mock_adapter.py` 通过

### 2.3 行情服务与落库

- [x] 迁移 `0003_market_tables`：`market_snapshots` / `kline_bars`
- [x] `MarketService`：订阅、落库、K 线、WS `quote.update`
- [x] API：`/quotes`、`/quotes/{market}/{symbol}`、`/quotes/subscriptions`、`/klines`、`/ws/events`
- [x] **验证**：行情接口有数据，快照表持续写入

### 2.4 行情停更检测

- [x] `check_quote_stale`（3s）+ APScheduler；超 10s 写 `quote_stale` 并降级
- [x] **验证**：单测覆盖 `stop_quotes` / 集成落库

### 2.5 前端行情看板

- [x] `Market.tsx` + `QuoteTable` + `KlineChart` + WS 客户端
- [x] 停更行标黄告警；Vite 代理开启 `ws: true`
- [x] **验证**：前端 build 通过

### 阶段 2 完成标志

- [x] Mock 行情实时推送到前端。
- [x] 行情快照落库。
- [x] 行情停更触发系统事件。
- [ ] Git 提交：`phase 2: mock sdk and market`。

---

## 阶段 3：策略与风控

**目标**：策略信号进入强制风控流程，风控通过/拒绝都有记录，风控拒绝不会调用 SDK。

### 3.1 策略表与模型

- [x] 迁移 `0004_strategy_risk`：strategies / strategy_runs / strategy_signals / risk_configs / risk_checks
- [x] SQLAlchemy 模型 + seed `ma_cross`

### 3.2 策略基类与上下文

- [x] Strategy / StrategyContext / registry
- [x] Context 仅只读 + submit_signal

### 3.3 示例 Mock 策略

- [x] `ma_cross` 双均线（金叉买/死叉卖）
- [x] **验证**：`test_ma_cross.py` 通过

### 3.4 策略引擎与生命周期

- [x] StrategyService 启停、行情 dispatch、信号落库→风控（阶段3不下单）
- [x] API：strategies / signals
- [x] **验证**：start 后 `strategy_runs=running`，系统 `ready→trading`

### 3.5 风控配置与规则

- [x] 11 条规则短路 + RiskService + risk API（含紧急停止/恢复）
- [x] **验证**：黑名单/状态拒绝；拒绝路径不调用 `place_order`

### 3.6 前端策略与风控页

- [x] Strategies / RiskSettings / RiskCheckDrawer
- [x] **验证**：前端 build 通过

### 阶段 3 完成标志

- [x] 策略信号可在前端查看。
- [x] 风控通过/拒绝都有 `risk_checks` 记录。
- [x] 风控拒绝不调用 SDK `place_order`（用 Mock spy 验证）。
- [ ] Git 提交：`phase 3: strategy and risk`。

---

## 阶段 4：订单、成交与交易执行

**目标**：通过 Mock SDK 跑通"信号→风控→下单→成交→持仓/资金同步"自动交易闭环。

### 4.1 订单与成交表

- [x] 迁移 `0005_orders_trades`：orders/trades/positions/account_assets + 默认 Mock 账户
- [x] SQLAlchemy 模型与仓储

### 4.2 订单服务与状态机

- [x] OrderService：create_from_signal / 状态机 / on_order_update / WS
- [x] **验证**：单测覆盖合法迁移与 filled/failed

### 4.3 交易执行服务

- [x] TradeService：submit / cancel / on_trade_update（幂等）
- [x] 策略 `_on_signal` 风控通过后接单；SDK 回调已注册
- [x] **验证**：成交幂等单测通过

### 4.4 持仓与资金同步

- [x] sync_positions / sync_assets / sync_orders_trades 调度
- [x] **验证**：资金快照可落库（Mock 持仓可为空）

### 4.5 API

- [x] `/orders` `/trades` `/positions` `/assets` + 撤单

### 4.6 前端交易与持仓页

- [x] Trading / Positions + OrderTable / TradeTable / AssetCurveChart
- [x] WS 增量刷新委托与成交

### 阶段 4 完成标志

- [x] 策略信号通过风控后能生成订单。
- [x] 订单、成交、持仓、资金可落库。
- [x] 前端实时显示委托和成交变化。
- [x] 重复成交回报不重复入库。
- [ ] Git 提交：`phase 4: order and trade execution`。

---

## 阶段 5：熔断、恢复与异常处理

**目标**：完成实盘前必须具备的安全控制：一键停止、熔断、自动撤单、重启恢复、未知订单处理。

### 5.1 一键停止与熔断

- [x] 在 `risk_service.py` 加：
  - `emergency_stop(reason, cancel_open_orders)`：状态→`emergency_stopped`，可选撤未成交委托，写审计。
  - `trigger_breaker(reason)`：状态→`circuit_breaker`，写 `system_events` + 审计。
  - 熔断条件检查任务 `check_breaker_conditions`（5-30 秒）：当日亏损、SDK 断线、连续下单失败、行情停更、订单状态不一致。
- [x] API：`POST /api/risk/emergency-stop`、`POST /api/risk/resume`，出入参见 `api-spec.md` §风控。
- [x] **验证**：调 `emergency-stop` 后，再触发任何信号都被 `RISK_SYSTEM_STOPPED` 拒绝。

### 5.2 恢复交易

- [x] `resume(reason)`：校验恢复前置条件（见 `risk-control-design.md` §恢复流程），全部满足才解除熔断/紧急停止，写审计。
- [x] **验证**：单测覆盖：SDK 未连接时恢复被拒；未知订单未处理时恢复被拒；全部满足时恢复成功。

### 5.3 重启恢复

- [x] 在 `app/workers/recovery.py` 实现 `recover_on_startup()`：
  1. 检查迁移版本。
  2. 加载系统配置。
  3. 读最近系统状态，若为 `circuit_breaker`/`emergency_stopped` 则**保持**，不自动解除。
  4. 把未完结订单（`submitting`/`submitted`/`partially_filled`/`unknown`）加入同步队列。
  5. 上次运行中的策略**默认不自动启动**，标记 `pending_confirm`，需用户前端确认。
- [x] 在 `app/main.py` 的 `lifespan` 启动钩子里调用 `recover_on_startup()`。
- [x] **验证**：构造一笔 `submitting` 订单 → 停后端 → 重启 → 该订单进入同步队列；熔断状态保持。

### 5.4 未知订单处理

- [x] `sync_orders_trades` 任务遇到 SDK 返回状态无法映射时，订单状态置 `unknown`，写 `system_events`，前端醒目提示。
- [x] 恢复交易前必须处理或确认所有 `unknown` 订单。
- [x] **验证**：Mock 返回未知状态码，订单变 `unknown`，前端红色提示。

### 阶段 5 完成标志

- [x] 一键停止后禁止新委托。
- [x] 熔断状态不因重启自动解除。
- [x] 未知订单提示人工检查。
- [ ] Git 提交：`phase 5: breaker and recovery`。

---

## 阶段 6：真实 SDK 接入

**目标**：替换 Mock，接入同花顺股票/期货 SDK。**前置条件**：阶段 0-5 全部完成且 Mock 端到端用例通过；`open-questions.md` 中 SDK 相关问题已确认。

### 6.1 SDK 调研与样例

- [ ] 拿到同花顺股票 SDK 与期货 SDK 的文档、授权、调用示例。（**待 SDK 到位**）
- [x] 在 `doc/` 新增 `sdk-notes-stock.md` 与 `sdk-notes-futures.md`，记录：版本、绑定语言、连接方式、回调机制、字段对照、限制。（TBD 项已占位）
- [x] 用最小脚本验证 SDK 能连接、查账户、查持仓（不下单）。（`scripts/sdk_smoke_query.py`，`LIANGHUA_SDK_DRIVER=sim`）

### 6.2 股票适配器

- [x] 在 `app/sdk/stock_adapter.py` 实现 `StockTradingAdapter`：（骨架 + Simulated 驱动映射；原生待填）
  - 每个统一接口方法映射 SDK 实际调用。
  - 字段映射表见 `sdk-adapter-design.md` §字段映射原则，差异字段进 `metadata`/`raw_payload`。
  - 错误转标准错误码。
- [x] **验证**：跑 `app/tests/sdk/test_stock_adapter.py`（与 Mock 同一套测试接口），行为一致。

### 6.3 期货适配器

- [x] 在 `app/sdk/futures_adapter.py` 实现 `FuturesTradingAdapter`，注意开平/平今/平昨/投机套保字段通过 `action` + `metadata` 表达。
- [x] **验证**：同上（`test_futures_adapter.py`）。

### 6.4 双通道同步验证

- [x] 验证回调和轮询双通道都能同步订单/成交，幂等不重复。（`test_dual_channel_sync.py` + sim）
- [x] 小规模查询测试：连接、查账户、查持仓、查委托、查成交。

### 6.5 小额实盘前验收

- [x] 按 `testing-acceptance.md` §上线前检查清单 逐项打勾。（工程项；真实资金项待 SDK）
- [x] 用小额资金手动下一笔限价单并立即撤单，验证全链路。（`scripts/sdk_small_order_cancel.py`，sim 可跑通；原生安全退出）
- [ ] **验证**：所有检查项通过，审计日志完整。（**真实 SDK 待补**）

### 阶段 6 完成标志

- [x] 真实 SDK 连接状态可展示。（health / test-sdk 已接 real；原生连接待 SDK）
- [x] 真实账户、持仓、委托、成交可同步。（sim 驱动已验证映射与双通道）
- [ ] 小额实盘验收清单通过。（**待原生 SDK**）
- [ ] Git 提交：`phase 6: real sdk integration`。

---

## 阶段 7：AI 复盘与报表

**目标**：完成盘后分析能力。先做规则化报告，再接 AI 模型。

### 7.1 历史交易查询与导出

- [x] `app/api/routes/history.py`：`GET /api/history/orders`、`GET /api/history/trades`，支持按日期/标的/策略/状态筛选，`Accept: text/csv` 时返回 CSV。
- [x] 前端 `pages/History.tsx`：筛选表单 + 表格 + 导出按钮 + 单笔交易链路抽屉（信号→风控→委托→成交→审计）。

### 7.2 指标计算

- [x] 在 `app/services/metrics_service.py` 实现确定性指标计算：`total_pnl`、`win_rate`、`profit_loss_ratio`、`max_drawdown`、`trade_count`、`fee_total`、`slippage_estimate` 等，函数骨架见 `ai-analysis-design.md` §指标计算骨架。
- [x] **验证**：用固定测试数据，断言指标值与手工计算一致。

### 7.3 规则化报告模板

- [x] 在 `app/services/ai_report_service.py` 实现 `generate_report(range_start, range_end, scope)`：
  1. 查询订单/成交/信号/风控/资金/行情。
  2. 调 `MetricsService` 算指标。
  3. 套 Markdown 模板生成正文。
  4. 写 `ai_reports`，返回 `report_id`。
- [x] API：`GET /api/ai/reports`、`GET /api/ai/reports/{id}`、`POST /api/ai/reports`。

### 7.4 接入 AI 模型（可选）

- [x] 若 `LIANGHUA_AI_PROVIDER` 已配置，调用模型生成文字分析，**系统提示词必须包含** `ai-analysis-design.md` §提示词约束 的全部条款。
- [x] AI 输出后端做后处理：扫描是否包含"立即买入/卖出"等指令性词汇，命中则替换为"建议关注"并记录告警。
- [x] **验证**：构造测试数据生成报告，断言不含指令性词汇。

### 7.5 前端 AI 报告页

- [x] `pages/AiReports.tsx`：选择范围 → 生成 → 历史报告列表 → 报告详情（指标图表 + 文本）。
- [x] 页面顶部固定提示："AI 报告仅用于复盘参考，不提供直接下单入口"。

### 7.6 AI 自然语言策略生成

- [x] `app/services/ai_strategy_service.py`：System Prompt + 指标目录注入 + JSON 解析 + `RuleValidator` 校验 + 失败重试。
- [x] API：`POST /api/ai/strategies/generate`（见 `api/routes/ai_strategies.py`）。
- [x] 前端 `AiStrategyPanel` + `StrategyBuilder` 第一步集成。
- [x] 单测：`test_ai_strategy_service.py`、`test_ai_strategy_api.py`。
- [x] 设计文档：[strategy-builder-design.md](strategy-builder-design.md)。

### 阶段 7 完成标志

- [x] 用户可选择范围生成复盘报告。
- [x] 报告引用真实统计数据。
- [x] 报告不产生直接下单指令。
- [ ] Git 提交：`phase 7: ai report`。

---

## 阶段 8：收尾与上线

- [x] 跑 `testing-acceptance.md` §端到端验收场景：自动化冒烟 `scripts/acceptance_smoke.py` + 全量 pytest；完整手工 UI 场景见验收清单（Mock 工程项）。
- [x] 跑 `pytest` 全套：当前 **170 passed**；整体覆盖率 **85%** ✅。文档关键模块均达标：`trade_service`/`order_service`/`risk_rules`/`mock_adapter`/`ai_report_service` 100%，`metrics_service` 95%，`strategy_service` 82%。含 P0-2 风控关口单测。
- [x] 完善部署文档 `deployment-guide.md` 的启动脚本（落地 `start.ps1` / `stop.ps1` / `backup_db.ps1`）。
- [x] 写 `README.md` 根目录版本，含快速启动命令。
- [x] 整理 `open-questions.md`，已决策的标记「已确认」并补结论。
- [x] 实盘前最终 checklist：**Mock/工程项已勾**；真实 SDK 小额实盘项仍待原生授权（见 `testing-acceptance.md`）。
- [ ] Git 提交：`phase 8: wrap up and docs`。

---

## 附录 A：推荐 .gitignore

```text
# Python
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/
.pytest_cache/
.coverage
htmlcov/

# Node
node_modules/
dist/
.vite/

# 环境与密钥
.env
.env.local
*.local
secrets/

# 数据库备份
backups/
*.sql.gz

# IDE
.vscode/
.idea/
*.swp

# OS
Thumbs.db
.DS_Store
```

## 附录 B：每阶段自检清单模板

每完成一个阶段，复制以下清单到本阶段末尾自检：

- [ ] 本阶段所有子任务已勾选完成。
- [ ] 本阶段"完成标志"全部达成。
- [ ] 新增代码有对应单测且通过。
- [ ] 涉及数据库的变更已生成 Alembic 迁移且 `upgrade head` 成功。
- [ ] 涉及接口的变更已更新 `api-spec.md`（如有出入）。
- [ ] 已 Git 提交，提交信息符合 `phase N: <主题>` 格式。
