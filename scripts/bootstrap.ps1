[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

function Assert-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$InstallHint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found. $InstallHint"
    }
}

function Initialize-EnvironmentFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Template,
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    if (Test-Path -LiteralPath $Destination) {
        Write-Host "Preserved existing $Destination"
        return
    }

    Copy-Item -LiteralPath $Template -Destination $Destination
    Write-Host "Created $Destination from its example"
}

function Get-Sha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $stream = [System.IO.File]::OpenRead((Resolve-Path -LiteralPath $Path))
    try {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([System.BitConverter]::ToString($sha256.ComputeHash($stream))).Replace("-", "")
        }
        finally {
            $sha256.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

Push-Location $projectRoot
try {
    Assert-Command -Name "node" -InstallHint "Install Node.js 22."
    Assert-Command -Name "npm" -InstallHint "Install npm with Node.js 22."
    $nodeMajor = [int]((& node --version).TrimStart("v").Split(".")[0])
    if ($nodeMajor -ne 22) {
        throw "Node.js 22 is required because it matches CI and Vite 6; found $(& node --version). Use .nvmrc to switch versions."
    }

    Initialize-EnvironmentFile -Template ".env.example" -Destination ".env"
    Initialize-EnvironmentFile -Template "backend/.env.example" -Destination "backend/.env"
    Initialize-EnvironmentFile -Template "observability/.env.example" -Destination "observability/.env"

    $npmCache = Join-Path $projectRoot ".npm-cache"
    $npmLockHash = Get-Sha256 -Path "package-lock.json"
    $npmLockMarker = Join-Path $npmCache "athena-package-lock.sha256"
    $frontendDependenciesReady = $false

    if (Test-Path -LiteralPath "node_modules") {
        & npm ls --depth=0 --cache $npmCache --no-audit --no-fund *> $null
        if ($LASTEXITCODE -eq 0) {
            if (-not (Test-Path -LiteralPath $npmLockMarker)) {
                New-Item -ItemType Directory -Path $npmCache -Force | Out-Null
                Set-Content -LiteralPath $npmLockMarker -Value $npmLockHash
                $frontendDependenciesReady = $true
            }
            else {
                $recordedLockHash = (Get-Content -LiteralPath $npmLockMarker -Raw).Trim()
                $frontendDependenciesReady = $recordedLockHash -eq $npmLockHash
            }
        }
    }

    if ($frontendDependenciesReady) {
        Write-Host "Frontend dependencies already match package-lock.json"
    }
    else {
        Write-Host "Installing frontend dependencies..."
        & npm ci --cache $npmCache --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci failed with exit code $LASTEXITCODE. Stop running Vite/Node processes and rerun bootstrap."
        }
        New-Item -ItemType Directory -Path $npmCache -Force | Out-Null
        Set-Content -LiteralPath $npmLockMarker -Value $npmLockHash
    }

    $venvPython = Join-Path $projectRoot ".venv/Scripts/python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $pythonCommand = $null
        $pythonArguments = @()

        if (Get-Command "py" -ErrorAction SilentlyContinue) {
            $candidateVersion = & py -3.11 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $candidateVersion -eq "3.11") {
                $pythonCommand = "py"
                $pythonArguments = @("-3.11")
            }
        }

        if (-not $pythonCommand -and (Get-Command "python" -ErrorAction SilentlyContinue)) {
            $candidateVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            $candidateParts = $candidateVersion.Split(".")
            if (
                $LASTEXITCODE -eq 0 `
                    -and [int]$candidateParts[0] -eq 3 `
                    -and [int]$candidateParts[1] -ge 11 `
                    -and [int]$candidateParts[1] -le 13
            ) {
                $pythonCommand = "python"
            }
        }

        if (-not $pythonCommand) {
            throw "Python 3.11-3.13 was not found. Python 3.11 is recommended because it matches CI and Docker."
        }

        Write-Host "Creating Python virtual environment..."
        & $pythonCommand @pythonArguments -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            throw "Python virtual environment creation failed with exit code $LASTEXITCODE."
        }
    }
    else {
        Write-Host "Reusing existing .venv"
    }

    $venvPythonVersion = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    $venvVersionParts = $venvPythonVersion.Split(".")
    if (
        [int]$venvVersionParts[0] -ne 3 `
            -or [int]$venvVersionParts[1] -lt 11 `
            -or [int]$venvVersionParts[1] -gt 13
    ) {
        throw "The existing .venv uses unsupported Python $venvPythonVersion. Use Python 3.11-3.13."
    }

    Write-Host "Installing backend development dependencies..."
    & $venvPython -m pip install -r "backend/requirements-dev.txt"
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependency installation failed with exit code $LASTEXITCODE."
    }

    Write-Host ""
    Write-Host "Bootstrap complete. Review the three local .env files, then run:"
    Write-Host "  docker compose up -d --build"
    Write-Host "  npm run dev"
}
finally {
    Pop-Location
}
