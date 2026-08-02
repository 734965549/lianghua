# 项目交接说明（阶段 0–8 收尾 + 2026-07-24 验证）

> 更新日期：2026-07-24  
> 项目路径：`D:\Epan\BaiduNetdiskDownload\go\lianghua`  
> 状态：**MVP 工程主线已闭环，Mock 可本地冒烟**；**尚不能算正式验收完成**；**不建议无人值守模拟自动下单**；真实同花顺 SDK / 实盘资金未接入。  
> Git：最新提交仍为 `064591e`；修复与增强轮次改动仍在 working tree（约 **91** 个未提交文件）。

---

## 一、项目一句话

Windows 单机量化交易终端：FastAPI + React + PostgreSQL，默认 Mock SDK；可切换 `sim` 骨架验收映射与双通道；原生同花顺驱动仅为占位。覆盖行情、策略、风控、委托成交、熔断恢复、历史导出、AI 复盘（规则化优先）。

---

## 二、当前结论（接手人先看）

| 维度 | 结论 |
| --- | --- |
| 可以跑 | 界面浏览、行情 Mock、人工监督的工程冒烟（含指定 GET API；`acceptance_smoke` 另含写库） |
| 暂缓跑 | 自动策略持续产生模拟委托（需人工盯场） |
| 不能跑 | 实盘 / 原生 SDK（未配置账户与 DLL） |
| 测试 | 后端 pytest **170 passed, 0 failed**（2026-07-24） |
| 迁移 | `0008_audit_append_only (head)` |
| SDK | 当前验收环境有效模式为 `mock`，账户为空；每次启动前仍需核对环境变量和 `/api/health`（系统环境变量可覆盖 `.env`） |
| 数据库 | Docker 容器 `lianghua-pg` 可保持运行；`stop.ps1` **不会**停库 |

### 2026-07-24 本轮已修阻塞项

1. **PowerShell 编码**：`start.ps1` / `stop.ps1` / `backend/scripts/backup_db.ps1` 已加 UTF-8 BOM，PowerShell 5.1 可解析中文。
2. **总仓位风控**：`TotalPositionRule` 买入时计入本次委托敞口（`现有市值 + price×quantity`）；卖出不增加敞口。文档 `risk-control-design.md` 已同步（去掉错误的 `quantity×market_value`）。
3. **非法订单状态回报**：非法迁移保守标为 `unknown`；测试契约已与实现统一。

### 2026-07-24 验证快照

| 项 | 结果 |
| --- | --- |
| 后端 pytest | **170 passed, 11169 warnings**（Python **3.14.2**；README 基线为 3.11。警告主要为依赖在 3.14 下的弃用提示，不阻断 Mock） |
| Alembic | 已在 head，无需升级 |
| API 冒烟（本轮手工） | 已验证：`GET /api/health`、`/api/dashboard`、`/api/orders`、`/api/history/orders`、`/api/history/trades`、`/api/ai/reports`、`/api/risk/status`、`/api/risk/settings`、`/api/risk/checks` 全部 200 |
| acceptance_smoke | 另含 `POST /api/ai/reports`（会写库生成报告，非纯只读）；提交前应跑 |
| 健康检查 | api/db/stock_sdk/futures_sdk 均 ok；`system_status=ready` |
| 前端 | `npm run build` 成功 |
| 启停 | 冒烟后已用 `stop.ps1` 停后端；未启策略、未提交订单 |

---

## 三、做了什么（按阶段摘要）

### 阶段 0–1：骨架与系统

- FastAPI、Vite/React/Ant Design、Docker Compose PostgreSQL、Alembic
- 统一 API 响应、健康检查、系统状态、审计日志、配置读写

### 阶段 2：Mock SDK 与行情

- `MockTradingAdapter`、行情快照 / K 线、WebSocket 推送

### 阶段 3：策略与风控

