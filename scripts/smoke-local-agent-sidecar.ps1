[CmdletBinding()]
param(
    [string]$Binary = 'src-tauri/binaries/agentmate-local-agent-x86_64-pc-windows-gnu.exe',
    [switch]$CleanupStale
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$binaryPath = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $Binary))
if (-not (Test-Path -LiteralPath $binaryPath -PathType Leaf)) {
    throw "Local Agent sidecar does not exist: $binaryPath"
}

$systemTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
if ($CleanupStale) {
    Get-Process | Where-Object {
        try {
            [System.IO.Path]::GetFullPath($_.Path) -eq $binaryPath
        }
        catch {
            $false
        }
    } | Stop-Process -Force
    Get-ChildItem -LiteralPath $systemTemp -Directory -Filter 'agentmate-wb440-*' | ForEach-Object {
        $stalePath = [System.IO.Path]::GetFullPath($_.FullName)
        if (-not $stalePath.StartsWith($systemTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe stale Local Agent smoke directory: $stalePath"
        }
        Remove-Item -LiteralPath $stalePath -Recurse -Force
    }
}

$smokeRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $systemTemp ('agentmate-wb440-' + [guid]::NewGuid().ToString('N')))
)
if (-not $smokeRoot.StartsWith($systemTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe Local Agent smoke directory: $smokeRoot"
}
New-Item -ItemType Directory -Path $smokeRoot | Out-Null

$portProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$portProbe.Start()
$port = ([System.Net.IPEndPoint]$portProbe.LocalEndpoint).Port
$portProbe.Stop()
$ipcToken = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')

$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $binaryPath
$startInfo.Arguments = '--local-agent-core --ipc-token-stdin'
$startInfo.WorkingDirectory = $smokeRoot
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardInput = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.Environment['PORT'] = [string]$port
$startInfo.Environment['AGENTMATE_DB'] = Join-Path $smokeRoot 'compat.db'
$startInfo.Environment['AGENTMATE_LOCAL_AGENT_DB'] = Join-Path $smokeRoot 'local-agent.db'
$startInfo.Environment['AGENTMATE_WORKSPACE'] = Join-Path $smokeRoot 'workspace'
$startInfo.Environment['AGENTMATE_SERVER_URL'] = ''

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $startInfo
$started = $false
$smokeStartedAt = Get-Date
try {
    $started = $process.Start()
    if (-not $started) {
        throw 'Failed to start the Local Agent sidecar'
    }
    $process.StandardInput.WriteLine($ipcToken)
    $process.StandardInput.Close()

    $deadline = (Get-Date).AddSeconds(45)
    $health = $null
    do {
        Start-Sleep -Milliseconds 250
        try {
            $health = Invoke-RestMethod `
                -Uri "http://127.0.0.1:$port/api/local-agent/health" `
                -Headers @{ 'X-AgentMate-IPC-Token' = $ipcToken } `
                -TimeoutSec 2
        }
        catch {
            $health = $null
        }
    } while ($null -eq $health -and (Get-Date) -lt $deadline)

    if ($null -eq $health) {
        $launcherState = if ($process.HasExited) { "launcher exit=$($process.ExitCode)" } else { 'launcher running' }
        throw "Local Agent sidecar health check timed out ($launcherState)"
    }
    if (-not $health.ok -or $health.service -ne 'local-agent-core') {
        throw "Unexpected Local Agent health response: $($health | ConvertTo-Json -Compress)"
    }

    [pscustomobject]@{
        ok = $health.ok
        service = $health.service
        port = $port
        process = $process.ProcessName
        binary = [System.IO.Path]::GetFileName($binaryPath)
    } | ConvertTo-Json -Compress
}
finally {
    if ($started -and -not $process.HasExited) {
        $process.Kill()
        [void]$process.WaitForExit(10000)
    }
    Get-Process | Where-Object {
        try {
            $_.StartTime -ge $smokeStartedAt -and
                [System.IO.Path]::GetFullPath($_.Path) -eq $binaryPath
        }
        catch {
            $false
        }
    } | Stop-Process -Force
    $process.Dispose()
    if (Test-Path -LiteralPath $smokeRoot) {
        Remove-Item -LiteralPath $smokeRoot -Recurse -Force
    }
}
