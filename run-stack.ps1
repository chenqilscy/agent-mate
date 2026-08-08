# AgentMate 开发栈一键启动：Server(API + Console, :8100) + Local Agent(:8101) + App UI(:8102)
#
# 用法（在仓库根，PowerShell）：  ./run-stack.ps1
# 每层在独立窗口启动；已在运行的端口会跳过。关掉对应窗口即停该层。
# 前置：依赖已装（backend/.venv 是 Local Agent 的兼容源码环境；另需 pnpm install，见 README）。
#
# 拓扑：App UI(:8102) --/server-api--> Server(:8100)
#                    --/api---------> Local Agent(:8101，含迁移期兼容 API)
#   Server       远端部署的业务 API、Console 与持久业务数据权威源
#   Local Agent  用户设备上的执行服务：Agent runtime、MCP/tools、本机密钥、工作区、WAL/cache
#   App UI       用户设备上的界面；不是 Local Agent，也不是 Server API
#
# Server 地址只在 App“设置中心 → 运行服务”中配置，并保存在本机数据库。

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $root 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path $py)) { $py = 'python' }   # 无 venv 时退回 PATH 的 python

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Test-Listening([int]$port) {
  [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

# 1) Server :8100
if (Test-Listening 8100) { Write-Host 'Server      :8100  已在运行，跳过' -ForegroundColor Yellow }
else {
  Write-Host '启动 Server      :8100 ...' -ForegroundColor Cyan
  Start-Process -FilePath $py -ArgumentList 'main.py' -WorkingDirectory (Join-Path $root 'server')
}

# 2) Local Agent :8101（源码暂位于 backend/ 兼容目录）
if (Test-Listening 8101) { Write-Host 'Local Agent :8101  已在运行，跳过' -ForegroundColor Yellow }
else {
  Write-Host '启动 Local Agent :8101（连接 Server）...' -ForegroundColor Cyan
  Start-Process -FilePath $py -ArgumentList 'main.py' -WorkingDirectory (Join-Path $root 'backend')
}

# 3) App UI :8102
if (Test-Listening 8102) { Write-Host 'App UI      :8102  已在运行，跳过' -ForegroundColor Yellow }
else {
  Write-Host '启动 App UI      :8102 ...' -ForegroundColor Cyan
  Start-Process -FilePath 'cmd.exe' -ArgumentList '/k pnpm dev' -WorkingDirectory $root
}

Write-Host ''
Write-Host '开发栈：Server(API + Console) :8100  /  Local Agent :8101  /  App UI :8102' -ForegroundColor Green
Write-Host '浏览器打开 http://127.0.0.1:8102；Server/Console 应在正式环境中独立部署。'
Write-Host '停止：关掉各自窗口，或  Get-NetTCPConnection -LocalPort 8100,8101,8102 | %{ Stop-Process -Id $_.OwningProcess -Force }'
