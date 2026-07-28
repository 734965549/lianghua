# backup_db.ps1 —— 手动备份 PostgreSQL（UTF-8 SQL + gzip）
# 用法：在 backend 目录执行  .\scripts\backup_db.ps1
# 依赖：PATH 中有 pg_dump（PostgreSQL 客户端工具）
$ErrorActionPreference = "Stop"

$backendRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $backendRoot

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        if ($line -match "^([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
            $name = $matches[1]
            $value = $matches[2].Trim().Trim('"').Trim("'")
            Set-Item -Path "env:$name" -Value $value
        }
    }
}

Import-DotEnv (Join-Path $backendRoot ".env")

$dbUrl = $env:LIANGHUA_DATABASE_URL
if (-not $dbUrl) {
    Write-Error "未设置 LIANGHUA_DATABASE_URL（可写在 backend/.env）"
}

$backupDir = $env:LIANGHUA_BACKUP_DIR
if (-not $backupDir) { $backupDir = "./backups" }
if (-not [System.IO.Path]::IsPathRooted($backupDir)) {
    $backupDir = Join-Path $backendRoot $backupDir
}
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

# 将 SQLAlchemy URL 转为 libpq 可用连接串
# postgresql+psycopg://user:pass@host:port/db -> postgresql://user:pass@host:port/db
$conn = $dbUrl -replace "^postgresql\+psycopg", "postgresql"
$conn = $conn -replace "^postgresql\+psycopg2", "postgresql"

if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 pg_dump，请将 PostgreSQL bin 目录加入 PATH。"
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$sqlFile = Join-Path $backupDir "lianghua_$ts.sql"
$gzFile = Join-Path $backupDir "lianghua_$ts.sql.gz"

Write-Host "开始备份 -> $gzFile"
& pg_dump $conn -f $sqlFile
if ($LASTEXITCODE -ne 0) {
    Write-Error "pg_dump 失败，exit=$LASTEXITCODE"
}

# gzip（不依赖外部 gzip 命令）
Add-Type -AssemblyName System.IO.Compression.FileSystem
$inputStream = [System.IO.File]::OpenRead($sqlFile)
$outputStream = [System.IO.File]::Create($gzFile)
$gzip = New-Object System.IO.Compression.GZipStream($outputStream, [System.IO.Compression.CompressionLevel]::Optimal)
$inputStream.CopyTo($gzip)
$gzip.Dispose()
$outputStream.Dispose()
$inputStream.Dispose()
Remove-Item $sqlFile -Force

Write-Host "备份成功: $gzFile" -ForegroundColor Green
Write-Host ("大小: {0:N1} KB" -f ((Get-Item $gzFile).Length / 1KB))
