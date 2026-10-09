$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ProjectRoot
$FreqtradeExe = Join-Path $RepositoryRoot ".freqtrade-venv\Scripts\freqtrade.exe"
$PythonExe = Join-Path $RepositoryRoot ".freqtrade-venv\Scripts\python.exe"
$UserData = Join-Path $ProjectRoot "user_data"
$Results = Join-Path $UserData "backtest_results"

Push-Location $RepositoryRoot
try {
    & $PythonExe "$UserData\scripts\fit_regime_hmm.py" `
        --source "$RepositoryRoot\processed\usdt_futures" `
        --output "$UserData\regime_models"

    & $FreqtradeExe backtesting `
        --userdir $UserData `
        --config "$UserData\config_hmm_regime.json" `
        --strategy HMMTrendOnlyStrategy `
        --timerange 20250101-20260101 `
        --fee 0.001 `
        --export trades `
        --backtest-directory $Results `
        --notes hmm-trend-only-2025 `
        --cache none

    & $FreqtradeExe backtesting `
        --userdir $UserData `
        --config "$UserData\config_hmm_regime.json" `
        --strategy HMMSidewaysOnlyStrategy `
        --timerange 20250101-20260101 `
        --fee 0.001 `
        --export trades `
        --backtest-directory $Results `
        --notes hmm-sideways-only-2025 `
        --cache none

    & $FreqtradeExe backtesting `
        --userdir $UserData `
        --config "$UserData\config_hmm_regime.json" `
        --strategy HMMRegimeSwitchingStrategy `
        --timerange 20250101-20260101 `
        --fee 0.001 `
        --export trades `
        --backtest-directory $Results `
        --notes hmm-regime-2025 `
        --cache none

    & $FreqtradeExe backtesting `
        --userdir $UserData `
        --config "$UserData\config_hmm_lstm.json" `
        --strategy HMMRegimeLSTMStrategy `
        --freqaimodel PyTorchSequenceRegressor `
        --timerange 20250101-20260101 `
        --fee 0.001 `
        --export trades `
        --backtest-directory $Results `
        --notes hmm-regime-lstm-2025 `
        --cache none

    foreach ($FeeCase in @(
        @{ Fee = 0.0005; Suffix = "005" },
        @{ Fee = 0.002; Suffix = "020" }
    )) {
        & $FreqtradeExe backtesting `
            --userdir $UserData `
            --config "$UserData\config_hmm_regime.json" `
            --strategy HMMRegimeSwitchingStrategy `
            --timerange 20250101-20260101 `
            --fee $FeeCase.Fee `
            --export trades `
            --backtest-directory $Results `
            --notes "hmm-regime-fee-$($FeeCase.Suffix)-2025" `
            --cache none

        & $FreqtradeExe backtesting `
            --userdir $UserData `
            --config "$UserData\config_hmm_regime.json" `
            --strategy HMMTrendOnlyStrategy `
            --timerange 20250101-20260101 `
            --fee $FeeCase.Fee `
            --export trades `
            --backtest-directory $Results `
            --notes "hmm-trend-only-fee-$($FeeCase.Suffix)-2025" `
            --cache none
    }

    & $PythonExe "$UserData\scripts\build_regime_report.py"
}
finally {
    Pop-Location
}
