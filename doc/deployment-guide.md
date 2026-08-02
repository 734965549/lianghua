# Windows 本地部署指南

## 目标环境

| 依赖 | 版本 |
| --- | --- |
| Windows | 10 或 11 |
| Python | 3.11+ |
| Node.js | LTS |
| PostgreSQL | 15+ |
| 同花顺 SDK | 股票 SDK、期货 SDK |

## 默认端口

| 服务 | 端口 |
| --- | --- |
| 前端 Vite | 5173 |
| FastAPI | 8000 |
| PostgreSQL | 5432 |

## 环境变量

建议使用 Windows 用户级环境变量保存敏感配置：

| 变量 | 说明 |
| --- | --- |
| `LIANGHUA_DATABASE_URL` | PostgreSQL 连接串 |
| `LIANGHUA_STOCK_SDK_PATH` | 股票 SDK 本地路径 |
| `LIANGHUA_FUTURES_SDK_PATH` | 期货 SDK 本地路径 |
| `LIANGHUA_STOCK_ACCOUNT` | 股票账号标识 |
| `LIANGHUA_FUTURES_ACCOUNT` | 期货账号标识 |
| `LIANGHUA_CONFIG_KEY` | 本地配置加密密钥 |
| `LIANGHUA_AI_PROVIDER` | AI 服务提供方；复盘未配置降级模板，策略生成未配置则报错 |
| `LIANGHUA_AI_API_KEY` | AI 密钥，可为空 |

## 开发启动流程

1. 启动 PostgreSQL。
2. 创建数据库和本地用户。
3. 启动后端迁移，生成表结构。
4. 启动 FastAPI 后端。
5. 启动 React 前端。
6. 在浏览器访问 `http://127.0.0.1:5173`。
7. 在系统设置页测试数据库和 SDK 连接。

真实 SDK 未准备好时，后端应使用 Mock SDK 模式（`LIANGHUA_SDK_MODE=mock`）。进入真实模式前请保持同花顺客户端已登录；骨架期可用 `LIANGHUA_SDK_DRIVER=sim` 验证映射与双通道同步。

## 后端开发模式

建议命令形式：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 前端开发模式

建议命令形式：

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

## 数据库备份

MVP 建议提供手动备份脚本：

1. 使用 `pg_dump` 导出数据库。
2. 备份文件保存到用户配置的本地目录。
3. 文件名包含日期时间。
4. 备份成功或失败写入审计日志。

后续可增加定时备份。

## 运行注意事项

1. 交易时段内关闭 Windows 自动休眠。
2. 不要将数据库端口开放到公网。
3. 不要把 SDK 密码、Token 或密钥写入代码仓库。
4. 后端异常退出后，重新启动必须先检查未完成订单和风控状态。
5. 熔断或紧急停止状态不能因重启自动解除。

## 故障排查

| 现象 | 检查项 |
| --- | --- |
| 前端无法打开 | Vite 是否启动，端口 5173 是否被占用 |
| 健康检查失败 | 后端是否启动，端口 8000 是否被占用 |
| 数据库不可用 | PostgreSQL 服务、连接串、账号密码、防火墙 |
| SDK 连接失败 | SDK 路径、授权、账号、客户端是否已启动 |
| 行情无更新 | SDK 订阅、标的代码、交易时段、网络连接 |
| 委托状态 unknown | SDK 回调、轮询结果、账号委托列表 |
| 熔断无法恢复 | 风控状态、未知订单、SDK 和数据库健康状态 |

## 打包方向

MVP 先支持命令行启动。后续可以增加：

1. 一键启动 PowerShell 脚本。
2. Windows 服务模式。
3. Tauri 桌面客户端。
4. 本地安装包。

---

## 完整环境变量示例

> 在后端 `backend/` 下创建 `.env`（**不提交**），或用 Windows 用户级环境变量。模板见 `.env.example`。

```text
# ===== 数据库 =====
LIANGHUA_DATABASE_URL=postgresql+psycopg://lianghua:lianghua_dev@127.0.0.1:5432/lianghua

# ===== SDK =====
# mode: mock / real（MVP 阶段用 mock，真实接入前改 real）
LIANGHUA_SDK_MODE=mock
LIANGHUA_SDK_DRIVER=auto
LIANGHUA_STOCK_SDK_PATH=C:/ths/stock_sdk
LIANGHUA_FUTURES_SDK_PATH=C:/ths/futures_sdk
LIANGHUA_STOCK_ACCOUNT=
LIANGHUA_FUTURES_ACCOUNT=

# ===== 安全 =====
# 敏感字段加密密钥，32 字节随机串的 base64，生成方式见下文
LIANGHUA_CONFIG_KEY=

# ===== AI（可选）=====
# 复盘报告：未配置时降级为规则化模板
# 策略生成：未配置时 POST /api/ai/strategies/generate 返回 AI_STRATEGY_NOT_CONFIGURED
LIANGHUA_AI_PROVIDER=
LIANGHUA_AI_API_KEY=
LIANGHUA_AI_BASE_URL=
LIANGHUA_AI_MODEL=gpt-4o-mini

# ===== 运行 =====
LIANGHUA_HOST=127.0.0.1
LIANGHUA_PORT=8000
LIANGHUA_LOG_LEVEL=INFO
LIANGHUA_BACKUP_DIR=./backups
LIANGHUA_TZ=Asia/Shanghai
```

