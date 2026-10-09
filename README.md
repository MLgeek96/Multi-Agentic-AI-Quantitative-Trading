# Crypto Trading Strategy Research

## Local multi-agent research architecture

The BURSA-style local agent implementation is documented in
[`ARCHITECTURE.md`](ARCHITECTURE.md). It reuses the adaptive strategy with Meta,
Regime, Signal, Position, Risk and record-only Execution agents. An optional LLM
Research Agent validates imported replies after decisions. Risk has final veto
authority; generated intents never create exchange orders or paper fills.

```powershell
.\.venv\Scripts\python.exe -m crypto_agents --config config/agents.demo.json
.\.venv\Scripts\python.exe -m crypto_agents --config config/agents.research.json --as-of 2026-09-16
```

The research date replays the existing September daily cache. The new data-quality
gate also protects the separate daily paper runner and rejects stale/corrupt data.
See [`reports/agents/implementation_report.md`](reports/agents/implementation_report.md)
for verified results and [`GITHUB_PRIVATE.md`](GITHUB_PRIVATE.md) for private-repo
setup and future pushes. Neither these changes nor a successful demo activates the
October daily schedule.

## Final research wrap-up

The consolidated report prepared on 28 September 2026 is in
[`reports/FINAL_RESEARCH_REPORT.md`](reports/FINAL_RESEARCH_REPORT.md). Its companion
[`reports/FINAL_PARAMETER_MANIFEST.json`](reports/FINAL_PARAMETER_MANIFEST.json) records the
effective strategy, model, allocation, execution, and cost parameters. The report preparation
date is later than the latest validated hourly candle: results stop at 17 September 2026 23:00
UTC and do not claim coverage of the remaining September dates.

The separate USDT 1 million capacity and backtest-quality extension is in
[`freqtrade/reports/2026_million_usdt_quality/million_usdt_quality_report.md`](freqtrade/reports/2026_million_usdt_quality/million_usdt_quality_report.md).
It keeps the frozen portfolio weights and adds slippage stress, observed funding, a trailing-liquidity square-root impact estimate, 1,000 Monte Carlo perturbations, per-coin dollar attribution, and a strict quality-gate audit. The audit fails overall, so the result remains research-only.

The BTC/ETH/altcoin-season extension is in
[`freqtrade/reports/2026_market_cycle_hmm/market_cycle_report.md`](freqtrade/reports/2026_market_cycle_hmm/market_cycle_report.md).
It tests a frozen three-state relative-strength HMM, a one-third BTC / one-third ETH / one-third altcoin signal allocation, and a separate 50/25/25 HMM tilt. The equal-bucket signal allocation improved final return in the inspected 2026 sample, but the HMM tilt did not improve Sharpe and is retained only as a diagnostic experiment.

This workspace contains Binance BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT,
and DOGEUSDT hourly candles for two distinct markets:

