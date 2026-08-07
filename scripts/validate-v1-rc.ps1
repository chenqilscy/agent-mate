[CmdletBinding()]
param(
    [switch]$Live,
    [switch]$IsolatedLive,
    [switch]$DesktopPreflight,
    [switch]$WebE2E,
    [string]$LiveBaseUrl = "http://127.0.0.1:8101/api"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot "backend/.venv/Scripts/python.exe"
$node = (Get-Command node -CommandType Application -ErrorAction Stop |
    Select-Object -First 1 -ExpandProperty Source)
$tsc = Join-Path $repoRoot "node_modules/typescript/bin/tsc"
$vite = Join-Path $repoRoot "node_modules/vite/bin/vite.js"
$previousEmbedDownloadPolicy = $env:AGENTMATE_DISABLE_EMBED_MODEL_DOWNLOAD

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "[BLOCKED] Project Python runtime is missing: $python"
}
if (-not (Test-Path -LiteralPath $tsc -PathType Leaf) -or
    -not (Test-Path -LiteralPath $vite -PathType Leaf)) {
    throw "[BLOCKED] Node dependencies are missing. Run pnpm install first."
}

$passed = [System.Collections.Generic.List[string]]::new()

function Get-TrackedTests {
    param([Parameter(Mandatory)][string]$Pathspec)

    $files = @(& git ls-files --cached -- $Pathspec)
    if ($LASTEXITCODE -ne 0 -or $files.Count -eq 0) {
        throw "[BLOCKED] No tracked tests resolved for $Pathspec"
    }
    return $files
}

function Assert-NoUntrackedTests {
    $untracked = @(& git ls-files --others --exclude-standard -- `
        "backend/tests/**/*.py" "server/tests/**/*.py" `
        "src/**/*.test.ts" "src/**/*.test.tsx" "console/src/**/*.test.ts" "console/src/**/*.test.tsx")
    if ($LASTEXITCODE -ne 0) {
        throw "[BLOCKED] Unable to inspect untracked tests"
    }
    if ($untracked.Count -gt 0) {
        throw "[BLOCKED] Untracked tests are excluded from the release evidence: $($untracked -join ', ')"
    }
}

function Invoke-NativeStep {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Command
    )

    Write-Host "`n[RUN] $Name" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "[FAIL] $Name (exit $LASTEXITCODE)"
    }
    $script:passed.Add($Name)
    Write-Host "[PASS] $Name" -ForegroundColor Green
}

Push-Location $repoRoot
try {
    # Regression and integration lanes must never depend on a cold HuggingFace
    # download. Tests requiring semantic vectors inject an explicit fake/model.
    $env:AGENTMATE_DISABLE_EMBED_MODEL_DOWNLOAD = "1"
    if ($Live -and $IsolatedLive) {
        throw "Choose either -Live or -IsolatedLive, not both."
    }
    Assert-NoUntrackedTests
    $passed.Add("No untracked tests")
    $backendRegressionTests = Get-TrackedTests "backend/tests/regression/test_*.py"
    $serverTests = Get-TrackedTests "server/tests/test_*.py"
    $integrationTests = Get-TrackedTests "backend/tests/integration/test_*.py"

    Invoke-NativeStep "Issue archive consistency" {
        & $python scripts/archive_issues.py --check
    }
    Invoke-NativeStep "App TypeScript" {
        & $node $tsc -b --pretty false
    }
    Invoke-NativeStep "App production build" {
        & $node $vite build
    }
    Invoke-NativeStep "Console TypeScript" {
        & $node $tsc -p tsconfig.console.json --noEmit --pretty false
    }
    Invoke-NativeStep "Console production build" {
        & $node $vite build --config vite.console.config.ts
    }
    Invoke-NativeStep "Local Agent regression" {
        & $python -m unittest @backendRegressionTests
    }
    Invoke-NativeStep "Server unit and contract tests" {
        & $python -m unittest @serverTests
    }
    Invoke-NativeStep "Isolated Server-Local Agent HTTP integration" {
        & $python -m unittest @integrationTests
    }
    Invoke-NativeStep "Tracked Python compilation" {
        & $python scripts/compile_tracked_python.py
    }

    if ($WebE2E) {
        Invoke-NativeStep "Web visual theme and responsive E2E" {
            & $python backend/tests/e2e/visual_theme_check.py
        }
    }
    else {
        Write-Host "[NOT RUN] Web visual E2E. Start the intended App stack and re-run with -WebE2E." -ForegroundColor Yellow
    }

    if ($IsolatedLive) {
        Invoke-NativeStep "Isolated live functional journeys A-E" {
            & $python scripts/run_v1_live_isolated.py
        }
    }
    elseif ($Live) {
        Write-Host "`n[RUN] Live backend preflight" -ForegroundColor Cyan
        try {
            $health = Invoke-RestMethod -Method Get -Uri "$($LiveBaseUrl.TrimEnd('/'))/health" -TimeoutSec 10
        }
        catch {
            throw "[BLOCKED] Live backend is unreachable at $LiveBaseUrl. Start the intended backend before using -Live."
        }
        $passed.Add("Live backend preflight")
        Write-Host "[PASS] Live backend preflight; functional tests use their owner-scoped model DB configuration" -ForegroundColor Green

        $env:AGENTMATE_TEST_BASE = $LiveBaseUrl.TrimEnd('/')
        Invoke-NativeStep "Live functional journeys A-E" {
            & $python backend/tests/functional/run_all.py
        }
    }
    else {
        Write-Host "`n[NOT RUN] Live backend/LLM journeys. Re-run with -IsolatedLive, or use -Live for an already running intended backend." -ForegroundColor Yellow
    }

    if ($DesktopPreflight) {
        $cargo = (Get-Command cargo -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty Source)
        if (-not $cargo) {
            throw "[BLOCKED] Rust cargo is missing; desktop preflight cannot run."
        }
        Invoke-NativeStep "Tauri Rust compile preflight" {
            & $cargo check --manifest-path src-tauri/Cargo.toml
        }
    }
    else {
        Write-Host "[NOT RUN] Desktop Rust preflight. Re-run with -DesktopPreflight." -ForegroundColor Yellow
    }

    Write-Host "`nV1 RC selected gates passed: $($passed.Count)" -ForegroundColor Green
    Write-Host "This verdict covers only the selected lanes. Signed installer, clean-machine install, updater and pilot evidence remain separate release requirements."
}
finally {
    if ($null -eq $previousEmbedDownloadPolicy) {
        Remove-Item Env:AGENTMATE_DISABLE_EMBED_MODEL_DOWNLOAD -ErrorAction SilentlyContinue
    }
    else {
        $env:AGENTMATE_DISABLE_EMBED_MODEL_DOWNLOAD = $previousEmbedDownloadPolicy
    }
    Pop-Location
}
