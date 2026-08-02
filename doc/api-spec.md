# API 接口规范

## 基本约定

| 项目 | 约定 |
| --- | --- |
| Base URL | `http://127.0.0.1:8000` |
| API 前缀 | `/api` |
| 数据格式 | JSON |
| 时间格式 | ISO 8601，带时区 |
| 金额和数量 | 后端使用 decimal，JSON 中建议返回字符串 |
| 认证 | MVP 单机版默认不做登录；危险操作必须记录本地用户和审计日志 |

## 统一响应

成功：

```json
{
  "success": true,
  "data": {},
  "error": null,
  "correlation_id": "req_20260621_000001"
}
```

失败：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "RISK_DAILY_LOSS_LIMIT",
    "message": "当日亏损已达到熔断阈值，禁止提交新委托",
    "retryable": false
  },
  "correlation_id": "req_20260621_000002"
}
```

## 分页格式

列表接口统一支持：

| 参数 | 说明 |
| --- | --- |
| page | 页码，从 1 开始 |
| page_size | 每页条数，默认 20，最大 200 |

返回：

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 0
}
```

## 核心接口

### 健康与仪表盘

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 后端、数据库、SDK 适配器健康检查 |
| GET | `/api/dashboard` | 仪表盘核心数据 |
| GET | `/api/system/status` | 系统状态 |

`GET /api/health` 返回字段：

| 字段 | 说明 |
| --- | --- |
| api | API 服务状态 |
| database | 数据库连接状态 |
| stock_sdk | 股票 SDK 状态 |
| futures_sdk | 期货 SDK 状态 |
| system_status | 系统状态 |

### 行情

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/quotes` | 行情列表 |
| GET | `/api/quotes/{market}/{symbol}` | 单个标的行情 |
| POST | `/api/quotes/subscriptions` | 更新关注标的 |
| GET | `/api/klines` | 查询历史 K 线 |

`GET /api/quotes` 查询参数：

| 参数 | 说明 |
| --- | --- |
| market | `stock` 或 `futures`，可选 |
| symbols | 逗号分隔标的，可选 |

### 策略

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/indicator-catalog` | 策略构建器：指标/操作符/公式目录 |
| GET | `/api/strategies` | 策略列表 |
| POST | `/api/strategies` | 创建规则策略（含 definition） |
| GET | `/api/strategies/{strategy_id}` | 策略详情 |
| PUT | `/api/strategies/{strategy_id}` | 更新规则策略草稿 |
| PUT | `/api/strategies/{strategy_id}/parameters` | 更新策略参数 |
| POST | `/api/strategies/{strategy_id}/validate` | 校验 definition |
| POST | `/api/strategies/{strategy_id}/publish` | 发布规则策略 |
| POST | `/api/strategies/{strategy_id}/clone` | 克隆策略 |
| POST | `/api/strategies/{strategy_id}/archive` | 归档用户策略 |
| GET | `/api/strategies/{strategy_id}/versions` | 版本列表 |
| GET | `/api/strategies/{strategy_id}/versions/{version}` | 版本详情（含 definition） |
| POST | `/api/strategies/{strategy_id}/start` | 启动策略 |
| POST | `/api/strategies/{strategy_id}/stop` | 停止策略 |
| GET | `/api/strategy-runs` | 策略运行记录 |
| GET | `/api/signals` | 策略信号列表 |

启动策略请求：

```json
{
  "confirm": true,
  "run_mode": "live",
  "symbols": ["600000.SH", "IF2409"]
}
```

### 风控

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/risk/status` | 风控状态 |
| GET | `/api/risk/checks` | 风控检查记录 |
| GET | `/api/risk/settings` | 风控参数 |
| PUT | `/api/risk/settings` | 更新风控参数 |
| POST | `/api/risk/emergency-stop` | 一键停止 |
| POST | `/api/risk/resume` | 手动恢复交易 |

一键停止请求：

```json
{
  "reason": "用户手动紧急停止",
  "cancel_open_orders": true
}
```

恢复交易请求：

```json
{
  "confirm": true,
  "reason": "已确认 SDK 和账户状态正常"
}
```

### 委托与成交

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/orders` | 委托列表 |
| GET | `/api/orders/{client_order_id}` | 委托详情 |
| POST | `/api/orders/{client_order_id}/cancel` | 撤单 |
| GET | `/api/trades` | 成交列表 |
| GET | `/api/positions` | 持仓 |
| GET | `/api/assets` | 资金快照 |

