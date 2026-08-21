[CmdletBinding()]
param(
    [ValidateRange(1, 50)]
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

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$observabilityEnv = Join-Path $repoRoot "observability\.env"
$testPlan = Join-Path $PSScriptRoot "athena-agent-smoke.jmx"

if (-not $env:LOAD_TEST_ACCESS_TOKEN) {
    throw "LOAD_TEST_ACCESS_TOKEN is missing or expired. Copy a fresh Supabase access token into this PowerShell session first."
}

$tokenProbeUrl = "http://127.0.0.1:8001/api/v1/agent/chat/jobs/00000000-0000-0000-0000-000000000000"
$tokenProbeHeaders = @{
    Authorization = "Bearer $env:LOAD_TEST_ACCESS_TOKEN"
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
$resultFile = Join-Path $env:TEMP "athena-jmeter-smoke-$timestamp.jtl"
$plannedE2ERequests = $Users * $Loops

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
        "-Japplication=athena-agent" `
        "-JtestTitle=Athena agent $Scenario" `
        "-JeventTags=$Scenario"

    if ($LASTEXITCODE -ne 0) {
        throw "JMeter finished with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$results = @(Import-Csv -LiteralPath $resultFile)
$e2eResults = @($results | Where-Object { $_.label -eq "agent_chat_e2e" })
$failedE2E = @($e2eResults | Where-Object { $_.success -ne "true" })
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

Write-Host "Load test completed: e2e=$($e2eResults.Count)/$plannedE2ERequests failed=$($failedE2E.Count) missing=$missingE2E observed_error_rate=$observedErrorRate% planned_error_rate=$plannedErrorRate%"
Write-Host "JTL: $resultFile"
Write-Host "Grafana: http://127.0.0.1:3000/d/athena-jmeter-load-tests"
