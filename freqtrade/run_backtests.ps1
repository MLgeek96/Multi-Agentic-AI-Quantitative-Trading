$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ProjectRoot
$FreqtradeExe = Join-Path $RepositoryRoot ".freqtrade-venv\Scripts\freqtrade.exe"
$PythonExe = Join-Path $RepositoryRoot ".freqtrade-venv\Scripts\python.exe"
$UserData = Join-Path $ProjectRoot "user_data"
$Results = Join-Path $UserData "backtest_results"

if (-not (Test-Path -LiteralPath $FreqtradeExe)) {
    throw "Missing .freqtrade-venv. Follow freqtrade/README.md before running this script."
}

Push-Location $RepositoryRoot
try {
    & $PythonExe "$UserData\scripts\import_local_data.py" `
        --source "$RepositoryRoot\processed\usdt_futures" `
        --destination "$UserData\data\binanceusdm\futures"

    & $FreqtradeExe backtesting `
        --userdir $UserData `
        --config "$UserData\config_baseline.json" `
        --strategy BollingerBreakout40D `
        --timerange 20250101-20260101 `
        --fee 0.001 `
        --export trades `
        --backtest-directory $Results `
        --notes baseline-2025 `
        --cache none

    foreach ($Architecture in @("rnn", "gru", "lstm", "transformer")) {
        & $FreqtradeExe backtesting `
            --userdir $UserData `
            --config "$UserData\config_freqai_$Architecture.json" `
            --strategy SequenceBreakoutStrategy `
            --freqaimodel PyTorchSequenceRegressor `
            --timerange 20250101-20260101 `
            --fee 0.001 `
            --export trades `
            --backtest-directory $Results `
            --notes "$Architecture-seed42-2025" `
            --cache none
    }
}
finally {
    Pop-Location
}