## 生成 CONFIG_KEY

```bash
# Git Bash：生成 32 字节随机串的 base64
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

把输出填入 `LIANGHUA_CONFIG_KEY`。

## 一键启动脚本

> 项目根 `start.ps1`。PowerShell：`.\start.ps1`  
> 会检查本机 PostgreSQL 服务（或尝试 `docker compose up -d`），并在新窗口启动后端（8000）与前端（5173）。

首次使用前请先完成：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env

cd ..\frontend
npm install
```

## 一键停止脚本

> 项目根 `stop.ps1`：`.\stop.ps1`  
> 按命令行匹配停止本仓库相关的 python/uvicorn 与 frontend node 进程；**不会**停止 PostgreSQL/Docker。

## 数据库备份脚本

> `backend/scripts/backup_db.ps1`（需 PATH 含 `pg_dump`）。

```powershell
cd backend
.\scripts\backup_db.ps1
```

输出：`{LIANGHUA_BACKUP_DIR}/lianghua_yyyyMMdd_HHmmss.sql.gz`（默认 `./backups`）。脚本从 `.env` 读取 `LIANGHUA_DATABASE_URL`，在 Windows 上用 .NET GZip 压缩，不依赖外部 `gzip` 命令。

## 常用命令速查

| 操作 | 命令 |
| --- | --- |
| 创建虚拟环境 | `python -m venv .venv` |
| 激活虚拟环境（Git Bash） | `source .venv/Scripts/activate` |
| 激活虚拟环境（PowerShell） | `.\.venv\Scripts\Activate.ps1` |
| 安装后端依赖 | `pip install -r requirements.txt` |
| 生成迁移 | `alembic revision --autogenerate -m "描述"` |
| 执行迁移 | `alembic upgrade head` |
| 回滚一版 | `alembic downgrade -1` |
| 查看迁移历史 | `alembic history` |
| 启动后端 | `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` |
| 运行后端测试 | `pytest` |
| 覆盖率报告 | `pytest --cov=app --cov-report=html --cov-report=term-missing` |
| 验收冒烟（后端已启动） | `python scripts/acceptance_smoke.py` |
| 数据库备份 | `.\scripts\backup_db.ps1` |
| 一键启动/停止 | 项目根 `.\start.ps1` / `.\stop.ps1` |
| 运行指定测试 | `pytest app/tests/services/test_risk_service.py -v` |
| 前端安装依赖 | `npm install` |
| 启动前端 | `npm run dev` |
| 前端构建 | `npm run build` |
| 前端类型检查 | `npx tsc --noEmit` |
| 连接数据库 | `psql -U lianghua -d lianghua` |
| 查看表 | `\dt` |
| 查看表结构 | `\d orders` |

## PostgreSQL 安装方式选择

| 方式 | 优点 | 缺点 | 推荐场景 |
| --- | --- | --- | --- |
| 本机安装（EnterpriseDB） | 性能好、配置直观、开机自启 | 安装繁琐、卸载残留 | **推荐 MVP** |
| Docker Desktop | 隔离干净、切换版本方便 | 占用资源、需先装 Docker | 已有 Docker 环境 |
| 便携版 | 免安装 | 性能差、不适合长期 | 仅试用 |

本机安装后建议：
1. 安装时设 `postgres` 超级用户密码并记录。
2. 安装完用 Stack Builder 装 `pgAdmin`（图形化管理）。
3. 把 `bin` 目录加入 PATH（方便 `psql`、`pg_dump` 命令行）。

## Windows 休眠与电源设置

交易时段必须关闭自动休眠，避免后端中断：

```powershell
# 临时关闭休眠（管理员 PowerShell）
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change monitor-timeout-ac 0
```

或 GUI：设置 → 系统 → 电源 → 屏幕和睡眠 → "接通电源时永不休眠"。

## 防火墙与端口

- PostgreSQL 端口 5432 **不要**对公网开放，仅监听 127.0.0.1。
- 后端 8000、前端 5173 仅本机访问。
- `postgresql.conf` 中 `listen_addresses = 'localhost'`。
- `pg_hba.conf` 中只保留本地 `127.0.0.1/32` 与 `::1/128` 的 `md5` 认证。
