# stop.ps1 —— 停止本项目相关的后端/前端开发进程
# 用法（项目根目录）：.\stop.ps1
$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path

Write-Host "=== Lianghua 停止 ===" -ForegroundColor Cyan

function Stop-MatchingProcesses {
    param(
        [string[]]$Names,
        [string]$Hint
    )
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $Names -contains $_.Name -and
            ($_.CommandLine -like "*$Hint*" -or $_.ExecutablePath -like "*$Hint*")
        } |
        ForEach-Object {
            Write-Host ("停止 PID {0} ({1})" -f $_.ProcessId, $_.Name)
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

# uvicorn / 后端 python
Stop-MatchingProcesses -Names @("python.exe", "python") -Hint "lianghua\backend"
Stop-MatchingProcesses -Names @("python.exe", "python") -Hint "uvicorn app.main"

# Vite / 前端 node
Stop-MatchingProcesses -Names @("node.exe", "node") -Hint "lianghua\frontend"

Write-Host "已尝试停止前后端开发进程。" -ForegroundColor Green
Write-Host "PostgreSQL / Docker 数据库未自动停止（避免误关共享实例）。"
