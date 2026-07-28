# stop.ps1 -- 停止本项目相关的后端/前端开发进程
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

# 清理残留的启动窗口（start.ps1 用 Start-Process powershell -NoExit 打开的窗口）
Stop-MatchingProcesses -Names @("powershell.exe", "pwsh.exe") -Hint "lianghua\backend"
Stop-MatchingProcesses -Names @("powershell.exe", "pwsh.exe") -Hint "lianghua\frontend"

# 确认端口已释放
Start-Sleep -Seconds 1
$ports = @(8000, 5173)
foreach ($port in $ports) {
    $conn = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($conn) {
        Write-Warning "端口 $port 仍被占用，尝试强制释放..."
        $conn | ForEach-Object {
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "端口 $port 已释放" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "已停止前后端开发进程。" -ForegroundColor Green
Write-Host "PostgreSQL / Docker 数据库未自动停止（避免误关共享实例）。"
