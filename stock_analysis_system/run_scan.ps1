# 全市场扫描启动脚本
# 用法：
#   前台运行：.\run_scan.ps1
#   后台运行：.\run_scan.ps1 -Background
#   指定日志：.\run_scan.ps1 -LogFile run_v2_20260922.log
param(
    [switch]$Background,
    [string]$LogFile = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 关键环境变量
$env:PYTHONDONTWRITEBYTECODE = "1"   # 禁止写.pyc，避免沙箱拦截系统Python目录导致exit code 1
$env:PYTHONPATH = "$PSScriptRoot\.deps"  # 项目本地依赖（akshare/pandas等）

if (-not $LogFile) {
    $LogFile = "run_{0}.log" -f (Get-Date -Format "yyyyMMdd")
}

if ($Background) {
    Write-Host "后台启动扫描，日志: $PSScriptRoot\$LogFile"
    py -3 -u main.py *> $LogFile
} else {
    Write-Host "前台运行扫描，日志同时写入: $PSScriptRoot\$LogFile"
    py -3 -u main.py 2>&1 | Tee-Object -FilePath $LogFile
}
