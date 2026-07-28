# start.ps1 —— 一键启动：检查 PostgreSQL + 后端 + 前端
# 用法（项目根目录）：.\start.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== Lianghua 启动 ===" -ForegroundColor Cyan

# 1. PostgreSQL：优先本机服务，否则尝试 docker compose
$pgService = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($pgService) {
    if ($pgService.Status -ne "Running") {
        Write-Host "启动 PostgreSQL 服务: $($pgService.Name) ..."
        Start-Service $pgService.Name
    } else {
        Write-Host "PostgreSQL 服务已运行: $($pgService.Name)"
    }
} elseif (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "未检测到本机 PostgreSQL 服务，尝试 docker compose up -d ..."
    Push-Location $root
    docker compose up -d
    Pop-Location
} else {
    Write-Warning "未检测到 PostgreSQL 服务或 Docker，请先启动数据库。"
}

# 2. 后端依赖检查
$venvPy = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Error "未找到 backend\.venv，请先: cd backend; python -m venv .venv; .\.venv\Scripts\pip.exe install -r requirements.txt"
}

$envFile = Join-Path $root "backend\.env"
if (-not (Test-Path $envFile)) {
    $example = Join-Path $root "backend\.env.example"
    if (Test-Path $example) {
        Copy-Item $example $envFile
        Write-Host "已从 .env.example 复制 backend\.env，请按需修改。" -ForegroundColor Yellow
    }
}

# 3. 启动后端（新窗口，默认 8000）
$backendCmd = @"
cd '$root\backend'
.\.venv\Scripts\Activate.ps1
Write-Host '执行数据库迁移...' -ForegroundColor Cyan
alembic upgrade head 2>&1 | Out-Host
Write-Host '后端: http://127.0.0.1:8000/api/health' -ForegroundColor Green
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"@
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# 4. 启动前端（新窗口）
$frontendCmd = @"
cd '$root\frontend'
if (-not (Test-Path 'node_modules')) { npm install }
Write-Host '前端: http://127.0.0.1:5173' -ForegroundColor Green
npm run dev
"@
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host ""
Write-Host "已在新窗口启动后端与前端。" -ForegroundColor Green
Write-Host "  后端健康检查: http://127.0.0.1:8000/api/health"
Write-Host "  前端:         http://127.0.0.1:5173"
Write-Host "停止请运行:     .\stop.ps1"
