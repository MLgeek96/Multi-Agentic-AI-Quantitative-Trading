# Six-coin USD-M futures validation

Generated from the frozen-parameter validation run on six Binance USD-M perpetuals: BTC, ETH, SOL, XRP, BNB, and DOGE.

## Test design

- Parameter/model-selection boundary: 2025-12-31. Neural weights are fit once on 2025-01-01 through 2025-12-31; there is no 2026 refit in the primary results.
- Reported holdout: 2026-01-01 through 2026-09-17. The intended September endpoint is truncated because the common verified candle set ends on 2026-09-17 23:00 UTC.
- Instrument: Binance USD-M isolated perpetual futures at 1x notional exposure. These numbers are not a spot backtest.
- Freqtrade standalone costs: 10 bps per side fee, with no funding or slippage inside Freqtrade.
- Portfolio-layer costs: 10 bps fee plus 5 bps modeled slippage per one-way turnover, and observed Binance funding events.
- Ensemble: strict 3-of-5 majority across Bollinger, RNN, GRU, LSTM, and Transformer positions, sampled at 23:00 UTC and applied to the next daily return.
- HMM gate: trend 1.0, sideways 0.5, crisis/uncertain 0.0. The variable allocator uses inverse 30-day volatility, model-vote confidence, a 25% per-coin cap, and a 20% annualized portfolio-volatility ceiling. It never scales above 1x gross.

## Standalone Freqtrade results

| model | trades | return_pct | max_drawdown_pct | closed_trade_sharpe | profit_factor |
| --- | --- | --- | --- | --- | --- |
| LSTM static | 37 | 28.56 | 6.02 | 1.02 | 2.68 |
| RNN static | 31 | 27.96 | 5.21 | 1.06 | 3.26 |
| Transformer static | 17 | 26.90 | 2.50 | 0.97 | 6.34 |
| Bollinger 40d | 45 | 25.90 | 11.90 | 0.93 | 2.08 |
| GRU static | 35 | 9.07 | 8.29 | 0.35 | 1.43 |
| HMM trend defensive | 46 | -5.27 | 10.73 | -0.53 | 0.63 |
| HMM trend | 73 | -7.73 | 17.39 | -0.68 | 0.70 |
| HMM + LSTM static | 123 | -10.63 | 18.05 | -1.43 | 0.65 |
| HMM defensive | 211 | -14.48 | 24.40 | -2.00 | 0.72 |
| HMM switching | 237 | -15.83 | 26.30 | -1.93 | 0.74 |

The strongest standalone result is **LSTM static** at 28.56%. The result dispersion is important: neural architecture choice matters, and the standalone HMM sleeves are negative in this holdout.

## Allocation validation after fee, slippage, and funding

| portfolio | return_pct | annualized_vol_pct | sharpe | max_drawdown_pct | avg_gross_exposure_pct | total_turnover_x |
| --- | --- | --- | --- | --- | --- | --- |
| Ensemble equal | 27.12 | 49.01 | 0.93 | 22.82 | 79.90 | 20.83 |
| Ensemble equal + HMM gate | 19.44 | 29.99 | 0.98 | 13.46 | 46.88 | 47.92 |
| Ensemble variable | 17.75 | 19.77 | 1.26 | 9.39 | 44.95 | 18.67 |
| Ensemble variable + HMM gate | 9.00 | 12.42 | 1.04 | 6.14 | 25.47 | 26.23 |

The proposed variable/HMM portfolio returned 9.00% with a 6.14% maximum drawdown under the base cost assumptions. Compare it directly with both the equal-weight and ungated variable rows; variable sizing is only justified if its risk-adjusted result is stronger, not by assumption.

## Slippage stress for the proposed portfolio

| slippage_bps_per_side | return_pct | sharpe | max_drawdown_pct | slippage_drag_pct_simple |
| --- | --- | --- | --- | --- |
| 2.00 | 9.86 | 1.12 | 6.08 | 0.52 |
| 5.00 | 9.00 | 1.04 | 6.14 | 1.31 |
| 10.00 | 7.58 | 0.89 | 6.24 | 2.62 |

Slippage is a scenario assumption because this workspace does not contain historical order-book snapshots. Funding is based on 4,680 observed funding-rate events cached in `funding_rates.csv.gz`.

## Interpretation

- Treat the 2026 period as validation, not a new tuning set. Do not change thresholds after seeing these results unless a later period is reserved as a fresh test.
- HMM is more defensible here as a risk gate than as a standalone return engine: every tested standalone HMM variant lost money.
- The Transformer result is dominated by short trades, so it should not be presented as broad proof that deep learning is superior.
- Signals are hourly inside each strategy, but the portfolio overlay rebalances once daily at 23:00 UTC to control turnover and keep the allocation comparison causal.
- Spot deployment needs a separate long-only rerun: remove short positions and funding, then use spot fees and spot liquidity assumptions.

## Reproduction

The raw Freqtrade archives are under `freqtrade/validation_runs/2026_sixcoin`. Rebuild the portfolio outputs with:

```powershell
.\.freqtrade-venv\Scripts\python.exe freqtrade/user_data/scripts/build_sixcoin_validation_report.py
```
