$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ProjectRoot
$FreqtradeExe = Join-Path $RepositoryRoot ".freqtrade-venv\Scripts\freqtrade.exe"
$PythonExe = Join-Path $RepositoryRoot ".freqtrade-venv\Scripts\python.exe"
$UserData = Join-Path $ProjectRoot "user_data"
$Results = Join-Path $UserData "backtest_results"
$AltSymbols = @("SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT")
$AltPairs = @("SOL/USDT:USDT", "XRP/USDT:USDT", "BNB/USDT:USDT", "DOGE/USDT:USDT")

if (-not (Test-Path -LiteralPath $FreqtradeExe)) {
    throw "Missing .freqtrade-venv. Follow freqtrade/README.md before running this script."
}

function Invoke-Backtest {
    param(
        [Parameter(Mandatory = $true)][string]$Config,
        [Parameter(Mandatory = $true)][string]$Strategy,
        [Parameter(Mandatory = $true)][string]$Note,
        [string]$FreqaiModel = ""
    )

    $commandArguments = @(
        "backtesting",
        "--userdir", $UserData,
        "--config", (Join-Path $UserData $Config),
        "--strategy", $Strategy,
        "--timerange", "20250101-20260101",
        "--fee", "0.001",
        "--max-open-trades", "4",
        "--stake-amount", "2500",
        "--pairs"
    ) + $AltPairs + @(
        "--export", "trades",
        "--backtest-directory", $Results,
        "--notes", $Note,
        "--cache", "none"
    )
    if ($FreqaiModel) {
        $commandArguments += @("--freqaimodel", $FreqaiModel)
    }

    Write-Host "`n=== $Note ==="
    & $FreqtradeExe @commandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Backtest failed: $Note"
    }
}

Push-Location $RepositoryRoot
try {
    & $PythonExe "$UserData\scripts\import_local_data.py" `
        --source "$RepositoryRoot\processed\usdt_futures" `
        --destination "$UserData\data\binanceusdm\futures" `
        --symbols $AltSymbols
    if ($LASTEXITCODE -ne 0) {
        throw "Altcoin data import failed."
    }

    & $PythonExe "$UserData\scripts\fit_regime_hmm.py" `
        --source "$RepositoryRoot\processed\usdt_futures" `
        --output "$UserData\regime_models" `
        --symbols $AltSymbols
    if ($LASTEXITCODE -ne 0) {
        throw "Altcoin HMM fitting failed."
    }

    Invoke-Backtest `
        -Config "config_baseline.json" `
        -Strategy "BollingerBreakout40D" `
        -Note "alt4-bollinger-2025"

    foreach ($Architecture in @("rnn", "gru", "lstm")) {
        Invoke-Backtest `
            -Config "config_freqai_$Architecture.json" `
            -Strategy "SequenceBreakoutStrategy" `
            -Note "alt4-$Architecture-2025" `
            -FreqaiModel "PyTorchSequenceRegressor"
    }

    Invoke-Backtest `
        -Config "config_hmm_regime.json" `
        -Strategy "HMMTrendOnlyStrategy" `
        -Note "alt4-hmm-trend-only-2025"

    Invoke-Backtest `
        -Config "config_hmm_regime.json" `
        -Strategy "HMMRegimeSwitchingStrategy" `
        -Note "alt4-hmm-regime-2025"

    Invoke-Backtest `
        -Config "config_hmm_lstm.json" `
        -Strategy "HMMRegimeLSTMStrategy" `
        -Note "alt4-hmm-regime-lstm-2025" `
        -FreqaiModel "PyTorchSequenceRegressor"

    & $PythonExe "$UserData\scripts\build_altcoin_report.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Altcoin report generation failed."
    }
}
finally {
    Pop-Location
}
