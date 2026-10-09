[CmdletBinding()]
param(
    [string]$Config = "config\daily_portfolio.json"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Runner = Join-Path $ProjectRoot "scripts\run_daily_portfolio.py"
$ConfigPath = Join-Path $ProjectRoot $Config
$LogDirectory = Join-Path $ProjectRoot "live\logs"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment not found at $Python. Recreate .venv and install requirements.txt."
}

New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Log = Join-Path $LogDirectory "daily-$Timestamp.log"

Push-Location $ProjectRoot
try {
    & $Python $Runner --config $ConfigPath *>&1 | Tee-Object -FilePath $Log
    if ($LASTEXITCODE -ne 0) {
        throw "Daily portfolio runner failed with exit code $LASTEXITCODE. See $Log"
    }
}
finally {
    Pop-Location
}
