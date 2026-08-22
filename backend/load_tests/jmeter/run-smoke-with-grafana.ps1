[CmdletBinding()]
param(
    [ValidateRange(1, 1000)]
    [int]$Users = 5,

    [ValidateRange(0, 3600)]
    [int]$RampSeconds = 30,

    [ValidateRange(1, 100)]
    [int]$Loops = 5,

    [ValidatePattern('^[a-zA-Z0-9_-]+$')]
    [string]$Scenario = "baseline-5x5",

    [string]$JMeterHome = $env:JMETER_HOME,
    [string]$JavaHome = ""
)

$ErrorActionPreference = "Stop"

function Get-NearestRankPercentile {
    param(
        [Parameter(Mandatory)]
        [double[]]$Values,

        [Parameter(Mandatory)]
        [ValidateRange(0.01, 100)]
        [double]$Percentile
    )

    if (-not $Values.Count) {
        throw "Cannot calculate percentile from an empty sample set."
    }

    $sorted = @($Values | Sort-Object)
    $rank = [math]::Ceiling(($Percentile / 100.0) * $sorted.Count)
    return $sorted[[math]::Max(0, $rank - 1)]
}

function Get-JwtExpirationUtc {
    param(
        [Parameter(Mandatory)]
        [string]$Jwt
    )

    try {
        $payload = ($Jwt -split '\.')[1].Replace('-', '+').Replace('_', '/')
        switch ($payload.Length % 4) {
            2 { $payload += '==' }
            3 { $payload += '=' }
        }
        $claimsJson = [Text.Encoding]::UTF8.GetString(
            [Convert]::FromBase64String($payload)
        )
        $claims = $claimsJson | ConvertFrom-Json
        if (-not $claims.exp) {
            throw "JWT does not contain exp."
        }
        return [DateTimeOffset]::FromUnixTimeSeconds([long]$claims.exp)
    }
    catch {
        throw "LOAD_TEST_ACCESS_TOKEN payload cannot be decoded: $($_.Exception.Message)"
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$observabilityEnv = Join-Path $repoRoot "observability\.env"
$testPlan = Join-Path $PSScriptRoot "athena-agent-smoke.jmx"

if (-not $env:LOAD_TEST_ACCESS_TOKEN) {
    throw "LOAD_TEST_ACCESS_TOKEN is missing or expired. Copy a fresh Supabase access token into this PowerShell session first."
}

# DevTools can add wrappers, line breaks, non-breaking spaces, or invisible
# Unicode formatting characters to a copied Authorization value. Remove those
# characters and extract exactly one Supabase JWT instead of trusting the whole
# clipboard value to be the token.
$tokenSource = $env:LOAD_TEST_ACCESS_TOKEN.Trim()
$tokenSource = $tokenSource -replace '[\p{C}\p{Z}]', ''
$jwtMatches = [regex]::Matches(
    $tokenSource,
    '(?<jwt>eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)(?![A-Za-z0-9_-])'
)

if ($jwtMatches.Count -ne 1) {
    throw "LOAD_TEST_ACCESS_TOKEN must contain exactly one valid three-segment JWT. Copy a fresh Authorization value from DevTools."
}

$accessToken = $jwtMatches[0].Groups['jwt'].Value

$env:LOAD_TEST_ACCESS_TOKEN = $accessToken

# Avoid treating token expiry in the middle of a stage as backend overload.
$tokenExpiresAt = Get-JwtExpirationUtc -Jwt $accessToken
$requiredTokenLifetimeSeconds = [math]::Max(
    180,
    $RampSeconds + ($Loops * 5) + 60
)
$tokenLifetimeSeconds = ($tokenExpiresAt - [DateTimeOffset]::UtcNow).TotalSeconds
if ($tokenLifetimeSeconds -lt $requiredTokenLifetimeSeconds) {
    throw (
        "LOAD_TEST_ACCESS_TOKEN expires too soon for this stage. " +
        "Remaining=$([math]::Floor($tokenLifetimeSeconds))s, " +
        "required=${requiredTokenLifetimeSeconds}s. Copy a fresh token."
    )
}
Write-Host "Token lifetime check passed: $([math]::Floor($tokenLifetimeSeconds))s remaining."

$tokenProbeUrl = "http://127.0.0.1:8001/api/v1/agent/chat/jobs/00000000-0000-0000-0000-000000000000"
$tokenProbeHeaders = @{
    Authorization = "Bearer $accessToken"
}
$tokenProbeStatus = $null

try {
    Invoke-RestMethod `
        -Uri $tokenProbeUrl `
        -Headers $tokenProbeHeaders `
        -Method Get `
        -ErrorAction Stop | Out-Null
    $tokenProbeStatus = 200
}
catch {
    if ($null -ne $_.Exception.Response -and $null -ne $_.Exception.Response.StatusCode) {
        $tokenProbeStatus = [int]$_.Exception.Response.StatusCode
    }
    else {
        throw "FastAPI token preflight failed: $($_.Exception.Message)"
    }
}

if ($tokenProbeStatus -eq 401) {
    throw "LOAD_TEST_ACCESS_TOKEN is invalid or expired. Copy a fresh token before starting JMeter."
}
if ($tokenProbeStatus -ne 404) {
    throw "FastAPI token preflight returned unexpected HTTP $tokenProbeStatus (expected 404 for the probe job)."
}

Write-Host "Token preflight passed (authenticated probe returned expected HTTP 404)."

if (-not (Select-String -LiteralPath $testPlan -SimpleMatch "InfluxDB Backend Listener" -Quiet)) {
    throw "The JMeter plan does not contain the InfluxDB Backend Listener. Do not run it until the listener is restored."
}

if (-not (Test-Path -LiteralPath $observabilityEnv)) {
    throw "Missing $observabilityEnv. Copy observability/.env.example to observability/.env and set local credentials."
}

$influxTokenLine = Get-Content -LiteralPath $observabilityEnv |
    Where-Object { $_ -match '^INFLUXDB_TOKEN=' } |
    Select-Object -First 1

if (-not $influxTokenLine) {
    throw "INFLUXDB_TOKEN is missing in observability/.env."
}

$env:INFLUXDB_TOKEN = ($influxTokenLine -split '=', 2)[1].Trim()

if (-not $JavaHome) {
    $jdk17 = Get-ChildItem -LiteralPath "C:\Program Files\Eclipse Adoptium" -Directory -Filter "jdk-17*" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if ($jdk17) {
        $JavaHome = $jdk17.FullName
    }
}

if (-not $JavaHome -or -not (Test-Path -LiteralPath (Join-Path $JavaHome "bin\java.exe"))) {
    throw "Java 17 was not found. Pass -JavaHome or install Temurin JDK 17."
}

if (-not $JMeterHome) {
    $jmeter = Get-ChildItem -LiteralPath (Join-Path $env:USERPROFILE "Downloads") -Directory -Filter "apache-jmeter-*" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Get-ChildItem -LiteralPath $_.FullName -Directory -Filter "apache-jmeter-*" -ErrorAction SilentlyContinue
        } |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "bin\jmeter.bat") } |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if ($jmeter) {
        $JMeterHome = $jmeter.FullName
    }
}

