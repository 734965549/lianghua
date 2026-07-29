# 事件驱动回测引擎设计文档

- 日期：2026-07-29
- 状态：待审阅
- 作者：Trae Assistant
- 相关需求：补齐量化交易系统回测能力，支持 K 线 / 模拟 tick / 真实 tick 三种回放粒度

## 1. 背景与目标

当前系统已具备策略管理、实时行情分发、信号生成与风控能力，但缺少历史回测验证环节。策略上线前无法基于历史数据验证有效性，导致策略迭代风险高。

本设计目标：

- 提供独立、可测试的事件驱动回测引擎。
- 策略代码零改动复用：已有 `Strategy` 子类可直接用于回测。
- 支持三种回放粒度：K 线级别、模拟 tick、真实 tick（后两者预留接口）。
- 输出完整的回测绩效报告：收益率、夏普、最大回撤、胜率、成交记录等。

## 2. 非目标（第一期不做）

- 真实 tick 数据源的具体实现（仅预留接口）。
- CSV / Parquet 等外部历史数据导入。
- 多进程 / 分布式回测。
- 期权、可转债等复杂品种的行权处理。

## 3. 方案对比

| 方案 | 核心思路 | 优点 | 缺点 |
|------|----------|------|------|
| **A（推荐）** | 新增独立 `BacktestRunner`，通过 `HistoricalDataSource` + `SimulationBroker` 回放事件 | 与实盘服务解耦；策略零改动；三种粒度可切换；易测试 | 新增子系统，文件数略多 |
| **B** | 在现有 `StrategyService` 上增加“回测模式” | 复用现有调度逻辑，改动快 | 实盘/回测代码混杂；真实 tick 需侵入式改造；难单独验证 |
| **C** | 独立进程 + 消息总线，完全模拟生产事件流 | 最接近真实环境，扩展性强 | 对当前系统过重，第一期 ROI 低 |

推荐采用 **方案 A**。

## 4. 架构设计

### 4.1 核心模块

```text
backtest/
├── runner.py           # BacktestRunner：回测主控
├── data_source.py      # HistoricalDataSource 及 Kline/Tick 实现
├── broker.py           # SimulationBroker：模拟撮合
├── account.py          # SimulationAccount：虚拟资金与持仓
├── fill_model.py       # FillModel：撮合价格模型
├── metrics.py          # BacktestMetrics：绩效指标
├── context.py          # BacktestContext：回测专用策略上下文
└── models.py           # 回测领域模型（BacktestRequest、BacktestResult 等）
```

### 4.2 模块职责

- **BacktestRunner**：编排一次完整回测。负责加载策略、加载数据、事件循环、驱动策略回调、收集信号、委托 SimulationBroker 撮合、生成报告。
- **HistoricalDataSource**：抽象历史数据读取。提供按时间排序的事件流（`KlineEvent`、`QuoteEvent`）。
  - `KlineDataSource`：读取数据库现有 K 线。
  - `SimulatedTickDataSource`：基于 K 线生成 OHLC 伪 tick 序列。
  - `TickDataSource`：预留，后续接入真实 tick 数据。
- **SimulationBroker**：接收策略信号/订单，按价格模型撮合，维护成交记录，回调 `on_order_update`。
- **SimulationAccount**：维护现金、持仓、市值、冻结资金。
- **FillModel**：可配置的撮合价格模型，如 `next_open`、`next_close`、`vwap`、`tick_price`。
- **BacktestMetrics**：基于账户和成交记录计算绩效指标。
- **BacktestContext**：继承或兼容现有 `StrategyContext`，内部使用历史数据读取器和模拟账户读取器。

## 5. 数据流

1. 用户调用 `POST /backtests`，构造 `BacktestRequest`。
2. `BacktestRunner` 校验参数，实例化策略。
3. `HistoricalDataSource` 加载指定标的、时间区间、回放粒度的事件流。
4. 进入事件循环：
   - K 线模式：每个 bar 触发 `strategy.on_bar(bar)`。
   - 模拟 tick 模式：在每个 bar 内生成伪 tick，触发 `strategy.on_quote(quote)`。
   - 真实 tick 模式：直接回放真实 tick。
