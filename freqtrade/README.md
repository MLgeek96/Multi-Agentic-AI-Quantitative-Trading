# Freqtrade BTC/ETH sequence-model experiment

This is a reproducible, dry-run-only Freqtrade futures project. It imports this repository's
existing hourly BTC and ETH data, runs a Bollinger breakout control, and compares otherwise
identical RNN-, GRU-, LSTM-, and Transformer-filtered variants.

## Experiment design

- Market: Binance USD-M perpetual futures, BTC/USDT and ETH/USDT. The local candles drive the
  test; Binance's official USD-M testnet supplies public contract precision metadata because the
  production API is geoblocked from this machine.
- Candle data: the local `processed/usdt_futures/*_1h.csv.gz` files; no price download is needed.
- Holdout: 2025-01-01 through 2025-12-31, the latest complete year in those files.
- Baseline: enter on a 40-day Bollinger breakout and exit at the middle band.
- Neural variants: require the same breakout plus a correctly signed forecast whose absolute
  next-24-hour return is greater than 0.2%.
- Sequence: 48 hourly candles.
- Walk-forward training: trailing 365 days, refreshed every 90 days.
- Features: price returns, range and candle body, realized volatility, moving-average distance,
  RSI, volume change and z-score, and cyclical hour/weekday values. There are 18 causal features.
- Network: the recurrent runs use one layer and 32 hidden units. The Transformer uses a one-layer,
  32-wide encoder with four heads and a 64-unit feed-forward block. All use dropout 0.1, up to six
  epochs, Huber loss, chronological 90/10 validation, early-stopping patience 2, and seed 42.
- Costs: the provided runner uses a 0.10% fee on entry and again on exit. Funding is set to zero
  because the local archive does not include historical funding-rate candles.
- Risk: isolated futures, 1x leverage, two simultaneous slots. Freqtrade can hold opposite
  directions in BTC and ETH simultaneously, but not a long and short in the same pair at once.

All neural configurations keep the same features, target, sequence length, training windows,
optimizer, seed, and trading rules. Only the sequence model and FreqAI identifier change. This
keeps the comparison controlled and prevents cached predictions from being reused across models.

## Tested result

The completed 2025 holdout comparison, daily wallet chart, method notes, and all 78 trades are in
`reports/2025_sequence_baseline/backtest_results.xlsx`. The main result is that the pure Bollinger
control beat every neural gate on wallet Sharpe; LSTM nearly matched its return but took more
drawdown, while the Transformer returned only 2.16%. See
`reports/2025_sequence_baseline/research_report.md` for the interpretation and the development-only
tuning plan.

The original sequence-model comparison remains a 2025-only experiment. BTC/ETH source data has
since been extended with checksum-verified official archives through 2026-09-17 for the separate
HMM out-of-sample study described below.

## SOL/XRP/BNB/DOGE transfer test

The unchanged BTC/ETH rules were also screened on a separate four-altcoin portfolio using SOL,
XRP, BNB, and DOGE USD-M perpetuals. The experiment keeps the 10,000 USDT total wallet but permits
four simultaneous 2,500 USDT positions so one signal per pair can be active without slot
competition. HMMs are fit separately per pair on 2020-2024, and 2025 remains the holdout.

The plain 40-day Bollinger control produced the highest 2025 return at **+21.22%**, with **20.71%**
maximum drawdown. The HMM trend-only sleeve had the strongest risk-adjusted result at **+11.67%**,
**11.27%** maximum drawdown, and **0.68** daily wallet Sharpe. RNN and LSTM gates remained
profitable but did not beat the control; the complete HMM regime strategy lost **8.42%**, and its
LSTM-gated version lost **1.72%**. See `reports/2025_altcoin_screen/research_report.md` for the
portfolio and pair-level breakdown.

Run the complete transfer test and rebuild its report with:

```powershell
.\freqtrade\run_altcoin_backtests.ps1
```

The run covers Bollinger, RNN, GRU, LSTM, HMM trend-only, full HMM regime, and HMM-plus-LSTM. As
with the BTC/ETH experiment, funding and slippage are not included, and 2025 must be treated as
consumed after inspecting these results.

## Three-regime HMM baseline

The project now also contains a causal three-state Gaussian HMM router:

- **Trend:** 20-day Bollinger breakout confirmed by EMA 24/120, MACD, and RSI.
- **Sideways:** seven-day, two-standard-deviation Bollinger fade with RSI confirmation.
- **Crisis:** block entries, close existing risk, and remain in cash.
- **Optional LSTM:** the same 48-hour sequence model gates entries after the HMM chooses a sleeve.