if (-not $JMeterHome) {
    throw "JMeter was not found. Set JMETER_HOME or pass -JMeterHome."
}

$jmeterBat = Join-Path $JMeterHome "bin\jmeter.bat"
if (-not (Test-Path -LiteralPath $jmeterBat)) {
    throw "JMeter was not found. Set JMETER_HOME or pass -JMeterHome."
}

$env:JM_LAUNCH = Join-Path $JavaHome "bin\java.exe"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runId = "$Scenario-$timestamp"
$application = "athena-agent-$runId"
$resultFile = Join-Path $env:TEMP "athena-jmeter-smoke-$timestamp.jtl"
$summaryFile = Join-Path $env:TEMP "athena-jmeter-smoke-$timestamp.summary.json"
$plannedE2ERequests = $Users * $Loops

Write-Host "Run ID: $runId"
Write-Host "Load profile: users=$Users ramp=${RampSeconds}s loops=$Loops planned_e2e=$plannedE2ERequests"

Push-Location $repoRoot
try {
    docker compose up -d influxdb grafana
    & $jmeterBat `
        -n `
        -t $testPlan `
        -l $resultFile `
        "-Jusers=$Users" `
        "-JrampSeconds=$RampSeconds" `
        "-Jloops=$Loops" `
        "-Japplication=$application" `
        "-JtestTitle=Athena agent $runId" `
        "-JeventTags=$runId"

    if ($LASTEXITCODE -ne 0) {
        throw "JMeter finished with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$results = @(Import-Csv -LiteralPath $resultFile)
$e2eResults = @($results | Where-Object { $_.label -eq "agent_chat_e2e" })
$enqueueResults = @($results | Where-Object { $_.label -eq "POST agent/chat enqueue" })
$failedE2E = @($e2eResults | Where-Object { $_.success -ne "true" })
$httpResults = @(
    $results | Where-Object {
        $_.label -eq "POST agent/chat enqueue" -or
        $_.label -eq "GET agent/chat/jobs/{job_id} poll"
    }
)
$missingE2E = [math]::Max(0, $plannedE2ERequests - $e2eResults.Count)
$observedErrorRate = if ($e2eResults.Count) {
    [math]::Round(($failedE2E.Count / $e2eResults.Count) * 100, 2)
} else {
    100
}
$plannedErrorRate = [math]::Round(
    (($failedE2E.Count + $missingE2E) / $plannedE2ERequests) * 100,
    2
)

if (-not $e2eResults.Count) {
    throw "JMeter produced no agent_chat_e2e samples. Inspect $resultFile and jmeter.log."
}

$e2eElapsedMs = @($e2eResults | ForEach-Object { [double]$_.elapsed })
$enqueueElapsedMs = @($enqueueResults | ForEach-Object { [double]$_.elapsed })
$testStartMs = [double](
    $results | Measure-Object -Property timeStamp -Minimum
).Minimum
$testEndMs = [double](
    $results |
        ForEach-Object { [double]$_.timeStamp + [double]$_.elapsed } |
        Measure-Object -Maximum
).Maximum
$maxActiveUsers = [int](
    $results |
        ForEach-Object { [int]$_.allThreads } |
        Measure-Object -Maximum
).Maximum
$durationSeconds = ($testEndMs - $testStartMs) / 1000.0
$p50Ms = Get-NearestRankPercentile -Values $e2eElapsedMs -Percentile 50
$p95Ms = Get-NearestRankPercentile -Values $e2eElapsedMs -Percentile 95
$p99Ms = Get-NearestRankPercentile -Values $e2eElapsedMs -Percentile 99
$enqueueP50Ms = Get-NearestRankPercentile -Values $enqueueElapsedMs -Percentile 50
$enqueueP95Ms = Get-NearestRankPercentile -Values $enqueueElapsedMs -Percentile 95
$enqueueP99Ms = Get-NearestRankPercentile -Values $enqueueElapsedMs -Percentile 99
$e2eThroughput = $e2eResults.Count / $durationSeconds
$enqueueThroughput = $enqueueResults.Count / $durationSeconds
$httpThroughput = $httpResults.Count / $durationSeconds

$summary = [ordered]@{
    run_id = $runId
    application = $application
    users = $Users
    max_active_users = $maxActiveUsers
    ramp_seconds = $RampSeconds
    loops = $Loops
    planned_e2e = $plannedE2ERequests
    observed_e2e = $e2eResults.Count
    successful_e2e = $e2eResults.Count - $failedE2E.Count
    failed_e2e = $failedE2E.Count
    missing_e2e = $missingE2E
    observed_error_rate_percent = $observedErrorRate
    planned_error_rate_percent = $plannedErrorRate
    duration_seconds = [math]::Round($durationSeconds, 3)
    p50_ms = [math]::Round($p50Ms)
    p95_ms = [math]::Round($p95Ms)
    p99_ms = [math]::Round($p99Ms)
    e2e_throughput_per_second = [math]::Round($e2eThroughput, 3)
    enqueue_requests = $enqueueResults.Count
    enqueue_p50_ms = [math]::Round($enqueueP50Ms)
    enqueue_p95_ms = [math]::Round($enqueueP95Ms)
    enqueue_p99_ms = [math]::Round($enqueueP99Ms)
    enqueue_throughput_per_second = [math]::Round($enqueueThroughput, 3)
    http_requests = $httpResults.Count
    http_throughput_per_second = [math]::Round($httpThroughput, 3)
    jtl = $resultFile
}
$summary | ConvertTo-Json | Set-Content -LiteralPath $summaryFile -Encoding UTF8

$grafanaFromMs = [long][math]::Max(
    [double]0,
    [double]($testStartMs - 5000)
)
$grafanaToMs = [long]($testEndMs + 5000)
$encodedApplication = [uri]::EscapeDataString($application)
$grafanaUrl = "http://127.0.0.1:3000/d/athena-jmeter-load-tests?orgId=1&from=$grafanaFromMs&to=$grafanaToMs&var-application=$encodedApplication&refresh=5s"

Write-Host "Load test completed: e2e=$($e2eResults.Count)/$plannedE2ERequests failed=$($failedE2E.Count) missing=$missingE2E observed_error_rate=$observedErrorRate% planned_error_rate=$plannedErrorRate%"
Write-Host "Concurrency: configured_users=$Users max_active_users=$maxActiveUsers"
Write-Host "E2E metrics: duration=$([math]::Round($durationSeconds, 3))s p50=$([math]::Round($p50Ms))ms p95=$([math]::Round($p95Ms))ms p99=$([math]::Round($p99Ms))ms throughput=$([math]::Round($e2eThroughput, 3))/s"
Write-Host "Enqueue metrics: p50=$([math]::Round($enqueueP50Ms))ms p95=$([math]::Round($enqueueP95Ms))ms p99=$([math]::Round($enqueueP99Ms))ms throughput=$([math]::Round($enqueueThroughput, 3))/s"
Write-Host "JTL: $resultFile"
Write-Host "Summary: $summaryFile"
Write-Host "Grafana (this run only): $grafanaUrl"
