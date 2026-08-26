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
$controlStatePath = Join-Path $glitchRoot 'hermes\control-state.json'
$jobsPath = Join-Path $profileRoot 'cron\jobs.json'
$setupPath = Join-Path $profileRoot 'setup.ps1'
$distributionPath = Join-Path $profileRoot 'distribution.yaml'

foreach ($requiredRoot in @($profileRoot, $glitchRoot)) {
    if (-not (Test-Path -LiteralPath $requiredRoot -PathType Container)) {
        throw "Required reset root is missing: $requiredRoot"
    }
}
foreach ($requiredFile in @($controlStatePath, $setupPath, $distributionPath)) {
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

function New-VerifiedCheckpoint {
    $checkpointRoot = Join-Path $glitchRoot 'hermes-checkpoints'
    $checkpointName = [datetime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
    $checkpointPath = Join-Path $checkpointRoot $checkpointName
    New-Item -ItemType Directory -Force -Path $checkpointPath | Out-Null

    $sources = @(
        [ordered]@{ Path = (Join-Path $profileRoot 'memories'); Destination = 'profile\memories' },
        [ordered]@{ Path = (Join-Path $profileRoot 'plans'); Destination = 'profile\plans' },
        [ordered]@{ Path = (Join-Path $glitchRoot 'hermes\exchange\hermes\supervisor'); Destination = 'backend\supervisor' },
        [ordered]@{ Path = (Join-Path $glitchRoot 'hermes\epoch.json'); Destination = 'backend\epoch.json' },
        [ordered]@{ Path = $distributionPath; Destination = 'profile\distribution.yaml' }
    )
    $entries = [Collections.Generic.List[object]]::new()
    foreach ($source in $sources) {
        $sourcePath = [string]$source.Path
        if (-not (Test-Path -LiteralPath $sourcePath)) { continue }
        $sourceFiles = if (Test-Path -LiteralPath $sourcePath -PathType Container) {
            @(Get-ChildItem -LiteralPath $sourcePath -File -Recurse -Force)
        } else {
            @(Get-Item -LiteralPath $sourcePath -Force)
        }
        foreach ($sourceFile in $sourceFiles) {
            $sourceBytes = $sourceFile.Length
            $sourceHash = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash
            $relative = if (Test-Path -LiteralPath $sourcePath -PathType Container) {
                $sourceFile.FullName.Substring($sourcePath.TrimEnd('\').Length).TrimStart('\')
            } else {
                ''
            }
            $destinationRelative = if ([string]::IsNullOrWhiteSpace($relative)) {
                [string]$source.Destination
            } else {
                Join-Path ([string]$source.Destination) $relative
            }
            $destinationPath = Join-Path $checkpointPath $destinationRelative
            New-Item -ItemType Directory -Force -Path (Split-Path $destinationPath -Parent) | Out-Null
            Copy-Item -LiteralPath $sourceFile.FullName -Destination $destinationPath -Force
            $copiedFile = Get-Item -LiteralPath $destinationPath
            $copiedHash = (Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256).Hash
            if ($copiedFile.Length -ne $sourceBytes -or $copiedHash -ne $sourceHash) {
                throw "Checkpoint copy does not match source: $($sourceFile.FullName)"
            }
            $entries.Add([ordered]@{
                source = $sourceFile.FullName
                checkpoint_relative = $destinationRelative
                bytes = $sourceBytes
                sha256 = $sourceHash
            })
        }
    }

    foreach ($entry in $entries) {
        $checkpointFile = Join-Path $checkpointPath ([string]$entry.checkpoint_relative)
        $copiedFile = Get-Item -LiteralPath $checkpointFile
        $copiedHash = (Get-FileHash -LiteralPath $checkpointFile -Algorithm SHA256).Hash
        if ($copiedFile.Length -ne [long]$entry.bytes -or $copiedHash -ne [string]$entry.sha256) {
            throw "Checkpoint verification failed: $checkpointFile"
        }
    }

    $manifestPath = Join-Path $checkpointPath 'checkpoint-manifest.json'
    [ordered]@{
        schema_version = 'glitch.hermes.epoch_checkpoint.v1'
        created_utc = [datetime]::UtcNow.ToString('o')
        profile = $Profile
        profile_distribution = (Get-Content -LiteralPath $distributionPath -Raw)
        files = @($entries)
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'Checkpoint manifest could not be created.'
    }
    $checkpointBytes = 0
    foreach ($entry in $entries) {
        $checkpointBytes += [long]$entry.bytes
    }
    return [ordered]@{
        path = $checkpointPath
        manifest = $manifestPath
        files = $entries.Count
        bytes = $checkpointBytes
    }
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
$backendTargets = @(
    'intents',
    # Glitch continuously publishes native packets under exchange\glitch.
    # Epoch reset owns only Hermes-produced state; deleting the shared root races
    # the NinjaTrader publisher and can leave the reset incomplete.
    'hermes\exchange\hermes',
    'snapshots',
    'selfcheck',
    'hermes-archives',
    'replay',
    'Telemetry',
    'AccountPeaks.tsv',
    'hermes\control-commands.jsonl',
    'hermes\cycles.jsonl',
    'hermes\epoch.json'
)

$preview = [ordered]@{
    schema_version = 'glitch.hermes.trading_epoch_reset.v4'
    mode = if ($Apply) { 'apply' } else { 'preview' }
    profile = $Profile
    all_jobs_paused = $true
    native_accounts_inspected = $false
    profile_targets = $profileTargets.Count + $profileBackupTargets.Count
    backend_targets = $backendTargets.Count
    preserved = @(
        'Hermes authentication and profile configuration',
        'distributed SOUL, skills, plugin, scripts, and setup',
        'Glitch AI policy, account groups, ratios, runtime policy, licensing, and UI settings',
        'Glitch Journal, TradeLedger, CriticalWarnings, RiskLocks, and AnalyticsBridgeCache',
        'NinjaTrader native accounts, positions, orders, and credentials'
    )
    destroyed = @(
        'all Hermes sessions and native memories',
        'all Hermes cron jobs and cron execution history',
        'all Hermes decision, intent, execution, outcome, learning, prompt, packet, and snapshot backend history'
    )
    operator_handoff = @(
        'Reset the intended NinjaTrader accounts.',
        'Use Glitch Reset Data to clear Journal and Summary statistics.'
    )
    checkpoint_required = $true
    checkpoint_root = (Join-Path $glitchRoot 'hermes-checkpoints')
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

$checkpoint = New-VerifiedCheckpoint

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
foreach ($relative in $backendTargets) {
    $target = Join-Path $glitchRoot $relative
    if (Remove-ResetTarget -Path $target -Root $glitchRoot) {
        $removed.Add($target)
    }
}

$epochId = [guid]::NewGuid().ToString()
$distributionVersion = [regex]::Match(
    (Get-Content -LiteralPath $distributionPath -Raw),
    '(?m)^version:\s*[''"]?([^''"\r\n]+)'
).Groups[1].Value.Trim()
if ([string]::IsNullOrWhiteSpace($distributionVersion)) {
    throw 'Could not resolve the installed profile distribution version.'
}
$epochPath = Join-Path $glitchRoot 'hermes\epoch.json'
New-Item -ItemType Directory -Force -Path (Split-Path $epochPath -Parent) | Out-Null
[ordered]@{
    schema_version = 'glitch.hermes.epoch.v1'
    epoch_id = $epochId
    reset_utc = [datetime]::UtcNow.ToString('o')
    profile_distribution = $distributionVersion
    prior_state_preserved = $false
    reset_scope = 'hermes_backend_only'
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
if ([string]$direct.schedule.expr -ne '* * * * *' -or [string]$learning.schedule.expr -ne '2,32 * * * *') {
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
    schema_version = 'glitch.hermes.trading_epoch_reset.v4'
    mode = 'applied'
    reset_utc = [datetime]::UtcNow.ToString('o')
    epoch_id = $epochId
    profile = $Profile
    distribution_version = $distributionVersion
    removed_targets = $removed.Count
    backup_created = $true
    checkpoint_path = $checkpoint.path
    checkpoint_manifest = $checkpoint.manifest
    checkpoint_files = $checkpoint.files
    checkpoint_bytes = $checkpoint.bytes
    native_accounts_inspected = $false
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
    user_data_preserved = @(
        'Journal.tsv',
        'TradeLedger.tsv',
        'CriticalWarnings.tsv',
        'RiskLocks.tsv',
        'AnalyticsBridgeCache.json',
        'NinjaTrader accounts, positions, and orders'
    )
    operator_handoff = @(
        'Reset the intended NinjaTrader accounts.',
        'Use Glitch Reset Data to clear Journal and Summary statistics.',
        'Reload the Glitch AddOn before re-enabling AI so risk state is rebuilt from the clean peak store.'
    )
} | ConvertTo-Json -Depth 5