撤单请求：

```json
{
  "reason": "用户手动撤单"
}
```

MVP 不建议开放手动新建实盘委托接口。若后续增加，必须与策略信号一样进入风控。

### 历史交易

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/history/orders` | 历史委托（支持筛选；`Accept: text/csv` 导出） |
| GET | `/api/history/trades` | 历史成交（同上） |
| GET | `/api/history/orders/{client_order_id}/chain` | 单笔交易链路（信号→风控→委托→成交→审计） |

### AI

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/ai/reports` | AI 报告列表 |
| GET | `/api/ai/reports/{report_id}` | AI 报告详情 |
| POST | `/api/ai/reports` | 生成 AI 复盘报告 |
| POST | `/api/ai/reports/{report_id}/feedback` | 标记有用/无用 |
| POST | `/api/ai/strategies/generate` | AI 自然语言生成策略 definition |

生成报告请求：

```json
{
  "range_start": "2026-06-01T00:00:00+08:00",
  "range_end": "2026-06-21T23:59:59+08:00",
  "strategy_ids": ["ma_cross"],
  "markets": ["stock", "futures"],
  "symbols": []
}
```

生成策略定义请求：

```json
{
  "prompt": "日线双均线，5日上穿20日买入，下穿卖出，每次100股，止损5%止盈10%",
  "market": "stock",
  "interval": "1d"
}
```

- `prompt`：必填，自然语言描述，最长 4000 字符
- `market` / `interval`：可选，作为生成偏好注入模型

响应：

```json
{
  "name": "双均线金叉",
  "description": "快线上穿慢线买入，下穿卖出",
  "definition": { "schema_version": 1, "market": "stock", "interval": "1d", "...": "..." },
  "validation": { "valid": true, "errors": [] },
  "model_name": "gpt-4o-mini"
}
```

- 错误码：`AI_STRATEGY_NOT_CONFIGURED`、`AI_STRATEGY_PROMPT_EMPTY`、`AI_STRATEGY_FAILED`、`AI_STRATEGY_INVALID_OUTPUT`
- 生成结果**不会自动创建策略**；用户在前端确认后调用 `POST /api/strategies` 保存
- DSL 字段说明见 [strategy-builder-design.md](strategy-builder-design.md)