- Spot
- USD-M perpetual futures (`um` in Binance's archive paths)

The raw monthly ZIP files cover **2020-01 through 2025-12**. Binance SHA-256 checksum files are kept beside every archive.

## Assignment daily portfolio

The assignment workflow is separate from the hourly pattern research below. It automatically pulls completed daily Spot candles from Binance's public market-data API, verifies listing eligibility and continuity, refits an adaptive trend model, calculates target weights, and updates a paper portfolio. **It does not place exchange orders and does not need an API key.**

The current configurable universe is BTC and ETH against USDT. Update `config/daily_portfolio.json` when the mandatory class assets and official benchmark are confirmed.

### Set up Python

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Pull data and generate today's preview/signals

Run this after the UTC daily close:

```powershell
.\scripts\run_daily.ps1
```

Before October 1, the runner writes preview signals and validates the data pipeline. During October 1–23 it backfills any unprocessed dates and updates:

- `live/portfolio_closing_prices.csv` — required submission price file;
- `live/daily_signals.csv` — selected parameters, forecasts, and target weights;
- `live/portfolio_daily.csv` — paper equity, returns, drawdown, costs, and benchmarks;
- `live/paper_orders.csv` and `live/closed_trades.csv` — audit and trade ledgers;
- `live/portfolio_kpis.json` — the required performance statistics;
- `live/run_manifest.json` — source, candle boundary, eligibility, and safety status.

### Reproduce the walk-forward research

```powershell
.\.venv\Scripts\python.exe .\scripts\backtest_daily_portfolio.py
```

Results are written to `reports/daily_portfolio/`. The current validation result is positive but trails both BTC and the equal-weight crypto benchmark, so it is not yet a final strategy selection.

The report compares the baseline with an experimental Bollinger/RSI confirmation rule. The experiment uses RSI(14) of 45–70 and requires price to remain inside 20-day, two-standard-deviation Bollinger Bands. It reduced drawdown but produced a negative validation return, so the baseline remains the default. To generate a separate live preview of the experimental rule without contaminating the main paper ledger:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_daily_portfolio.py --config .\config\btc_eth_bb_rsi.json
```

### Schedule the daily run on Windows

Review the configuration first, then install the task once:

```powershell
.\scripts\install_daily_task.ps1
```

The default 08:15 Singapore run time is 15 minutes after Binance's 00:00 UTC daily close. The laptop must be available; `StartWhenAvailable` runs a missed task after it comes back online. Do not add exchange keys to source files. Authenticated/testnet execution should be a separate adapter only if the instructor requires order evidence.

## Prepare the research files

From PowerShell:

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_klines.py
```

This verifies every checksum and writes one normalized gzip-compressed CSV per market and symbol under `processed/`. Times are UTC. The loader automatically handles Binance spot's switch from millisecond to microsecond timestamps in 2025 and optional futures CSV header rows. `processed/manifest.json` records row counts, completeness, listing-dependent start dates, and the exact boundaries of any gaps; missing candles are deliberately not forward-filled.

Load a prepared file with pandas:

```python
import pandas as pd

spot_btc = pd.read_csv(
    "processed/spot/BTCUSDT_1h.csv.gz",
    parse_dates=["open_time", "close_time"],
)
futures_btc = pd.read_csv(
    "processed/usdt_futures/BTCUSDT_1h.csv.gz",
    parse_dates=["open_time", "close_time"],
)
```

Keep the two frames separate during signal generation. Join them explicitly on `open_time` only when a strategy needs both markets; spot volume and futures volume are not interchangeable.

## Run the pattern + momentum research suite

The strategy implementation in `crypto_quant/pattern_momentum.py` translates the rules in `references/crypto-quant-strategy-spec.md` into three testable hypotheses:

- double-top / double-bottom reversal;
- ascending / descending triangle breakout;
- bull / bear flag continuation.

Run the default BTC and ETH perpetual-futures research:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_strategy_research.py
```

To also test long-only spot behavior:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_strategy_research.py --markets usdt_futures spot
```

Results are written to `reports/pattern_momentum/`. The run keeps a 2020-2023 development period separate from a 2024-2025 holdout period. It models fees and slippage, but not perpetual funding, order-book liquidity, market impact, or liquidation. Treat the output as research rather than a live-trading recommendation.

Run the deterministic tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Run the two-state HMM regime baseline

The separate futures baseline in `crypto_quant/hmm_regime.py` uses a shared,
walk-forward two-state Gaussian HMM for BTC and ETH.  The higher-return-variance
state trades MACD/SMA/RSI momentum; the lower-volatility state trades Bollinger
mean reversion.  Positions are signed, so the portfolio can be long BTC and
short ETH (or vice versa) at the same time.  Signals are delayed one daily bar
and include turnover costs.

```powershell
.\.venv\Scripts\python.exe .\scripts\run_hmm_regime_research.py
```

Configuration is in `config/hmm_regime.json`; artifacts and parameter-selection
guidance are written to `reports/hmm_regime/`.  Optional macro inputs must be a
daily CSV of already-stationary features (for example S&P 500 return, VIX
change, and 10-year-yield change).  Set `macro_features_csv` and
`macro_columns`; the runner applies the configured one-day availability lag and
uses zero for weekend/no-release changes.  Raw index or yield levels should not
be fed directly into the HMM.

To compare the HMM with development-tuned controls, the strategies from the
trend-strategy reference, a dynamic-grid proxy, and walk-forward ridge linear
regression, run:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_model_selection.py
```

This runner selects one configuration per family using only four rolling folds
inside 2022–2023, freezes those choices, evaluates 2024–2025 once, and repeats
the final comparison at 5/10/20/30 bps. Outputs go to
`reports/model_selection/`. The grid strategy is explicitly a daily-close
proxy; it is not an intraday limit-order fill simulation.

## Add macro relationships and extend through 2026

The macro-regime experiment downloads checked Binance USD-M daily archives and
FRED S&P 500, Nasdaq, VIX, 10-year-yield, and effective-fed-funds series. It
adds rolling relationship, volume-surprise, and taker-buy-imbalance features;
the relationship sign is estimated walk-forward rather than assumed.

```powershell
.\.venv\Scripts\python.exe .\scripts\download_macro_regime_inputs.py
.\.venv\Scripts\python.exe .\scripts\run_macro_regime_research.py
```

The grid is selected on rolling 2022–2024 folds and reported separately for
2025 through the latest common 2026 observation. Outputs go to
`reports/macro_regime/`.

The hierarchical gatekeeper proposed in the architecture review is tested
separately so it cannot silently replace the pure-breakout control:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_gatekeeper_research.py
```

It uses HMM state only as an allocation throttle, Bollinger(40, 1.5) as the
trade engine, and MA/momentum only to confirm new entries. Results and layer
ablations are written to `reports/gatekeeper/`. The runner also exports
chart-ready equity/drawdown/exposure curves, an entry-to-exit trade ledger,
and a fully reconciling daily model/date/symbol trading log for all four layer
controls.

## Validate frozen models across Spot and futures

To apply the already-selected rule, HMM, macro-regime, and gatekeeper
parameters to both markets without retuning them on the comparison period:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_cross_market_validation.py
```

The comparison writes to `reports/cross_market_validation/` and separates
ordinary Spot long/cash, futures long/cash, and futures long/short. The common
validation period is 2025 because the normalized Spot history currently ends
on 31 December 2025. Treat it as a frozen cross-market transfer test rather
than a new pristine holdout because 2025 has already been viewed elsewhere in
the research.

For the later forward split, reselect every model on eight half-year folds
covering 2022–2025 and test the frozen choices on the common 2026 Spot/futures
period through 16 September:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_2026_forward_validation.py
```

Outputs are written to `reports/forward_2026_validation/`. Although the runner
does not use 2026 for parameter ranking, earlier reports already inspected
some 2026 futures results, so this is not a globally pristine holdout for the
entire research project.

## Re-download or resume

```powershell
.\scripts\download_data.ps1
```

The wrapper uses Binance's official [`binance-public-data`](https://github.com/binance/binance-public-data) Python downloader. It is safe to rerun: already-downloaded files are retained, and missing files are fetched. Raw data, processed data, the virtual environment, and the cloned downloader are ignored by Git.

To change the symbols, years, or interval:

```powershell
.\scripts\download_data.ps1 -Symbols BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,DOGEUSDT -Years 2024,2025 -Interval 1h
```

## Layout

```text
datasets/
  spot/data/spot/monthly/klines/...
  usdt_futures/data/futures/um/monthly/klines/...
processed/
  spot/...
  usdt_futures/...
  manifest.json
scripts/
  download_data.ps1
  prepare_klines.py
```
