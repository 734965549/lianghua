# 量化交易系统（Lianghua）

Windows 单机版量化交易终端：FastAPI + React + PostgreSQL，同花顺 SDK 接入（默认 Mock；真实 SDK 用可切换骨架）。

## 快速启动

### 前置条件

- Windows 10/11
- Python ≥ 3.11
- Node.js LTS（≥ 20）
- PostgreSQL 15+（本机安装，或 Docker Compose）

### 一键启动（推荐）

```powershell
# 项目根目录
# 首次：先装好 backend\.venv 与 frontend 依赖（见下方手动步骤）
.\start.ps1
```

浏览器打开 http://127.0.0.1:5173  
健康检查：http://127.0.0.1:8000/api/health  

停止：

```powershell
.\stop.ps1
```

### 数据库

**本机 PostgreSQL（推荐）**：创建库与用户后，配置 `backend/.env` 中的 `LIANGHUA_DATABASE_URL`。

**Docker**：

```powershell
docker compose up -d
docker compose ps
```

### 后端（手动）

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # 按需修改
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 前端（手动）

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

> 前端 Vite 代理 `/api` → `http://127.0.0.1:8000`（见 `frontend/vite.config.ts`）。

### SDK 模式

| 变量 | 说明 |
| --- | --- |
| `LIANGHUA_SDK_MODE=mock` | 默认，本地开发与验收 |
| `LIANGHUA_SDK_MODE=real` + `LIANGHUA_SDK_DRIVER=sim` | 无原生 DLL 时的映射/双通道骨架验收 |
| `LIANGHUA_SDK_MODE=real` + `native` | 真实同花顺驱动占位（未配置则 `SDKNotConfigured`） |

探活脚本（real + sim）：

```powershell
$env:LIANGHUA_SDK_MODE="real"
$env:LIANGHUA_SDK_DRIVER="sim"
$env:LIANGHUA_STOCK_ACCOUNT="SIM_STOCK_001"
cd backend
.\.venv\Scripts\python.exe scripts\sdk_smoke_query.py --market stock
```

### 数据库备份

```powershell
cd backend
.\scripts\backup_db.ps1
```

备份文件默认写入 `backend/backups/lianghua_yyyyMMdd_HHmmss.sql.gz`。

### 测试

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
pytest --cov=app --cov-report=term-missing --cov-report=html
```

## 文档

| 文档 | 说明 |
| --- | --- |
| [`doc/README.md`](doc/README.md) | 设计文档索引 |
| [`doc/development-roadmap.md`](doc/development-roadmap.md) | 阶段 0→8 路线图 |
| [`doc/deployment-guide.md`](doc/deployment-guide.md) | 部署、环境变量、故障排查 |
| [`doc/testing-acceptance.md`](doc/testing-acceptance.md) | 测试与上线前清单 |
| [`doc/open-questions.md`](doc/open-questions.md) | 未决/已确认问题 |

## 安全提示

- 不要把 `.env`、SDK 密码、AI Key 提交到仓库。
- 熔断/紧急停止状态不会因重启自动解除。
- AI 报告仅供复盘参考，不提供直接下单入口。
- AI 策略生成仅辅助编写规则定义，生成后需人工确认并校验，不会自动下单。
- **真实资金下单前**：须完成原生 SDK 接入与 `testing-acceptance.md` 上线前清单中的实盘项。