- 策略注册 / 启停（如 `ma_cross`）、信号落库
- 风控规则链（白名单、限额、时段、日亏损、总仓位含新委托敞口等）

### 阶段 4：订单与成交

- 下单 / 撤单 / 成交幂等、订单状态机、持仓与资金快照
- **P0-2**：`trade_service.submit` 强制校验 passed 风控记录；缺则订单 `FAILED`，禁止直达 SDK

### 阶段 5：熔断与恢复

- 熔断 / 紧急停止、重启恢复；一键停止；恢复交易需确认
- unknown 订单确认 API：`POST /api/orders/{client_order_id}/confirm-unknown`

### 阶段 6：真实 SDK 骨架（无原生 DLL）

- Driver：`Unconfigured` / `Simulated` / `Native` 占位
- 股票 / 期货适配器 + 字段映射、双通道；验收脚本已备

### 阶段 7：AI 复盘与报表

- 历史筛选、CSV（UTF-8 BOM）、交易链路抽屉
- 规则化 Markdown 报告；可选 OpenAI 兼容接口（复盘）
- AI 自然语言策略定义生成（`POST /api/ai/strategies/generate`，见 `strategy-builder-design.md`）

### 阶段 8：收尾与工程上线

- `start.ps1` / `stop.ps1`、`backup_db.ps1`、`acceptance_smoke.py`
- 前端路由懒加载；组件抽离（委托/持仓/策略/审计/紧急停止等）

---

## 四、关键路径速查

```
backend/
  app/
    api/routes/        # health, orders, risk, history, ai_reports, ...
    sdk/               # mock + drivers(sim/native) + stock/futures adapter
    services/          # order/trade/risk/metrics/ai_report/...
    db/migrations/     # 0001–0008
    tests/             # api / e2e / sdk / services
    workers/           # scheduler, sync_jobs, retention
  scripts/             # acceptance_smoke, sdk_smoke_query, backup_db

frontend/src/pages/    # Dashboard, Market, Strategies, Trading, Positions,
                       # History, AiReports, RiskSettings, Settings, Logs

doc/                   # 设计文档 + roadmap + 本交接说明
start.ps1 / stop.ps1
README.md
```

### 常用命令

```powershell
# 一键启停（需 UTF-8 BOM；已修复）
.\start.ps1
.\stop.ps1

# 后端
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pytest
pytest --cov=app --cov-report=term-missing

# 验收冒烟（后端已启动）
.\.venv\Scripts\python.exe scripts\acceptance_smoke.py

# sim 骨架探活（非默认，勿对真实资金使用）
$env:LIANGHUA_SDK_MODE="real"
$env:LIANGHUA_SDK_DRIVER="sim"
$env:LIANGHUA_STOCK_ACCOUNT="SIM_STOCK_001"
.\.venv\Scripts\python.exe scripts\sdk_smoke_query.py --market stock
```

默认：`LIANGHUA_SDK_MODE=mock`。敏感配置在 `backend/.env`（**勿提交**）。

---

## 五、没有做什么 / 仍开放项

### 工程债

1. **工作区未全部提交**：HEAD=`064591e`；后续缺口对齐、风控修复、前端组件、迁移 `0007`/`0008`、e2e 等均在 working tree（约 91 个未提交文件）。提交前确认排除：`.env`、`backups/`、`.venv/`、`node_modules/`、`htmlcov/`；`.codebase-memory/` 已写入根 `.gitignore`，若此前曾被跟踪需确认未 `git add`
2. 非关键路径覆盖率仍可加深：`risk_service` 部分分支、`sync_jobs`/`scheduler`、`sdk/drivers/native.py`
3. 完整手工 UI 端到端（策略→下单→成交→报告）仍依赖人工对照 `testing-acceptance.md` 表 1–16 点一遍

### 真实交易未就绪

