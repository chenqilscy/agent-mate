[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'AgentMate'),
    [switch]$LaunchSmoke
)

$ErrorActionPreference = 'Stop'
$resolvedInstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$requiredFiles = @(
    'agentmate.exe',
    'agentmate-backend.exe',
    'WebView2Loader.dll'
)

if (-not (Test-Path -LiteralPath $resolvedInstallDir -PathType Container)) {
    throw "AgentMate install directory does not exist: $resolvedInstallDir"
}

$missingFiles = @(
    $requiredFiles | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $resolvedInstallDir $_) -PathType Leaf)
    }
)
if ($missingFiles.Count -gt 0) {
    throw "AgentMate install is incomplete; missing: $($missingFiles -join ', ')"
}

$result = [ordered]@{
    ok = $true
    install_dir = $resolvedInstallDir
    files = [ordered]@{}
}
foreach ($name in $requiredFiles) {
    $file = Get-Item -LiteralPath (Join-Path $resolvedInstallDir $name)
    $result.files[$name] = [ordered]@{
        size_bytes = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

if ($LaunchSmoke) {
    $app = Start-Process -FilePath (Join-Path $resolvedInstallDir 'agentmate.exe') -PassThru
    $deadline = (Get-Date).AddSeconds(45)
    $health = $null
    do {
        Start-Sleep -Milliseconds 500
        $app.Refresh()
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8101/api/health' -TimeoutSec 2
        } catch {
            $health = $null
        }
    } while (
        -not $app.HasExited -and
        ($app.MainWindowHandle -eq 0 -or $null -eq $health) -and
        (Get-Date) -lt $deadline
    )

    if ($app.HasExited) {
        throw "AgentMate exited during startup with code $($app.ExitCode)"
    }
    if ($app.MainWindowHandle -eq 0) {
        throw 'AgentMate did not create a visible window within 45 seconds'
    }
    if ($null -eq $health) {
        throw 'AgentMate backend did not become healthy within 45 seconds'
    }

    $listener = Get-NetTCPConnection -LocalPort 8101 -State Listen -ErrorAction Stop |
        Where-Object { $_.LocalAddress -in @('127.0.0.1', '0.0.0.0', '::1', '::') } |
        Select-Object -First 1
    if ($null -eq $listener) {
        throw 'AgentMate health endpoint responded but no local :8101 listener was found'
    }
    $backend = Get-Process -Id $listener.OwningProcess -ErrorAction Stop

    $result.launch = [ordered]@{
        app_pid = $app.Id
        window_handle = $app.MainWindowHandle
        window_title = $app.MainWindowTitle
        backend_pid = $backend.Id
        backend_process = $backend.ProcessName
        health = $health
    }
}

$result | ConvertTo-Json -Depth 4
