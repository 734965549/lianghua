# 项目交接说明（阶段 0–8 收尾）

> 更新日期：2026-07-20  
> 项目路径：`D:\E盘\BaiduNetdiskDownload\go\lianghua`  
> 状态：**MVP 工程主线已闭环（Mock 可本地验收）**；真实同花顺 SDK / 实盘资金未接入；**Git 尚无任何 commit**。

---

## 一、项目一句话

Windows 单机量化交易终端：FastAPI + React + PostgreSQL，默认 Mock SDK；可切换 `sim` 骨架验收映射与双通道；原生同花顺驱动仅为占位。覆盖行情、策略、风控、委托成交、熔断恢复、历史导出、AI 复盘（规则化优先）。

---

## 二、做了什么（按阶段）

### 阶段 0–1：骨架与系统

- 后端 FastAPI、前端 Vite/React/Ant Design、Docker Compose PostgreSQL、Alembic 迁移
- 统一 API 响应、健康检查、系统状态、审计日志、配置读写（敏感字段不回显）
- 根 `.gitignore`、`.env.example`、基础文档体系（`doc/`）

### 阶段 2：Mock SDK 与行情

- `MockTradingAdapter`、行情快照 / K 线、WebSocket 推送
- 行情看板与仪表盘基础能力

### 阶段 3：策略与风控

- 策略注册 / 启停（如 `ma_cross`）、信号落库
- 风控规则链（白名单、限额、时段、日亏损等）与风控设置页

### 阶段 4：订单与成交

- 下单 / 撤单 / 成交幂等、订单状态机、持仓与资金快照
- 自动交易页（委托 / 成交表）

### 阶段 5：熔断与恢复

- 熔断 / 紧急停止、重启恢复未完结订单与风控状态
- 一键停止（全局）、恢复交易需确认

### 阶段 6：真实 SDK 骨架（无原生 DLL）

- Driver：`Unconfigured` / `Simulated` / `Native` 占位；`LIANGHUA_SDK_DRIVER=auto|sim|native`
- `StockTradingAdapter` / `FuturesTradingAdapter` + 字段映射、错误标准化、本地 `client_order_id ↔ sdk_order_id`
- 期货开平 / 平今昨 / 投机套保走 `action` + `metadata`
- real 模式探活；回调 + 轮询双通道单测
- 验收脚本：`sdk_smoke_query.py`、`sdk_small_order_cancel.py`

### 阶段 7：AI 复盘与报表

- 历史委托/成交筛选、CSV（UTF-8 BOM）、交易链路抽屉
- `MetricsService`（FIFO 盈亏等确定性指标）
- 规则化 Markdown 报告 → `ai_reports`；可选 OpenAI 兼容接口 + 指令词过滤
- 前端 `History.tsx`、`AiReports.tsx`（固定「仅供复盘、无下单入口」提示）

### 阶段 8：收尾与工程上线

- `start.ps1` / `stop.ps1`、`backend/scripts/backup_db.ps1`、`acceptance_smoke.py`
- 根 `README.md`、部署文档脚本落地、`open-questions.md` 全部标已确认默认
- 前端代理统一 `8000`；上线清单 Mock/工程项已勾

### 验证快照（交接时）

| 项 | 结果 |
| --- | --- |
| 后端 pytest | **66 passed** |
| 覆盖率（约） | 整体 **~74%**；`metrics_service` ~95%；AI/历史关键路径已补测 |
| 前端 | `npm run build` 可通过 |
| 迁移 | 至 `0006_ai_reports` |
| Git | 仓库已 init，**尚无 commit**（全部为未跟踪文件） |

---

## 三、关键路径速查

```
backend/app/
  api/routes/          # health, orders, risk, history, ai_reports, ...
  sdk/                 # mock + drivers(sim/native) + stock/futures adapter
  services/            # order/trade/risk/metrics/ai_report/history/...
  db/migrations/       # 0001–0006
  tests/               # sdk / services / api
  scripts/             # sdk_smoke_query, sdk_small_order_cancel, backup_db, acceptance_smoke

frontend/src/pages/    # Dashboard, Market, Strategies, Trading, Positions,
                       # History, AiReports, RiskSettings, Settings, Logs

doc/                   # 设计文档 + development-roadmap + open-questions + deployment-guide
start.ps1 / stop.ps1
README.md
```

### 常用命令

```powershell
# 一键启停
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

# sim 骨架探活
$env:LIANGHUA_SDK_MODE="real"
$env:LIANGHUA_SDK_DRIVER="sim"
$env:LIANGHUA_STOCK_ACCOUNT="SIM_STOCK_001"
.\.venv\Scripts\python.exe scripts\sdk_smoke_query.py --market stock
```

