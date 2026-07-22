[CmdletBinding()]
param(
    [string]$Profile = 'glitch',
    [string]$GlitchData = (Join-Path $env:USERPROFILE 'Documents\NinjaTrader 8\GlitchData')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($Profile -ne 'glitch') {
    throw 'This distribution must be installed as the glitch Hermes profile.'
}

$profileRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$expectedRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'hermes\profiles\glitch'))
if ($profileRoot.TrimEnd('\') -ne $expectedRoot.TrimEnd('\')) {
    throw "Run setup from the installed glitch profile: $expectedRoot"
}

function Assert-DistributionIntegrity {
    $manifestPath = Join-Path $profileRoot 'SHA256SUMS'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'SHA256SUMS is missing; reinstall the profile before setup.'
    }

    foreach ($line in Get-Content -LiteralPath $manifestPath) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split '\s{2,}', 2
        if ($parts.Count -ne 2 -or $parts[0] -notmatch '^[0-9A-Fa-f]{64}$') {
            throw "Invalid SHA256SUMS line: $line"
        }
        $relative = $parts[1].Replace('/', '\')
        $path = [IO.Path]::GetFullPath((Join-Path $profileRoot $relative))
        if (-not $path.StartsWith($profileRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Manifest path escapes the profile: $relative"
        }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Distributed file is missing: $relative"
        }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        if ($actual -ne $parts[0].ToUpperInvariant()) {
            throw "Distributed file checksum mismatch: $relative"
        }
    }
}

function Get-HermesJobs {
    $jobsPath = Join-Path $profileRoot 'cron\jobs.json'
    if (-not (Test-Path -LiteralPath $jobsPath -PathType Leaf)) { return @() }
    $document = Get-Content -LiteralPath $jobsPath -Raw | ConvertFrom-Json
    return @($document.jobs)
}

function Get-ScheduleText($job) {
    if ($null -eq $job) { return '' }
    if ($job.schedule.display) { return [string]$job.schedule.display }
    return [string]$job.schedule.expr
}

function Ensure-CronJob {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Schedule,
        [Parameter(Mandatory = $true)][string]$Script,
        [Parameter(Mandatory = $true)][string]$Workdir
    )

    $matches = @(Get-HermesJobs | Where-Object name -eq $Name)
    if ($matches.Count -gt 1) {
        throw "Multiple $Name jobs exist; refusing to guess which one is authoritative."
    }

    $preserveEnabled = $matches.Count -eq 1 -and [bool]$matches[0].enabled
    if ($matches.Count -eq 1) {
        $jobId = [string]$matches[0].id
        & hermes cron edit $jobId --schedule $Schedule --script $Script --no-agent --workdir $Workdir | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not reconcile $Name." }
    }
    else {
        & hermes cron create $Schedule --name $Name --script $Script --no-agent --deliver local --workdir $Workdir | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not create $Name." }
        $created = @(Get-HermesJobs | Where-Object name -eq $Name)
        if ($created.Count -ne 1) { throw "$Name was not created exactly once." }
        $jobId = [string]$created[0].id
        $preserveEnabled = $false
    }

    $current = @(Get-HermesJobs | Where-Object name -eq $Name)
    if ($current.Count -ne 1) { throw "$Name reconciliation did not leave exactly one job." }
    if ($preserveEnabled -and -not [bool]$current[0].enabled) {
        & hermes cron resume $jobId | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not preserve enabled state for $Name." }
    }
    elseif (-not $preserveEnabled -and [bool]$current[0].enabled) {
        & hermes cron pause $jobId | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not leave $Name paused." }
    }

    $verified = @(Get-HermesJobs | Where-Object name -eq $Name)[0]
    if ((Get-ScheduleText $verified) -ne $Schedule `
        -or -not [bool]$verified.no_agent `
        -or [string]$verified.script -ne $Script `
        -or [IO.Path]::GetFullPath([string]$verified.workdir) -ne [IO.Path]::GetFullPath($Workdir) `
        -or [bool]$verified.enabled -ne $preserveEnabled) {
        throw "$Name persisted with the wrong schedule, script, workdir, or enabled state."
    }

    return [ordered]@{ name = $Name; id = $jobId; enabled = $preserveEnabled; schedule = $Schedule }
}

Assert-DistributionIntegrity
$hermesCommand = Get-Command hermes -ErrorAction Stop
$python = Join-Path (Split-Path $hermesCommand.Source -Parent) 'python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Could not locate the Hermes Python runtime: $python"
}

$requiredFiles = @(
    'scripts\run-direct-glitch-cycle.py',
    'scripts\reconcile-hermes-outcomes.py',
    'scripts\run-hermes-learning-cycle.py',
    'scripts\launch-hermes-learning-cycle.py',
    'scripts\ensure-named-sessions.py',
    'plugins\glitch-control\plugin.yaml',
    'plugins\glitch-control\__init__.py'
)
foreach ($relative in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $profileRoot $relative) -PathType Leaf)) {
        throw "Required distribution file is missing: $relative"
    }
}

$exchange = Join-Path ([IO.Path]::GetFullPath($GlitchData)) 'hermes\exchange'
$supervisor = Join-Path $exchange 'hermes\supervisor'
New-Item -ItemType Directory -Force -Path $supervisor | Out-Null
foreach ($stream in @(
    'trade-episodes.jsonl',
    'observations.jsonl',
    'trading-guidance.jsonl',
    'lessons.jsonl',
    'plans.jsonl',
    'daily-journal.jsonl',
    'cognitive-changes.jsonl',
    'build-requests.jsonl',
    'codex-events.jsonl'
)) {
    $streamPath = Join-Path $supervisor $stream
    if (-not (Test-Path -LiteralPath $streamPath)) {
        New-Item -ItemType File -Path $streamPath | Out-Null
    }
}

& hermes -p $Profile plugins enable glitch-control --no-allow-tool-override | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not enable the deterministic Glitch control plugin.' }

& hermes -p $Profile gateway install --start-now --start-on-login
if ($LASTEXITCODE -ne 0) { throw 'Could not install the supervised Glitch Hermes gateway.' }

$previousHermesHome = $env:HERMES_HOME
try {
    $env:HERMES_HOME = $profileRoot
    & $python (Join-Path $profileRoot 'scripts\ensure-named-sessions.py') | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not seed the named chat and trading sessions.' }

    $directJob = Ensure-CronJob `
        -Name 'glitch-direct-operator' `
        -Schedule '* * * * *' `
        -Script 'run-direct-glitch-cycle.py' `
        -Workdir $exchange
    $learningJob = Ensure-CronJob `
        -Name 'glitch-learning-supervisor' `
        -Schedule '*/15 * * * *' `
        -Script 'launch-hermes-learning-cycle.py' `
        -Workdir $exchange
}
finally {
    $env:HERMES_HOME = $previousHermesHome
}

[ordered]@{
    schema_version = 'glitch.hermes.setup.v1'
    profile = $Profile
    distribution_version = '0.0.2.2'
    gateway_supervised = $true
    plugin_enabled = $true
    jobs = @($directJob, $learningJob)
    fresh_install_jobs_paused = (-not $directJob.enabled -and -not $learningJob.enabled)
    activation = 'Use Glitch AI Auto or /trade.'
} | ConvertTo-Json -Depth 5