The pair-specific HMMs use return, realized volatility, volatility ratio, trend strength,
drawdown, and volume z-score. They were fit on 2020-2024 only, with five initializations, then
frozen for the 2025 comparison. The strategy uses forward-filtered state probabilities; it does
not use future-aware smoothed states.

The strongest new 2025 control was **HMM trend only: +19.58%, 4.66% maximum drawdown, 1.32 daily
wallet Sharpe**. The sideways-only sleeve lost 11.01%; combining it with trend reduced return to
12.89%, and the LSTM gate reduced the combined result to 7.18%. See
`reports/2025_regime_baseline/research_report.md` and the interactive
`reports/2025_regime_baseline/regime_dashboard.html` for the full diagnostics and trade log.

Run the complete regime experiment and rebuild its report with:

```powershell
.\freqtrade\run_regime_backtests.ps1
```

The HMM dependency is pinned in the repository-level `requirements.txt`. This runner includes
trend-only, sideways-only, combined, combined-plus-LSTM, and 0.05%/0.20% fee stress controls.
Treat 2025 as consumed; use the rolling development protocol in
`reports/2025_regime_baseline/parameter_selection.md` before changing parameters.

## Extended HMM test through September 2026

Lessons 12 and 13 from Wayland Zhang's quantitative-trading book are implemented as a separate
defensive ablation: low-confidence output becomes an explicit `uncertain` state, normal
trend/sideways changes require three consecutive hourly observations, and crisis de-risking stays
immediate. Because this Freqtrade experiment uses fixed 5,000 USDT slots, uncertainty exits to
cash rather than applying a fractional position scale.

The 2025-01-01 through 2026-09-17 comparison includes raw and defensive three-sleeve HMMs, raw
and defensive trend-only HMMs, and the no-HMM Bollinger control. The HMM/scaler is still fit only
through 2024. Run it with:

```powershell
.\freqtrade\run_regime_oos_backtests.ps1
```

The downloader and normalizer used for the extension are:

```powershell
.\.freqtrade-venv\Scripts\python.exe .\scripts\download_hourly_oos_inputs.py
.\.freqtrade-venv\Scripts\python.exe .\scripts\prepare_klines.py --markets usdt_futures --symbols BTCUSDT ETHUSDT --interval 1h --start 2020-01-01 --end 2026-09-18 --output processed
```

Results and router-health diagnostics are in `reports/2025_2026_regime_lessons/`. The main
finding is negative but useful: immediate exits on every uncertain transition reduced trades but
did not improve drawdown enough to offset lost edge. The unmodified trend-only HMM remained the
best HMM variant, while the simple Bollinger control was still far stronger in this sample.

## Native Windows setup

Freqtrade recommends Docker on Windows, but this machine's Docker engine currently fails on a
stale Docker socket. The successful tests used a local Python 3.12 environment instead:

```powershell
py -3.12 -m venv .freqtrade-venv
.\.freqtrade-venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "freqtrade[freqai,plot]==2026.8" torch
python -m pip install "joblib==1.5.3"
python -m pip install -r .\requirements.txt
```

The explicit joblib pin matches Freqtrade's stable FreqAI requirements and avoids an import error
seen with joblib 1.6.

## Run the five backtests

From the repository root:

```powershell
.\freqtrade\run_backtests.ps1
```

The runner imports local candles and writes timestamped archives to
`freqtrade/user_data/backtest_results`. It uses the 2025 holdout, 0.10% per-side fee, seed 42, and
fresh backtest calculation. FreqAI may reuse prediction files for the same unchanged identifier.

To rebuild the consolidated report after new runs:

```powershell
.\.freqtrade-venv\Scripts\python.exe .\freqtrade\user_data\scripts\build_backtest_report_data.py
```

## Docker alternative

`docker-compose.yml` uses the official `stable_freqaitorch` image. Once Docker Desktop works, the
same configs and local data importer can run in the container. Do not mix Docker and native result
archives without checking that the Freqtrade versions match.

## Safety

These configs are dry-run configurations with blank API keys. Do not add credentials or switch to
live trading based on this one-year result. Before even a small dry trade:

1. Treat the reviewed 2025 result as consumed. Tune only on rolling 2020-2024 development folds.
2. Repeat every neural candidate across several random seeds.
3. Stress entry and exit fees, slippage, and actual historical funding.
4. Investigate why BTC loses money in all five final runs.
5. Dry-run for several weeks and compare modeled fills with observed fills.