5. 策略通过 `context.submit_signal()` 提交信号。
6. `BacktestRunner` 把信号转换为模拟订单，交给 `SimulationBroker`。
7. `SimulationBroker` 在后续价格事件中按 `FillModel` 撮合，更新 `SimulationAccount`，并回调 `strategy.on_order_update(event)`。
8. 事件流结束后，`BacktestMetrics` 计算绩效，持久化 `BacktestResult`。
9. 用户通过 `GET /backtests/{id}` 查询状态，`GET /backtests/{id}/results` 获取报告。

## 6. 关键接口设计

### 6.1 Python 内部接口

```python
class HistoricalDataSource(ABC):
    def load_events(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        granularity: Granularity,
    ) -> Iterator[MarketEvent]: ...

class SimulationBroker:
    def submit_order(self, order: Order) -> str: ...
    def on_market_event(self, event: MarketEvent) -> list[Fill]: ...
    def get_account(self) -> SimulationAccount: ...

class BacktestRunner:
    def __init__(self, request: BacktestRequest): ...
    def run(self) -> BacktestResult: ...
```

### 6.2 REST API

- `POST /backtests`：创建回测任务，返回 `backtest_id`。
- `GET /backtests`：分页列出回测任务。
- `GET /backtests/{id}`：查询回测状态与元数据。
- `GET /backtests/{id}/results`：获取完整绩效报告、权益曲线、成交记录。
- `DELETE /backtests/{id}`：删除回测记录（仅管理员或创建者）。

### 6.3 前端页面

新增页面 `/backtest`：

- 参数表单：选择策略、标的、时间区间、初始资金、回放粒度、撮合模型、滑点/佣金设置。
- 结果展示：权益曲线图、关键指标卡片、成交记录表格、日志。

## 7. 策略代码兼容性

- 已有 `Strategy` 子类无需修改即可回测。
- `StrategyContext` 的行为保持一致：`get_klines`、`get_quote`、`get_position`、`get_account`、`submit_signal`。
- 回测中不调用 `on_start` / `on_stop` 的副作用（如连接外部服务），由 `BacktestContext` 保证安全。

## 8. 错误处理

- 参数非法：返回 `400` 并说明字段错误。
- 标的无历史数据：回测结果为空，报告中明确提示。
- 策略运行异常：记录错误日志，中止该次回测，不污染实盘服务。
- 数据库连接异常：返回 `503`，并记录审计日志。

## 9. 测试策略

- 单元测试：
  - K 线回放产生正确 bar。
  - 模拟 tick 在 bar 内按 OHLC 顺序生成。
  - 市价/限价单撮合价格正确。
  - 佣金、滑点、印花税计算正确。
  - 绩效指标计算正确（已知输入输出比对）。
- 集成测试：
  - 使用 `ma_cross` 策略跑一段历史数据，验证端到端流程。
  - API 创建回测并获取结果。

## 10. 数据库变更

新增表 `backtest_runs` 与 `backtest_results`（或使用 JSON 字段存储）。字段包括：

- `id`, `strategy_id`, `parameters`, `symbols`, `start_time`, `end_time`
- `granularity`, `fill_model`, `initial_cash`, `final_equity`
- `metrics_json`, `trades_json`, `equity_curve_json`, `status`, `error_msg`
- `created_at`, `updated_at`

## 11. 实现任务拆分（Phase 1）

1. 创建 `backtest/` 包及核心模型。
2. 实现 `KlineDataSource` 与 `SimulatedTickDataSource`。
3. 实现 `SimulationBroker`、`SimulationAccount`、`FillModel`。
4. 实现 `BacktestContext`。
5. 实现 `BacktestRunner` 与 `BacktestMetrics`。
6. 新增 `POST/GET /backtests` API。
7. 新增前端回测页面。
8. 编写单元测试与集成测试。
9. 补齐 CTA / 网格 / 多因子策略模板。

## 12. 后续扩展

- 接入 `TickDataSource` 实现真实 tick 回测。
- 支持 CSV / Parquet 历史数据导入。
- 参数寻优与 Walk-Forward 分析。
- 多进程并行回测。

## 13. 开放问题

- 回测任务是否需要异步执行（Celery / BackgroundTasks）？第一期建议同步执行并设置超时，后续根据性能需求改造。
- 历史数据量较大时，是否需要在内存中流式读取？建议数据源返回迭代器，避免一次性加载。
