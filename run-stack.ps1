# AgentMate 三层本地栈一键启动：Server(:8100) + backend(:8000, 接 Server) + frontend(:5173)
#
# 用法（在仓库根，PowerShell）：  ./run-stack.ps1
# 每层在独立窗口启动；已在运行的端口会跳过。关掉对应窗口即停该层。
# 前置：依赖已装（backend/.venv + pnpm install，见 README）；SkillHub CLI 在 ~/.skillhub。
#
# 拓扑：浏览器(:5173) --/api 代理--> backend(:8000) --AGENTMATE_SERVER_URL--> Server(:8100)
#   Server      账号/组织/项目/成员 + 目录（含 SkillHub 定时镜像 369 技能）的权威源
#   backend  local-first 执行 + 作 Server 客户端（下行 pull 镜像 / 上行 outbox）
#   frontend 显示器，只连本地 backend
#
# 纯本地模式：删掉下面的 AGENTMATE_SERVER_URL 那行（或 backend/.env 里的 AGENTMATE_SERVER_URL），backend 即不接 Server、回退本地。

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $root 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path $py)) { $py = 'python' }   # 无 venv 时退回 PATH 的 python

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:AGENTMATE_SERVER_URL = 'http://127.0.0.1:8100'          # backend 接本地 Server（亦可写进 backend/.env）

function Test-Listening([int]$port) {
  [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

# 1) Server :8100
if (Test-Listening 8100) { Write-Host 'Server      :8100  已在运行，跳过' -ForegroundColor Yellow }
else {
  Write-Host '启动 Server      :8100 ...' -ForegroundColor Cyan
  Start-Process -FilePath $py -ArgumentList 'main.py' -WorkingDirectory (Join-Path $root 'server')
}

# 2) backend :8000（接 Server）
if (Test-Listening 8000) { Write-Host 'backend  :8000  已在运行，跳过' -ForegroundColor Yellow }
else {
  Write-Host '启动 backend  :8000（接 Server）...' -ForegroundColor Cyan
  Start-Process -FilePath $py -ArgumentList 'main.py' -WorkingDirectory (Join-Path $root 'backend')
}

# 3) frontend :5173
if (Test-Listening 5173) { Write-Host 'frontend :5173  已在运行，跳过' -ForegroundColor Yellow }
else {
  Write-Host '启动 frontend :5173 ...' -ForegroundColor Cyan
  Start-Process -FilePath 'cmd.exe' -ArgumentList '/k pnpm dev' -WorkingDirectory $root
}

Write-Host ''
Write-Host '三层：Server :8100  /  backend :8000（接 Server）  /  frontend :5173' -ForegroundColor Green
Write-Host '浏览器打开  http://localhost:5173   → 技能页即显示 Server 镜像的真实技能目录'
Write-Host '停止：关掉各自窗口，或  Get-NetTCPConnection -LocalPort 8100,8000,5173 | %{ Stop-Process -Id $_.OwningProcess -Force }'