### 系统设置和日志

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/settings` | 获取非敏感配置 |
| PUT | `/api/settings` | 更新配置 |
| POST | `/api/settings/test-sdk` | 测试 SDK 连接 |
| POST | `/api/settings/test-database` | 测试数据库连接 |
| GET | `/api/logs/audit` | 审计日志 |
| GET | `/api/logs/system-events` | 系统事件 |

配置接口不返回敏感字段明文。前端可显示 `configured: true/false`。

## 实时事件接口

建议 MVP 提供：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| WebSocket | `/api/ws/events` | 实时事件流 |

事件格式：

```json
{
  "topic": "order.update",
  "event_time": "2026-06-21T10:01:02+08:00",
  "data": {},
  "correlation_id": "req_20260621_000003"
}
```

事件主题：

| topic | 说明 |
| --- | --- |
| `system.status` | 系统状态变化 |
| `quote.update` | 行情更新 |
| `strategy.signal` | 新策略信号 |
| `order.update` | 委托状态变化 |
| `trade.update` | 成交更新 |
| `risk.event` | 风控拒绝、熔断、恢复 |
| `audit.event` | 关键审计事件 |

## 错误码

> 代码常量：`backend/app/schemas/error_codes.py`（`ErrorCode`）。新增错误码时先加常量再引用。

| 错误码 | 说明 |
| --- | --- |
| `SYS_DATABASE_UNAVAILABLE` | 数据库不可用 |
| `SYS_INVALID_CONFIG` | 系统配置错误 |
| `SDK_CONNECTION_FAILED` | SDK 连接失败 |
| `SDK_RESPONSE_INVALID` | SDK 返回字段异常 |
| `RISK_SYMBOL_BLOCKED` | 标的被风控禁止 |
| `RISK_DAILY_LOSS_LIMIT` | 当日亏损达到阈值 |
| `RISK_SYSTEM_STOPPED` | 系统熔断或紧急停止 |
| `ORDER_DUPLICATE_CLIENT_ID` | 重复委托幂等 ID |
| `ORDER_STATUS_UNKNOWN` | 委托状态未知 |
| `STRATEGY_RUNTIME_ERROR` | 策略运行异常 |
| `AI_REPORT_FAILED` | AI 报告生成失败 |
| `AI_STRATEGY_NOT_CONFIGURED` | AI 未配置（策略生成） |
| `AI_STRATEGY_PROMPT_EMPTY` | 策略描述为空 |
| `AI_STRATEGY_FAILED` | AI 策略生成调用失败 |
| `AI_STRATEGY_INVALID_OUTPUT` | AI 返回非合法 definition |

## 审计要求

以下接口成功或失败都必须写审计日志：

1. 更新系统设置。
2. 更新风控设置。
3. 启动和停止策略。
4. 一键停止和恢复交易。
5. 撤单。
6. 生成 AI 报告。
7. AI 自然语言生成策略定义（`ai_strategy_generate`）。
8. 任何现在或未来新增的交易写接口。

---

## 统一响应骨架（后端实现参考）

> 放 `backend/app/api/response.py`。

```python
from typing import Any, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False
    debug: str | None = None  # 仅开发环境返回


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
    correlation_id: str