4. **未接入**真实同花顺 DLL/COM（`NativeThsDriver` 调用即 `SDKNotConfigured`）
5. **未拿到**真实 SDK 文档 / 授权 / 调用示例
6. **未做**小额实盘验收
7. 生产默认仍为 **mock**

### 功能遗留

8. 策略 `pending_confirm` 前端确认重启流未做完
9. 交易日历（节假日等）未完善
10. AI 报告 PDF、本地模型、定时备份调度（现仅手动 `backup_db.ps1`）
11. CI（GitHub Actions 等）未建

---

## 六、下一步建议（优先级）

### P0 — 立刻可做

1. **提交工作区补丁**（在 `064591e` 之上再提一次或多次有意义的 commit）
2. **本地 Mock 手工验收**：`start.ps1` → 仪表盘 → 策略（人工盯）→ 订单成交 → 历史 CSV → AI 报告
3. **提交前必须跑**：全量 `pytest`、前端 `npm run build`、`acceptance_smoke.py`（后端已启动）

### P1 — 真实 SDK 到位后（阻塞实盘）

4. 补齐 `sdk-notes-stock.md` / `sdk-notes-futures.md`
5. 实现 `NativeThsDriver`，完善状态映射
6. `real` + `native`：`sdk_smoke_query` → 小额下单撤单 → 勾实盘验收清单

### P2 — 体验与增强

7. `pending_confirm` 前端流、交易日历、定时备份、AI PDF
8. 可选 CI / Windows 服务 / 桌面壳

---

## 七、风险与注意事项

- 在原生 SDK 接入、只读探活、小额下单撤单和实盘验收清单全部通过前，禁止使用真实资金。
- 熔断 / 紧急停止**不会**因进程重启自动解除。
- 非法订单状态回报会标为 `unknown`，需人工 `confirm-unknown` 后再恢复交易。
- AI 报告仅供复盘参考，禁止「直接下单」话术；外部 AI 只发聚合指标。
- AI 策略生成只输出 DSL JSON，须经 `RuleValidator` 与用户确认后才可保存，不自动创建或启动策略。
- 交易时段关闭 Windows 休眠；PostgreSQL 勿对公网开放。
- 换机器：复制 `backend/.env.example` → `.env`，再 `alembic upgrade head`。
- `stop.ps1` 只停前后端开发进程，**不停** Docker/PostgreSQL。

---

## 八、文档索引

| 文档 | 用途 |
| --- | --- |
| [README.md](../README.md) | 快速启动 |
| [development-roadmap.md](development-roadmap.md) | 阶段勾选主线 |
| [open-questions.md](open-questions.md) | 已确认默认与可变更项 |
| [deployment-guide.md](deployment-guide.md) | 部署 / 备份 / 故障排查 |
| [testing-acceptance.md](testing-acceptance.md) | 测试、覆盖率、上线清单 |
| [risk-control-design.md](risk-control-design.md) | 风控规则（含总仓位敞口） |
| [ai-analysis-design.md](ai-analysis-design.md) | 复盘指标与安全边界 |
| [sdk-adapter-design.md](sdk-adapter-design.md) | SDK 适配设计 |

---

## 九、交接检查清单（接手人）

- [ ] 能 `.\start.ps1` 打开前后端，`/api/health` 正常（UTF-8 BOM 已修）；启动前核对环境变量有效模式
- [ ] 提交前跑通：全量 `pytest`（目标 170 passed）、前端 `npm run build`、`acceptance_smoke.py`
- [ ] 读完本文件 §二、§五、§六、§七
- [ ] 与交接人确认：**工作区是否再提 commit**、**SDK 预计到位时间**
- [ ] 明确当前禁止：真实资金（须原生 SDK + 探活 + 小额验收全过）、未授权外部 AI 密钥入库、无人值守自动模拟下单

---

*本交接对应路线图阶段 0–8。后续以「固化 working tree 提交 + Mock 人工验收」或「原生 SDK 接入」为两条主线择一推进。*
