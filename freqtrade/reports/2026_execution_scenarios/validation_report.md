# Spot and futures execution-scenario validation

## Test design

- Frozen selection boundary: 2025-12-31. Neural models use a single 2025-01-01 through 2025-12-31 fit; no 2026 retraining is allowed in the reported holdout.
- Holdout: 2026-01-01 through 2026-09-17 23:00 UTC. September stops at the latest common verified Binance candle, so this is not a complete January-through-September calendar period.
- Coins: BTC, ETH, SOL, XRP, BNB, and DOGE, all at 1-hour strategy frequency.
- Execution cases: futures long/short, futures long-only, and spot long-only. Spot uses independently downloaded spot candles, spot-trained sequence models, and separately fitted spot HMMs.
- Standalone Freqtrade rows include 10 bps per-side fees. They do not include slippage or funding; those are handled in the daily portfolio layer.
- Portfolio rows include 10 bps fees and 5 bps modeled one-way slippage. Observed Binance funding is applied only to the two futures modes; spot has no funding and cannot short.

## Core model comparison

| execution_mode | model | trades | long_trades | short_trades | total_return_pct | maximum_drawdown_pct | closed_trade_sharpe_zero_rf |
| --- | --- | --- | --- | --- | --- | --- | --- |
| futures_long_only | Bollinger 40d | 27 | 27 | 0 | 0.12 | 17.16 | 0.00 |
| futures_long_only | HMM + LSTM static | 54 | 54 | 0 | -2.50 | 7.38 | -0.39 |
| futures_long_only | HMM switching | 120 | 120 | 0 | -5.81 | 17.62 | -0.75 |
| futures_long_only | HMM trend | 35 | 35 | 0 | -5.57 | 9.54 | -0.54 |
| futures_long_only | LSTM static | 20 | 20 | 0 | 6.84 | 11.08 | 0.23 |
| futures_long_short | Bollinger 40d | 45 | 30 | 15 | 25.90 | 11.90 | 0.93 |
| futures_long_short | HMM + LSTM static | 123 | 54 | 69 | -10.63 | 18.05 | -1.43 |
| futures_long_short | HMM switching | 237 | 118 | 119 | -15.83 | 26.30 | -1.93 |
| futures_long_short | HMM trend | 73 | 35 | 38 | -7.73 | 17.39 | -0.68 |
| futures_long_short | LSTM static | 37 | 21 | 16 | 28.56 | 6.02 | 1.02 |
| spot_long_only | Bollinger 40d | 27 | 27 | 0 | 0.23 | 17.08 | 0.01 |
| spot_long_only | HMM + LSTM static | 56 | 56 | 0 | 0.04 | 5.70 | 0.01 |
| spot_long_only | HMM switching | 119 | 119 | 0 | -7.36 | 17.65 | -0.99 |
| spot_long_only | HMM trend | 34 | 34 | 0 | -6.26 | 9.46 | -0.65 |
| spot_long_only | LSTM static | 20 | 20 | 0 | 4.04 | 10.86 | 0.14 |

## Best standalone Sharpe in each execution mode

| execution_mode | model | trades | total_return_pct | maximum_drawdown_pct | closed_trade_sharpe_zero_rf |
| --- | --- | --- | --- | --- | --- |
| futures_long_only | RNN static | 16 | 5.99 | 7.28 | 0.26 |
| futures_long_short | RNN static | 31 | 27.96 | 5.21 | 1.06 |
| spot_long_only | LSTM static | 20 | 4.04 | 10.86 | 0.14 |

## Allocation and cost scenarios

| execution_mode | portfolio | return_pct | sharpe | max_drawdown_pct | avg_gross_exposure_pct | average_daily_turnover_pct |
| --- | --- | --- | --- | --- | --- | --- |
| futures_long_only | Ensemble variable | 1.42 | 0.21 | 10.69 | 23.64 | 3.75 |
| futures_long_only | Ensemble equal | -5.19 | -0.24 | 17.05 | 34.90 | 4.38 |
| futures_long_only | Ensemble variable + HMM gate | -1.73 | -0.24 | 7.49 | 13.09 | 5.30 |
| futures_long_only | Ensemble equal + HMM gate | -7.33 | -0.74 | 11.83 | 19.34 | 7.48 |
| futures_long_short | Ensemble variable | 17.75 | 1.26 | 9.39 | 44.95 | 7.18 |
| futures_long_short | Ensemble variable + HMM gate | 9.00 | 1.04 | 6.14 | 25.47 | 10.09 |
| futures_long_short | Ensemble equal + HMM gate | 19.44 | 0.98 | 13.46 | 46.88 | 18.43 |
| futures_long_short | Ensemble equal | 27.12 | 0.93 | 22.82 | 79.90 | 8.01 |
| spot_long_only | Ensemble variable | 1.66 | 0.23 | 11.20 | 23.85 | 3.84 |
| spot_long_only | Ensemble variable + HMM gate | -1.44 | -0.19 | 7.37 | 13.18 | 5.24 |
| spot_long_only | Ensemble equal | -5.08 | -0.23 | 17.73 | 35.10 | 4.65 |
| spot_long_only | Ensemble equal + HMM gate | -7.17 | -0.72 | 11.71 | 19.40 | 7.50 |

## Interpretation

- Futures long/short is the only valid short-selling case. Spot and the futures long-only control both clamp all short entries to zero.
- The raw Freqtrade comparison isolates strategy behavior after exchange fees. The portfolio comparison is the relevant cost-aware allocation validation because it adds modeled slippage and, for futures, observed funding.
- Spot and futures long-only can look close for slow Bollinger trades, but they are not duplicates: the candles, trained neural weights, HMM parameters, and funding treatment differ.
- Do not tune after reading this holdout. A rule change now needs a later untouched test period.