class PagedData(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


def ok(data: Any = None, correlation_id: str = "") -> ApiResponse:
    return ApiResponse(success=True, data=data, error=None, correlation_id=correlation_id)


def fail(code: str, message: str, *, retryable: bool = False,
        debug: str | None = None, correlation_id: str = "") -> ApiResponse:
    return ApiResponse(
        success=False, data=None,
        error=ErrorDetail(code=code, message=message, retryable=retryable, debug=debug),
        correlation_id=correlation_id,
    )


class BizError(Exception):
    """业务异常，由全局异常处理器转成 fail() 响应。"""
    def __init__(self, code: str, message: str, *, retryable: bool = False, status: int = 400):
        self.code, self.message, self.retryable, self.status = code, message, retryable, status
```

全局异常处理器（放 `app/api/dependencies.py` 或 `app/main.py`）：

```python
@app.exception_handler(BizError)
async def biz_error_handler(request, exc: BizError):
    cid = request.state.correlation_id
    return JSONResponse(status_code=exc.status, content=fail(
        exc.code, exc.message, retryable=exc.retryable, correlation_id=cid
    ).model_dump())
```

---

## 各接口详细定义

> 每个接口给出：路径 / 请求参数 / 请求体 / 响应字段 / 示例。
> 所有响应都包裹在统一响应结构里，下文"响应字段"指 `data` 字段内容。

### 1. 健康检查

`GET /api/health`

- 请求参数：无
- 响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| api | string | 固定 `"ok"` |
| database | string | `connected` / `disconnected` |
| stock_sdk | string | `connected` / `disconnected` / `not_configured` |
| futures_sdk | string | 同上 |
| system_status | string | 系统状态枚举 |
| version | string | 后端版本 |

- 示例：
  ```json
  {"success": true, "data": {"api":"ok","database":"connected","stock_sdk":"not_configured","futures_sdk":"not_configured","system_status":"ready","version":"0.1.0"}, "error": null, "correlation_id":"req_..."}
  ```

### 2. 仪表盘

`GET /api/dashboard`

- 响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| system_status | string | 系统状态 |
| daily_pnl | string | 当日盈亏（decimal 字符串） |
| position_value | string | 持仓市值 |
| available_cash | string | 可用资金 |
| daily_trade_count | int | 当日交易次数 |
| risk_reject_count | int | 当日风控拒绝次数 |
| breaker_active | boolean | 是否熔断中 |
| running_strategies | int | 运行中策略数 |
| latest_orders | Order[] | 最近 5 笔委托 |
| latest_alerts | SystemEvent[] | 最近 5 条告警 |

### 3. 系统状态

`GET /api/system/status`

- 响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| status | string | 系统状态枚举 |
| status_reason | string | 当前状态原因 |
| status_since | string | 进入当前状态的时间 |
| breaker_reason | string \| null | 熔断原因（非熔断为 null） |

### 4. 行情列表

`GET /api/quotes`

- 查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| market | string | 否 | `stock` / `futures` |
| symbols | string | 否 | 逗号分隔标的，如 `600000.SH,IF2409` |

- 响应：`QuoteSnapshot[]`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| symbol | string | 标的 |
| market | string | 市场 |
| last_price | string | 最新价 |
| change_rate | string | 涨跌幅 |
| volume | string | 成交量 |
| bid_price | string | 买一价 |
| ask_price | string | 卖一价 |
| quote_time | string | 行情时间 |

### 5. 单标的行情

`GET /api/quotes/{market}/{symbol}`

- 路径参数：`market`、`symbol`
- 响应：`QuoteSnapshot`（含买卖盘多档，扩展字段在 `metadata`）

### 6. 更新关注标的

`POST /api/quotes/subscriptions`

- 请求体：
  ```json
  {"symbols": ["600000.SH", "IF2409"], "market": "futures"}
  ```
- 响应：
  ```json
  {"subscribed": ["600000.SH", "IF2409"]}
  ```

### 7. 历史 K 线

`GET /api/klines`

- 查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| market | string | 是 | 市场 |
| symbol | string | 是 | 标的 |
| interval | string | 是 | `1m` / `5m` / `1d` |
| start | string | 否 | ISO8601 开始时间 |
| end | string | 否 | 结束时间 |
| limit | int | 否 | 默认 500，最大 2000 |

- 响应：`KlineBar[]`
  ```json
  [{"bar_time":"2026-07-20T09:30:00+08:00","open":"10.00","high":"10.20","low":"9.95","close":"10.15","volume":"100000"}]
  ```

### 8. 策略列表

`GET /api/strategies`

- 响应：`Strategy[]`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| strategy_id | string | 策略 ID |
| name | string | 名称 |
| description | string | 说明 |
| enabled | boolean | 是否启用 |
| running | boolean | 当前是否运行中 |
| supported_markets | string[] | 支持市场 |
| parameters | object | 当前参数 |
| parameters_schema | object | 参数 JSON Schema（前端动态表单） |

### 9. 策略详情

`GET /api/strategies/{strategy_id}`

- 响应：`Strategy` + `latest_run`（最近一次运行实例）+ `today_metrics`

### 10. 更新策略参数

`PUT /api/strategies/{strategy_id}/parameters`

- 请求体：参数对象，必须符合 `parameters_schema`
  ```json
  {"fast": 5, "slow": 20, "quantity": "100", "symbols": ["600000.SH"]}
  ```
- 响应：更新后的完整 `Strategy`
- 错误码：`STRATEGY_PARAM_INVALID`、`STRATEGY_RUNNING_PARAMS_LOCKED`（运行中改参数需先暂停）

### 11. 启动策略

`POST /api/strategies/{strategy_id}/start`

- 请求体：
  ```json
  {"confirm": true, "run_mode": "live", "symbols": ["600000.SH"], "parameters": {}}
  ```
- 响应：
  ```json
  {"run_id": "...", "strategy_id": "ma_cross", "status": "running", "started_at": "..."}
  ```
- 错误码：`STRATEGY_ALREADY_RUNNING`、`STRATEGY_PARAM_INVALID`、`RISK_SYSTEM_STOPPED`

### 12. 停止策略

`POST /api/strategies/{strategy_id}/stop`

- 请求体：
  ```json
  {"reason": "用户手动停止", "cancel_open_orders": false}
  ```
- 响应：
  ```json
  {"run_id": "...", "status": "stopped", "stopped_at": "..."}
  ```

### 13. 策略运行记录

`GET /api/strategy-runs`

- 查询参数：`strategy_id`、`status`、`page`、`page_size`
- 响应：分页 `StrategyRun[]`

### 14. 策略信号列表

`GET /api/signals`

- 查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| strategy_id | string | 否 | 筛选策略 |
| symbol | string | 否 | 筛选标的 |
| market | string | 否 | 筛选市场 |
| start | string | 否 | 开始时间 |
| end | string | 否 | 结束时间 |
| page | int | 否 | 页码 |
| page_size | int | 否 | 每页 |

- 响应：分页 `StrategySignal[]`

### 15. 风控状态

`GET /api/risk/status`

- 响应：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| system_status | string | 系统状态 |
| breaker_active | boolean | 是否熔断 |
| breaker_reason | string | 熔断原因 |
| daily_loss | string | 当日亏损 |
| daily_loss_limit | string | 亏损阈值 |
| daily_trade_count | int | 当日交易次数 |
| consecutive_order_fail | int | 连续下单失败数 |
| unknown_order_count | int | 未知订单数 |

### 16. 风控检查记录

`GET /api/risk/checks`

- 查询参数：`client_order_id`、`signal_id`、`result`、`page`、`page_size`
- 响应：分页 `RiskCheck[]`

### 17. 风控参数

`GET /api/risk/settings`

- 响应：`risk_configs` 表全部字段（见 `database-design.md` 迁移 5）

### 18. 更新风控参数

`PUT /api/risk/settings`

- 请求体：`risk_configs` 子集（只传要改的字段）+ 必须 `confirm=true`
  ```json
  {"confirm": true, "daily_loss_limit": "30000", "max_order_amount": "500000", "reason": "调整日亏损阈值"}
  ```
- 响应：更新后的完整 `risk_configs`
- 错误码：`RISK_CONFIG_INVALID`、`RISK_CONFIRM_REQUIRED`
- 必须：写审计日志，后端与前端二次确认

### 19. 一键停止

`POST /api/risk/emergency-stop`

- 请求体：
  ```json
  {"reason": "用户手动紧急停止", "cancel_open_orders": true}
  ```
- 响应：
  ```json
  {"status": "emergency_stopped", "cancelled_orders": 3}
  ```
- 错误码：`RISK_ALREADY_STOPPED`

### 20. 恢复交易

`POST /api/risk/resume`

- 请求体：
  ```json
  {"confirm": true, "reason": "已确认 SDK 和账户状态正常"}
  ```
- 响应：
  ```json
  {"status": "trading", "resumed_at": "..."}
  ```
- 错误码：`RISK_RESUME_BLOCKED`（附未满足的前置条件列表）、`RISK_UNKNOWN_ORDERS_PENDING`

### 21. 委托列表

`GET /api/orders`

- 查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| market | string | 否 | 市场 |
| symbol | string | 否 | 标的 |
| strategy_id | string | 否 | 策略 |
| status | string | 否 | 订单状态 |
| start | string | 否 | 开始时间 |
| end | string | 否 | 结束时间 |
| page | int | 否 |  |
| page_size | int | 否 |  |

- 响应：分页 `Order[]`

### 22. 委托详情

`GET /api/orders/{client_order_id}`

- 响应：`Order` + 关联的 `RiskCheck` + `Trade[]` + `AuditLog[]`（交易链路）

### 23. 撤单

`POST /api/orders/{client_order_id}/cancel`

- 请求体：
  ```json
  {"reason": "用户手动撤单"}
  ```
- 响应：
  ```json
  {"client_order_id": "...", "status": "cancelled", "cancelled_at": "..."}
  ```
- 错误码：`ORDER_NOT_CANCELLABLE`（已成交/已撤单）、`RISK_SYSTEM_STOPPED`

### 24. 成交列表

`GET /api/trades`

- 查询参数：同 `/api/orders`
- 响应：分页 `Trade[]`

### 25. 持仓

`GET /api/positions`

- 查询参数：`account_id`、`market`、`symbol`
- 响应：`Position[]`（取每个标的最新快照）

### 26. 资金快照

`GET /api/assets`

- 查询参数：`account_id`
- 响应：`AccountAsset[]`（含历史序列用于画曲线，`limit` 控制点数）

### 27. AI 报告列表

`GET /api/ai/reports`

- 查询参数：`page`、`page_size`
- 响应：分页 `AiReport` 摘要（不含 content 全文）

### 28. AI 报告详情

`GET /api/ai/reports/{report_id}`

- 响应：完整 `AiReport`（含 `content`、`metrics`）

### 29. 生成 AI 报告

`POST /api/ai/reports`

- 请求体：
  ```json
  {
    "range_start": "2026-06-01T00:00:00+08:00",
    "range_end": "2026-06-21T23:59:59+08:00",
    "strategy_ids": ["ma_cross"],
    "markets": ["stock", "futures"],
    "symbols": []
  }
  ```
- 响应：
  ```json
  {"report_id": "...", "generated_at": "...", "metrics_summary": {...}}
  ```
- 错误码：`AI_REPORT_NO_DATA`（范围内无数据）、`AI_REPORT_FAILED`

### 30. 系统配置

`GET /api/settings`

- 响应：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| database | object | `{configured: bool, host, port, dbname}` |
| stock_sdk | object | `{configured: bool, path, account_ref}` |
| futures_sdk | object | 同上 |
| ai | object | `{provider, configured: bool}` |
| backup_dir | string | 备份目录 |
| sensitive_fields | string[] | 敏感字段名列表（不回显值） |

### 31. 更新配置

`PUT /api/settings`

- 请求体：配置对象，敏感字段以明文提交但**不回显**
  ```json
  {"stock_sdk": {"path": "C:/ths/stock_sdk", "account": "12345", "password": "secret"}}
  ```
- 响应：更新后的配置（敏感字段只返回 `configured: true`）

### 32. 测试数据库连接

`POST /api/settings/test-database`

- 请求体：
  ```json
  {"database_url": "postgresql+psycopg://..."}
  ```
- 响应：
  ```json
  {"ok": true, "server_version": "PostgreSQL 15.3"}
  ```
- 错误码：`SYS_DATABASE_UNAVAILABLE`

### 33. 测试 SDK 连接

`POST /api/settings/test-sdk`

- 请求体：
  ```json
  {"market": "stock"}
  ```
- 响应：
  ```json
  {"ok": true, "account_no": "12345", "latency_ms": 120}
  ```
- 错误码：`SDK_CONNECTION_FAILED`、`SDK_AUTH_FAILED`

### 34. 审计日志

`GET /api/logs/audit`

- 查询参数：`module`、`action`、`object_type`、`start`、`end`、`page`、`page_size`
- 响应：分页 `AuditLog[]`

### 35. 系统事件

`GET /api/logs/system-events`

- 查询参数：`severity`、`module`、`resolved`、`start`、`end`、`page`、`page_size`
- 响应：分页 `SystemEvent[]`

---

## WebSocket 事件详细字段

### `system.status`
```json
{"status": "circuit_breaker", "reason": "当日亏损达到阈值", "since": "2026-07-20T14:00:00+08:00"}
```

### `quote.update`
```json
{"symbol":"600000.SH","market":"stock","last_price":"10.15","change_rate":"0.015","volume":"100000","quote_time":"2026-07-20T10:00:00+08:00"}
```

### `strategy.signal`
完整 `StrategySignal` 对象。

### `order.update`
```json
{"client_order_id":"lh_20260720_xxxx","sdk_order_id":"THS123","status":"partially_filled","filled_quantity":"50","remaining_quantity":"50","event_time":"..."}
```

### `trade.update`
完整 `Trade` 对象。

### `risk.event`
```json
{"type":"rejected","rule_code":"RISK_SYMBOL_BLACKLIST","signal_id":"...","reason":"标的同时在黑名单"}
```
或
```json
{"type":"breaker","reason":"当日亏损达到阈值","cancelled_orders":3}
```
