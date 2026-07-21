param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^WB-\d{3}$')]
    [string]$IssueId,

    [string[]]$ForbiddenPattern = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-GitReadOnly {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = @(& git @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed:`n$($output -join [Environment]::NewLine)"
    }
    return $output
}

function Add-Failure {
    param([Parameter(Mandatory = $true)][string]$Message)
    $script:failures.Add($Message)
}

$repoRoot = (Invoke-GitReadOnly -Arguments @('rev-parse', '--show-toplevel') | Select-Object -First 1).Trim()
Push-Location -LiteralPath $repoRoot
try {
    $failures = [System.Collections.Generic.List[string]]::new()
    $stagedNames = @(@(Invoke-GitReadOnly -Arguments @('diff', '--cached', '--name-only')) |
        Where-Object { $_ -and $_.Trim() })

    if ($stagedNames.Count -eq 0) {
        Add-Failure 'The staged index is empty.'
    }

    $sensitivePath = '(?i)(^|/)(\.env|node_modules|\.venv|workspace)(/|$)|\.db(?:-[^/]*)?$|\.png$|(^|/)\.playwright'
    $sensitiveFiles = @($stagedNames | Where-Object { $_ -match $sensitivePath })
    if ($sensitiveFiles.Count -gt 0) {
        Add-Failure "Sensitive or runtime files are staged: $($sensitiveFiles -join ', ')"
    }

    $otherIssueFiles = [System.Collections.Generic.List[string]]::new()
    foreach ($path in $stagedNames) {
        if ($path -match '^docs/issues/(WB-\d{3})-.*\.md$' -and $Matches[1] -ne $IssueId) {
            $otherIssueFiles.Add($path)
        }
    }
    if ($otherIssueFiles.Count -gt 0) {
        Add-Failure "Issue files for a different issue are staged: $($otherIssueFiles -join ', ')"
    }

    $readmeDiff = @(Invoke-GitReadOnly -Arguments @(
        'diff', '--cached', '--unified=0', '--', 'docs/issues/README.md'
    ))
    $otherReadmeIds = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($line in $readmeDiff) {
        if ($line -match '^[+-]\| \[(WB-\d{3})\]' -and $Matches[1] -ne $IssueId) {
            [void]$otherReadmeIds.Add($Matches[1])
        }
    }
    if ($otherReadmeIds.Count -gt 0) {
        Add-Failure "README rows for a different issue are staged: $(@($otherReadmeIds) -join ', ')"
    }

    $issueFilesById = @{}
    foreach ($file in Get-ChildItem -LiteralPath 'docs/issues' -File -Filter 'WB-*.md') {
        if ($file.Name -match '^(WB-\d{3})-.*\.md$') {
            $id = $Matches[1]
            if (-not $issueFilesById.ContainsKey($id)) { $issueFilesById[$id] = @() }
            $issueFilesById[$id] += $file.Name
        }
    }
    foreach ($entry in $issueFilesById.GetEnumerator()) {
        if ($entry.Value.Count -gt 1) {
            Add-Failure "Duplicate issue file id $($entry.Key): $($entry.Value -join ', ')"
        }
    }

    $readmeLinesById = @{}
    foreach ($line in Get-Content -LiteralPath 'docs/issues/README.md' -Encoding UTF8) {
        if ($line -match '^\| \[(WB-\d{3})\]') {
            $id = $Matches[1]
            if (-not $readmeLinesById.ContainsKey($id)) { $readmeLinesById[$id] = 0 }
            $readmeLinesById[$id]++
        }
    }
    foreach ($entry in $readmeLinesById.GetEnumerator()) {
        if ($entry.Value -gt 1) {
            Add-Failure "Duplicate README issue id $($entry.Key): $($entry.Value) rows"
        }
    }

    if (-not $issueFilesById.ContainsKey($IssueId)) {
        Add-Failure "No issue file found for $IssueId."
    }
    if (-not $readmeLinesById.ContainsKey($IssueId)) {
        Add-Failure "No README row found for $IssueId."
    }

    if ($issueFilesById.ContainsKey($IssueId) -and $readmeLinesById.ContainsKey($IssueId)) {
        $issuePath = Join-Path 'docs/issues' $issueFilesById[$IssueId][0]
        $issueText = Get-Content -LiteralPath $issuePath -Raw -Encoding UTF8
        if ($issueText -notmatch '(?m)^status:\s*(open|in-progress|fixed|deferred|wontfix)\s*$') {
            Add-Failure "$IssueId frontmatter has no valid status."
        } else {
            $status = $Matches[1]
            $yellowCircle = [string]::Concat([char]0xD83D, [char]0xDFE1)
            $statusEmoji = @{
                'open'        = [string][char]0x2B1C
                'in-progress' = $yellowCircle
                'fixed'       = [string][char]0x2705
                'deferred'    = [string][char]0x23F8
                'wontfix'     = [string][char]0x26D4
            }
            $readmeLine = Get-Content -LiteralPath 'docs/issues/README.md' -Encoding UTF8 |
                Where-Object { $_ -match "^\| \[$([regex]::Escape($IssueId))\]" } |
                Select-Object -First 1
            if ($readmeLine -notmatch "\| $([regex]::Escape($statusEmoji[$status])) \|") {
                Add-Failure "$IssueId status is not mirrored: frontmatter=$status, README expected $($statusEmoji[$status])."
            }
        }
    }

    $cachedDiff = @(Invoke-GitReadOnly -Arguments @('diff', '--cached', '--unified=0'))
    foreach ($pattern in $ForbiddenPattern) {
        if ($cachedDiff -match $pattern) {
            Add-Failure "The staged diff matches forbidden pattern: $pattern"
        }
    }

    $whitespaceErrors = @(& git diff --cached --check 2>&1)
    if ($LASTEXITCODE -ne 0) {
        Add-Failure "git diff --cached --check failed:`n$($whitespaceErrors -join [Environment]::NewLine)"
    }

    Write-Output "Audited issue: $IssueId"
    Write-Output 'Staged files:'
    $stagedNames | ForEach-Object { Write-Output "  $_" }
    Write-Output 'Staged diff stat:'
    Invoke-GitReadOnly -Arguments @('diff', '--cached', '--stat') | ForEach-Object { Write-Output "  $_" }

    if ($failures.Count -gt 0) {
        $failures | ForEach-Object { Write-Error $_ }
        exit 1
    }

    Write-Output 'PASS: read-only staged-index audit passed. Review every hunk in git diff --cached before committing.'
} finally {
    Pop-Location
}
