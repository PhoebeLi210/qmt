# Web 展示层启动脚本（共享推荐清单 + 多用户自选股分析 + 推送）
# 用法：.\run_web.ps1
# 可选：$env:CHAOGU_PORT="8000"; $env:CHAOGU_INVITE_CODE="你的邀请码"
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = "$PSScriptRoot\.deps"

py -3 -u run_web.py