默认：`LIANGHUA_SDK_MODE=mock`。敏感配置在 `backend/.env`（勿提交）。

---

## 四、没有做什么（刻意未做 / 未收尾）

### 工程债

1. **从未做过 Git 提交**（roadmap 阶段 0–8 的 Git 项全部未勾）
2. 整体测试覆盖率未达文档理想值 **80%**（约 74%）；`strategy_service` 等深度单测不足
3. 完整手工 UI 端到端（策略触发→下单→成交→报告）依赖人工点一遍；自动化仅有 API/单测 + `acceptance_smoke`

### 真实交易未就绪

4. **未接入真实同花顺 DLL/COM**：`NativeThsDriver` 调用即 `SDKNotConfigured`
5. **未拿到**真实 SDK 文档 / 授权 / 调用示例（roadmap 6.1 第一项仍空）
6. **未做**小额实盘验收
7. 生产默认仍为 **mock**，未切 real/native

### 功能遗留（可后续增强）

8. unknown 订单**专用确认 API**（目前有提示与状态，无独立确认流）
9. 策略 `pending_confirm` **前端确认重启流**未做完
10. **交易日历**深化（节假日等）未完善
11. AI 报告 PDF、本地模型、定时备份调度（现仅手动 `backup_db.ps1`）
12. CI（GitHub Actions 等）未建

---

## 五、下一步要做什么（建议优先级）

### P0 — 立刻可做（不依赖外部 SDK）

1. **首次 Git 提交**  
   - 建议：一次 `phase 8: wrap up and docs` 总提交，或按阶段拆 `phase 0`…`phase 8`  
   - 确认勿提交：`.env`、`backups/`、`.venv/`、`node_modules/`、`htmlcov/`
2. **本地 Mock 手工验收**（对照 `doc/testing-acceptance.md` 手工表 1–16）  
   - `start.ps1` → 仪表盘绿 → 策略 → 订单成交 → 历史 CSV → AI 报告无下单指令
3. **跑冒烟**：`acceptance_smoke.py` + 全量 `pytest`

### P1 — 真实 SDK 到位后（阻塞实盘）

4. 补齐 `doc/sdk-notes-stock.md` / `sdk-notes-futures.md`
5. 实现 `NativeThsDriver`（替换占位），完善 `mapping.py` 状态枚举
6. `LIANGHUA_SDK_MODE=real` + `native` 下：`sdk_smoke_query` → 小额下单撤单 → 勾「小额实盘验收」
7. 复核 open-questions 中「可变更」项（client_order_id 透传、消息泵、频率限制等）

### P2 — 体验与增强

8. 补 `strategy_service` / 订单成交路径覆盖率，冲整体 ≥80%
9. unknown 订单确认 API + `pending_confirm` 前端流
10. 交易日历 / 定时备份 / AI PDF（按需）
11. 可选：CI、Windows 服务、桌面壳（Tauri 等，见部署文档「打包方向」）

---

## 六、风险与注意事项

- **不要**在 mock/sim 验收通过前对真实资金下单。
- 熔断 / 紧急停止**不会**因进程重启自动解除。
- AI 仅复盘参考，页面与报告均禁止「直接下单」话术；外部 AI 只发聚合指标。
- 交易时段关闭 Windows 休眠；PostgreSQL 勿对公网开放。
- 交接后若换机器：先复制 `backend/.env.example` → `.env`，再 `alembic upgrade head`。

---

## 七、文档索引

| 文档 | 用途 |
| --- | --- |
| [README.md](../README.md) | 快速启动 |
| [development-roadmap.md](development-roadmap.md) | 阶段勾选主线 |
| [open-questions.md](open-questions.md) | 已确认默认与可变更项 |
| [deployment-guide.md](deployment-guide.md) | 部署 / 备份 / 故障排查 |
| [testing-acceptance.md](testing-acceptance.md) | 测试、覆盖率、上线清单 |
| [ai-analysis-design.md](ai-analysis-design.md) | 复盘指标与安全边界 |
| [sdk-adapter-design.md](sdk-adapter-design.md) | SDK 适配设计 |

---

## 八、交接检查清单（接手人）

- [ ] 能 `.\start.ps1` 打开前端，`/api/health` 正常
- [ ] 能跑通 `pytest`（66+）
- [ ] 读完本文件 §四、§五
- [ ] 与交接人确认：**是否现在做 Git 首次提交**、**SDK 预计到位时间**
- [ ] 明确当前禁止：真实资金、未授权外部 AI 密钥入库

---

*本交接对应路线图阶段 0–8 工程收尾。后续以「Git 固化 + Mock 验收」或「原生 SDK 接入」为两条主线择一推进。*
