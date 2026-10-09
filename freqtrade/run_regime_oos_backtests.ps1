$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ProjectRoot
$FreqtradeExe = Join-Path $RepositoryRoot ".freqtrade-venv\Scripts\freqtrade.exe"
$PythonExe = Join-Path $RepositoryRoot ".freqtrade-venv\Scripts\python.exe"
$UserData = Join-Path $ProjectRoot "user_data"
$Results = Join-Path $UserData "backtest_results"
$Timerange = "20250101-20260918"

Push-Location $RepositoryRoot
try {
    & $PythonExe "$UserData\scripts\import_local_data.py" `
        --source "$RepositoryRoot\processed\usdt_futures" `
        --destination "$UserData\data\binanceusdm\futures" `
        --symbols BTCUSDT ETHUSDT
    if ($LASTEXITCODE -ne 0) { throw "Hourly data import failed." }

    & $PythonExe "$UserData\scripts\fit_regime_hmm.py" `
        --source "$RepositoryRoot\processed\usdt_futures" `
        --output "$UserData\regime_models" `
        --symbols BTCUSDT ETHUSDT
    if ($LASTEXITCODE -ne 0) { throw "Frozen HMM fit failed." }

    $Runs = @(
        @{ Config = "config_hmm_regime.json"; Strategy = "HMMRegimeSwitchingStrategy"; Note = "hmm-regime-oos-2025-2026" },
        @{ Config = "config_hmm_regime.json"; Strategy = "HMMRegimeDefensiveStrategy"; Note = "hmm-defensive-oos-2025-2026" },
        @{ Config = "config_hmm_regime.json"; Strategy = "HMMTrendOnlyStrategy"; Note = "hmm-trend-only-oos-2025-2026" },
        @{ Config = "config_hmm_regime.json"; Strategy = "HMMTrendOnlyDefensiveStrategy"; Note = "hmm-trend-defensive-oos-2025-2026" },
        @{ Config = "config_baseline.json"; Strategy = "BollingerBreakout40D"; Note = "bollinger-control-oos-2025-2026" }
    )

    foreach ($Run in $Runs) {
        & $FreqtradeExe backtesting `
            --userdir $UserData `
            --config "$UserData\$($Run.Config)" `
            --strategy $Run.Strategy `
            --timerange $Timerange `
            --fee 0.001 `
            --export trades `
            --backtest-directory $Results `
            --notes $Run.Note `
            --cache none
        if ($LASTEXITCODE -ne 0) { throw "Backtest failed: $($Run.Strategy)" }
    }

    & $PythonExe "$UserData\scripts\build_regime_oos_report.py"
    if ($LASTEXITCODE -ne 0) { throw "OOS report build failed." }
}
finally {
    Pop-Location
}
