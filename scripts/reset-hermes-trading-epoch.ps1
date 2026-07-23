[CmdletBinding()]
param(
    [string]$Profile = 'glitch',
    [string]$GlitchData = (Join-Path $env:USERPROFILE 'Documents\NinjaTrader 8\GlitchData'),
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($Profile -ne 'glitch') {
    throw 'Only the installed glitch Hermes profile may be reset by this script.'
}

$profileRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'hermes\profiles\glitch'))
$glitchRoot = [IO.Path]::GetFullPath($GlitchData)
$snapshotPath = Join-Path $glitchRoot 'snapshots\portfolio\latest.json'
$controlStatePath = Join-Path $glitchRoot 'hermes\control-state.json'
$jobsPath = Join-Path $profileRoot 'cron\jobs.json'
$setupPath = Join-Path $profileRoot 'setup.ps1'

foreach ($requiredRoot in @($profileRoot, $glitchRoot)) {
    if (-not (Test-Path -LiteralPath $requiredRoot -PathType Container)) {
        throw "Required reset root is missing: $requiredRoot"
    }
}
foreach ($requiredFile in @($snapshotPath, $controlStatePath, $setupPath)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required reset precondition file is missing: $requiredFile"
    }
}

function Assert-ChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )

    $fullPath = [IO.Path]::GetFullPath($Path)
    $fullRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if (-not $fullPath.StartsWith($fullRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing reset target outside the expected root: $fullPath"
    }
    return $fullPath
}

function Remove-ResetTarget {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )

    $target = Assert-ChildPath -Path $Path -Root $Root
    if (-not (Test-Path -LiteralPath $target)) { return $false }
    Remove-Item -LiteralPath $target -Recurse -Force
    if (Test-Path -LiteralPath $target) {
        throw "Reset target could not be removed: $target"
    }
    return $true
}

function Get-HermesJobs {
    if (-not (Test-Path -LiteralPath $jobsPath -PathType Leaf)) { return @() }
    return @((Get-Content -LiteralPath $jobsPath -Raw | ConvertFrom-Json).jobs)
}

$controlState = Get-Content -LiteralPath $controlStatePath -Raw | ConvertFrom-Json
if (-not [bool]$controlState.trading_paused) {
    throw 'AI trading must be paused before resetting the epoch.'
}

$jobs = @(Get-HermesJobs)
$enabledJobs = @($jobs | Where-Object {
    [bool]$_.enabled -or [string]$_.state -eq 'active'
})
if ($enabledJobs.Count -gt 0) {
    throw ('Every Hermes job must be paused before reset: ' + (($enabledJobs | ForEach-Object name) -join ', '))
}

$portfolio = Get-Content -LiteralPath $snapshotPath -Raw | ConvertFrom-Json
$snapshotUtc = [datetime]::Parse([string]$portfolio.created_utc).ToUniversalTime()
if (([datetime]::UtcNow - $snapshotUtc).TotalMinutes -gt 3) {
    throw "Portfolio snapshot is stale: $($portfolio.created_utc)"
}
$accounts = @($portfolio.accounts)
if ($accounts.Count -eq 0) {
    throw 'Portfolio snapshot contains no accounts.'
}
$unsafeAccounts = @($accounts | Where-Object {
    @($_.positions).Count -gt 0 -or [int]$_.working_orders -gt 0
})
if ($unsafeAccounts.Count -gt 0) {
    throw ('Every observed account must be flat and order-free: ' + (($unsafeAccounts | ForEach-Object account) -join ', '))
}

$profileTargets = @(
    'audio_cache',
    'cache',
    'cron',
    'image_cache',
    'logs',
    'memories',
    'plans',
    'sandboxes',
    'sessions',
    'state',
    'workspace',
    'state.db',
    'state.db-shm',
    'state.db-wal',
    'verification_evidence.db',
    '.hermes_history',
    'gateway-starts.log'
)
$profileBackupTargets = @(
    Get-ChildItem -LiteralPath $profileRoot -Force |
        Where-Object { $_.Name -match '^(memories|skills)\.pre-' -or $_.Name -match '^(SOUL|\.env)\.pre-' } |
        ForEach-Object FullName
)
$glitchTargets = @(
    'intents',
    'hermes\exchange',
    'snapshots',
    'selfcheck',
    'hermes-archives',
    'replay',
    'Telemetry',
    'Journal.tsv',
    'TradeLedger.tsv',
    'CriticalWarnings.tsv',
    'RiskLocks.tsv',
    'AccountPeaks.tsv',
    'AnalyticsBridgeCache.json',
    'hermes\control-commands.jsonl',
    'hermes\cycles.jsonl',
    'hermes\epoch.json'
)

