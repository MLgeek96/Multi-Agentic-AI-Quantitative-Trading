param(
    [string[]]$Symbols = @("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"),
    [int[]]$Years = @(2020, 2021, 2022, 2023, 2024, 2025),
    [string]$Interval = "1h",
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$downloaderRoot = Join-Path $projectRoot "binance-public-data"
$downloader = Join-Path $downloaderRoot "python\download-kline.py"

function Test-PythonInterpreter {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }

    & $Path -c "import sys" *> $null
    return $LASTEXITCODE -eq 0
}

$pythonCandidates = @()
if ($PythonPath) {
    $pythonCandidates += $PythonPath
}
$pythonCandidates += @(
    (Join-Path $projectRoot ".venv\Scripts\python.exe"),
    (Join-Path $projectRoot ".freqtrade-venv\Scripts\python.exe")
)
$venvPython = $pythonCandidates |
    Where-Object { Test-PythonInterpreter -Path $_ } |
    Select-Object -First 1

if (-not (Test-Path -LiteralPath $downloader)) {
    & git clone https://github.com/binance/binance-public-data.git $downloaderRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to clone Binance's public-data repository."
    }
}

if (-not $venvPython) {
    throw "No working project Python found. Repair .venv or pass -PythonPath with a working interpreter."
}

& $venvPython -c "import pandas" *> $null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install -r (Join-Path $downloaderRoot "python\requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to install the Binance downloader dependencies."
    }
}

$markets = @(
    @{ Type = "spot"; Folder = "spot" },
    @{ Type = "um"; Folder = "usdt_futures" }
)
$yearArguments = @($Years | ForEach-Object { [string]$_ })
$previousStoreDirectory = $env:STORE_DIRECTORY

try {
    foreach ($market in $markets) {
        # STORE_DIRECTORY avoids the official script's interactive -folder prompt,
        # making this safe to rerun: existing files are left in place.
        $env:STORE_DIRECTORY = Join-Path $projectRoot ("datasets\" + $market.Folder)
        $arguments = @(
            $downloader,
            "-t", $market.Type,
            "-s"
        ) + $Symbols + @(
            "-i", $Interval,
            "-y"
        ) + $yearArguments + @(
            "-skip-daily", "1",
            "-c", "1"
        )

        & $venvPython @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Binance download failed for market type $($market.Type)."
        }
    }
}
finally {
    $env:STORE_DIRECTORY = $previousStoreDirectory
}

Write-Host "Download complete. Run scripts\prepare_klines.py next."
