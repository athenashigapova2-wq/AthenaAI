[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [int[]]$UserStages = @(10, 20, 40, 80, 120),

    [ValidateRange(1, 100)]
    [int]$Loops = 10,

    [ValidateRange(0, 3600)]
    [int]$RampSeconds = 30,

    [ValidateRange(0, 100)]
    [double]$MaxErrorRatePercent = 1,

    [ValidateRange(1, 600000)]
    [double]$MaxP95Ms = 5000,

    [switch]$StopOnBreach,
    [string]$JMeterHome = $env:JMETER_HOME,
    [string]$JavaHome = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$smokeRunner = Join-Path $PSScriptRoot "run-smoke-with-grafana.ps1"
$capacityTimestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$resultPrefix = Join-Path $env:TEMP "athena-jmeter-capacity-results-$capacityTimestamp"
$csvPath = "$resultPrefix.csv"
$jsonPath = "$resultPrefix.json"

if (-not $UserStages.Count) {
    throw "At least one user stage is required."
}
if ($UserStages | Where-Object { $_ -lt 1 -or $_ -gt 1000 }) {
    throw "Every user stage must be between 1 and 1000."
}
if (-not (Test-Path -LiteralPath $smokeRunner)) {
    throw "Missing JMeter runner: $smokeRunner"
}

Push-Location $repoRoot
try {
    docker compose up -d redis api worker influxdb grafana
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to start the capacity-test contour."
    }

    $workerMode = docker compose exec -T worker python -c `
        "from app.config import settings; print(f'{settings.llm_provider}:{str(settings.agent_infrastructure_test_mode).lower()}')"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read worker capacity-test settings."
    }
    $workerMode = ($workerMode | Select-Object -Last 1).Trim()
    if ($workerMode -ne "mock:true") {
        throw (
            "Capacity test requires LLM_PROVIDER=mock and " +
            "AGENT_INFRASTRUCTURE_TEST_MODE=true in the worker; got '$workerMode'."
        )
    }
    Write-Host "Worker isolation verified: LLM_PROVIDER=mock, AGENT_INFRASTRUCTURE_TEST_MODE=true."
}
finally {
    Pop-Location
}

$capacityResults = [System.Collections.Generic.List[object]]::new()

foreach ($users in $UserStages) {
    $scenario = "capacity-${users}u"
    $stageStartedAt = Get-Date
    Write-Host ""
    Write-Host "=== Capacity stage: users=$users ramp=${RampSeconds}s loops=$Loops ==="

    $runnerArguments = @{
        Users = $users
        RampSeconds = $RampSeconds
        Loops = $Loops
        Scenario = $scenario
    }
    if ($JMeterHome) {
        $runnerArguments.JMeterHome = $JMeterHome
    }
    if ($JavaHome) {
        $runnerArguments.JavaHome = $JavaHome
    }
    & $smokeRunner @runnerArguments

    $summaryFile = Get-ChildItem -LiteralPath $env:TEMP -Filter "athena-jmeter-smoke-*.summary.json" |
        Where-Object { $_.LastWriteTime -ge $stageStartedAt.AddSeconds(-2) } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $summaryFile) {
        throw "No summary JSON was produced for stage $users."
    }

    $summary = Get-Content -LiteralPath $summaryFile.FullName -Raw | ConvertFrom-Json
    if ($summary.run_id -notlike "$scenario-*") {
        throw "Unexpected summary '$($summary.run_id)' for stage '$scenario'."
    }

    $breached = (
        [double]$summary.planned_error_rate_percent -gt $MaxErrorRatePercent -or
        [double]$summary.p95_ms -gt $MaxP95Ms
    )
    $capacityResults.Add([pscustomobject]@{
        users = [int]$summary.users
        max_active_users = [int]$summary.max_active_users
        ramp_seconds = [int]$summary.ramp_seconds
        loops = [int]$summary.loops
        planned_e2e = [int]$summary.planned_e2e
        successful_e2e = [int]$summary.successful_e2e
        failed_e2e = [int]$summary.failed_e2e
        missing_e2e = [int]$summary.missing_e2e
        error_rate_percent = [double]$summary.planned_error_rate_percent
        duration_seconds = [double]$summary.duration_seconds
        e2e_p50_ms = [double]$summary.p50_ms
        e2e_p95_ms = [double]$summary.p95_ms
        e2e_p99_ms = [double]$summary.p99_ms
        e2e_throughput_per_second = [double]$summary.e2e_throughput_per_second
        enqueue_p50_ms = [double]$summary.enqueue_p50_ms
        enqueue_p95_ms = [double]$summary.enqueue_p95_ms
        enqueue_p99_ms = [double]$summary.enqueue_p99_ms
        enqueue_throughput_per_second = [double]$summary.enqueue_throughput_per_second
        slo_breached = $breached
        run_id = [string]$summary.run_id
        jtl = [string]$summary.jtl
        summary = $summaryFile.FullName
    })

    $capacityResults | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8
    $capacityResults | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

    if ($breached) {
        Write-Warning "Capacity threshold breached at $users users."
        if ($StopOnBreach) {
            break
        }
    }
}

Write-Host ""
$capacityResults |
    Select-Object users, max_active_users, successful_e2e, failed_e2e, missing_e2e,
        error_rate_percent, e2e_p50_ms, e2e_p95_ms, e2e_p99_ms,
        e2e_throughput_per_second, enqueue_p95_ms, slo_breached |
    Format-Table -AutoSize

$firstBreach = $capacityResults | Where-Object slo_breached | Select-Object -First 1
if ($firstBreach) {
    Write-Warning "First observed threshold breach: $($firstBreach.users) users."
} else {
    Write-Host "No configured threshold was breached. The tested upper bound is $($capacityResults[-1].users) users; it is not yet the system limit."
}
Write-Host "Capacity CSV: $csvPath"
Write-Host "Capacity JSON: $jsonPath"