$preview = [ordered]@{
    schema_version = 'glitch.hermes.trading_epoch_reset.v3'
    mode = if ($Apply) { 'apply' } else { 'preview' }
    profile = $Profile
    portfolio_snapshot_utc = $portfolio.created_utc
    observed_accounts = $accounts.Count
    all_accounts_flat_and_order_free = $true
    all_jobs_paused = $true
    profile_targets = $profileTargets.Count + $profileBackupTargets.Count
    glitch_targets = $glitchTargets.Count
    preserved = @(
        'Hermes authentication and profile configuration',
        'distributed SOUL, skills, plugin, scripts, and setup',
        'Glitch AI policy, account groups, ratios, runtime policy, licensing, and UI settings',
        'NinjaTrader native accounts and credentials'
    )
    destroyed = @(
        'all Hermes sessions and native memories',
        'all Hermes cron jobs and cron execution history',
        'all Glitch decision, intent, execution, outcome, learning, prompt, packet, and snapshot history',
        'Glitch Journal, TradeLedger, warnings, locks, analytics cache, and AccountPeaks'
    )
    backup_created = $false
}

if (-not $Apply) {
    $preview | ConvertTo-Json -Depth 5
    return
}

& hermes -p $Profile gateway stop | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Could not stop the Glitch Hermes gateway before reset.'
}

$removed = [Collections.Generic.List[string]]::new()
foreach ($relative in $profileTargets) {
    $target = Join-Path $profileRoot $relative
    if (Remove-ResetTarget -Path $target -Root $profileRoot) {
        $removed.Add($target)
    }
}
foreach ($target in $profileBackupTargets) {
    if (Remove-ResetTarget -Path $target -Root $profileRoot) {
        $removed.Add($target)
    }
}
foreach ($relative in $glitchTargets) {
    $target = Join-Path $glitchRoot $relative
    if (Remove-ResetTarget -Path $target -Root $glitchRoot) {
        $removed.Add($target)
    }
}

$epochId = [guid]::NewGuid().ToString()
$epochPath = Join-Path $glitchRoot 'hermes\epoch.json'
New-Item -ItemType Directory -Force -Path (Split-Path $epochPath -Parent) | Out-Null
[ordered]@{
    schema_version = 'glitch.hermes.epoch.v1'
    epoch_id = $epochId
    reset_utc = [datetime]::UtcNow.ToString('o')
    profile_distribution = '0.0.2.9'
    prior_state_preserved = $false
} | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $epochPath -Encoding utf8

& powershell -NoProfile -ExecutionPolicy Bypass -File $setupPath -Profile $Profile -GlitchData $glitchRoot | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Clean profile setup failed after reset; AI remains paused.'
}

$freshJobs = @(Get-HermesJobs)
$expectedJobs = @('glitch-direct-operator', 'glitch-learning-supervisor')
if ($freshJobs.Count -ne 2) {
    throw "Reset setup created $($freshJobs.Count) jobs instead of exactly two."
}
foreach ($expected in $expectedJobs) {
    $match = @($freshJobs | Where-Object name -eq $expected)
    if ($match.Count -ne 1 -or [bool]$match[0].enabled -or [string]$match[0].state -ne 'paused') {
        throw "Reset setup did not leave $expected exactly once and paused."
    }
}
$direct = @($freshJobs | Where-Object name -eq 'glitch-direct-operator')[0]
$learning = @($freshJobs | Where-Object name -eq 'glitch-learning-supervisor')[0]
if ([string]$direct.schedule.expr -ne '* * * * *' -or [string]$learning.schedule.expr -ne '*/30 * * * *') {
    throw 'Reset setup created an unexpected cron schedule.'
}

$memoryFiles = @(
    Get-ChildItem -LiteralPath (Join-Path $profileRoot 'memories') -File -ErrorAction SilentlyContinue |
        Where-Object Length -gt 0
)
$requestDumps = @(
    Get-ChildItem -LiteralPath (Join-Path $profileRoot 'sessions') -Filter 'request_dump_*.json' `
        -File -Recurse -ErrorAction SilentlyContinue
)
if ($memoryFiles.Count -gt 0 -or $requestDumps.Count -gt 0) {
    throw 'Fresh setup unexpectedly recreated non-empty memory or prompt dumps; AI remains paused.'
}

[ordered]@{
    schema_version = 'glitch.hermes.trading_epoch_reset.v3'
    mode = 'applied'
    reset_utc = [datetime]::UtcNow.ToString('o')
    epoch_id = $epochId
    profile = $Profile
    distribution_version = '0.0.2.9'
    removed_targets = $removed.Count
    backup_created = $false
    all_accounts_were_flat_and_order_free = $true
    memory_files_with_content = $memoryFiles.Count
    request_dumps = $requestDumps.Count
    cron_jobs = @($freshJobs | ForEach-Object {
        [ordered]@{
            name = $_.name
            schedule = $_.schedule.expr
            enabled = [bool]$_.enabled
        }
    })
    ai_remains_paused = $true
    addon_reload_required_for_account_peak_memory = $true
} | ConvertTo-Json -Depth 5
