# Spot and futures execution-scenario validation

## Test design

- Frozen selection boundary: 2025-12-31. Neural and HMM models use each coin's own available history through 2025-12-31. After the 1,000-hour feature warm-up, the neural fitting windows span 1,893-2,150 days for futures and 1,927-2,150 days for spot. No 2026 retraining is allowed in the reported holdout.
- Holdout: 2026-01-01 through 2026-09-17 23:00 UTC. September stops at the latest common verified Binance candle, so this is not a complete January-through-September calendar period.
- Coins: BTC, ETH, SOL, XRP, BNB, and DOGE, all at 1-hour strategy frequency.
- Execution cases: futures long/short, futures long-only, and spot long-only. Spot uses independently downloaded spot candles, spot-trained sequence models, and separately fitted spot HMMs.
- Standalone Freqtrade rows include 10 bps per-side fees. They do not include slippage or funding; those are handled in the daily portfolio layer.
- Portfolio rows include 10 bps fees and 5 bps modeled one-way slippage. Observed Binance funding is applied only to the two futures modes; spot has no funding and cannot short.

## Core model comparison

| execution_mode | model | trades | long_trades | short_trades | total_return_pct | maximum_drawdown_pct | closed_trade_sharpe_zero_rf |
| --- | --- | --- | --- | --- | --- | --- | --- |
| futures_long_only | Bollinger 40d | 27 | 27 | 0 | 0.12 | 17.16 | 0.00 |
| futures_long_only | HMM + LSTM static | 65 | 65 | 0 | -4.84 | 9.60 | -0.70 |
| futures_long_only | HMM switching | 121 | 121 | 0 | -7.46 | 19.60 | -0.99 |
| futures_long_only | HMM trend | 38 | 38 | 0 | -5.02 | 9.02 | -0.50 |
| futures_long_only | LSTM static | 24 | 24 | 0 | -0.35 | 16.42 | -0.01 |
| futures_long_short | Bollinger 40d | 45 | 30 | 15 | 25.90 | 11.90 | 0.93 |
| futures_long_short | HMM + LSTM static | 111 | 65 | 46 | 0.24 | 10.25 | 0.03 |
| futures_long_short | HMM switching | 246 | 120 | 126 | -15.49 | 27.35 | -1.97 |
| futures_long_short | HMM trend | 83 | 38 | 45 | -6.64 | 16.68 | -0.63 |
| futures_long_short | LSTM static | 38 | 26 | 12 | 23.71 | 8.71 | 0.87 |
| spot_long_only | Bollinger 40d | 27 | 27 | 0 | 0.23 | 17.08 | 0.01 |
| spot_long_only | HMM + LSTM static | 41 | 41 | 0 | -5.35 | 7.51 | -0.80 |
| spot_long_only | HMM switching | 120 | 120 | 0 | -7.83 | 19.62 | -1.03 |
| spot_long_only | HMM trend | 36 | 36 | 0 | -4.48 | 8.49 | -0.44 |
| spot_long_only | LSTM static | 20 | 20 | 0 | 6.02 | 12.31 | 0.20 |

## Best standalone Sharpe in each execution mode

| execution_mode | model | trades | total_return_pct | maximum_drawdown_pct | closed_trade_sharpe_zero_rf |
| --- | --- | --- | --- | --- | --- |
| futures_long_only | Transformer static | 5 | 0.42 | 4.43 | 0.01 |
| futures_long_short | Bollinger 40d | 45 | 25.90 | 11.90 | 0.93 |
| spot_long_only | LSTM static | 20 | 6.02 | 12.31 | 0.20 |

## Allocation and cost scenarios

| execution_mode | portfolio | return_pct | sharpe | max_drawdown_pct | avg_gross_exposure_pct | average_daily_turnover_pct |
| --- | --- | --- | --- | --- | --- | --- |
| futures_long_only | Ensemble variable | -5.51 | -0.61 | 15.54 | 18.04 | 3.53 |
| futures_long_only | Ensemble equal | -13.66 | -1.21 | 23.28 | 23.75 | 3.65 |
| futures_long_only | Ensemble variable + HMM gate | -6.32 | -1.31 | 9.79 | 9.86 | 4.22 |
| futures_long_only | Ensemble equal + HMM gate | -10.69 | -1.75 | 14.11 | 12.88 | 5.29 |
| futures_long_short | Ensemble variable | 15.51 | 1.10 | 11.42 | 40.33 | 6.92 |
| futures_long_short | Ensemble variable + HMM gate | 6.65 | 0.85 | 7.51 | 22.70 | 9.26 |
| futures_long_short | Ensemble equal + HMM gate | 12.39 | 0.74 | 17.12 | 41.52 | 17.19 |
| futures_long_short | Ensemble equal | 18.25 | 0.73 | 26.55 | 70.77 | 7.56 |
| spot_long_only | Ensemble variable | 4.57 | 0.60 | 6.11 | 15.32 | 2.53 |
| spot_long_only | Ensemble variable + HMM gate | 0.01 | 0.04 | 3.82 | 8.57 | 4.09 |
| spot_long_only | Ensemble equal | -1.84 | -0.09 | 9.78 | 20.87 | 2.50 |
| spot_long_only | Ensemble equal + HMM gate | -2.78 | -0.40 | 4.73 | 11.59 | 5.38 |

## Native-history versus 2025-only training

Positive return and Sharpe deltas favor native-history training. Negative maximum-drawdown deltas mean a smaller drawdown.

| execution_mode | model | total_return_pct_2025_only | total_return_pct_native_history | total_return_pct_delta_native_minus_2025_only | closed_trade_sharpe_zero_rf_delta_native_minus_2025_only |
| --- | --- | --- | --- | --- | --- |
| futures_long_only | GRU static | -6.35 | -6.18 | 0.17 | -0.01 |
| futures_long_only | HMM + LSTM static | -2.50 | -4.84 | -2.34 | -0.31 |
| futures_long_only | LSTM static | 6.84 | -0.35 | -7.20 | -0.25 |
| futures_long_only | RNN static | 5.99 | -5.36 | -11.36 | -0.53 |
| futures_long_only | Transformer static | -1.33 | 0.42 | 1.75 | N/A |
| futures_long_short | GRU static | 9.07 | 7.64 | -1.42 | -0.06 |
| futures_long_short | HMM + LSTM static | -10.63 | 0.24 | 10.87 | 1.46 |
| futures_long_short | LSTM static | 28.56 | 23.71 | -4.85 | -0.15 |
| futures_long_short | RNN static | 27.96 | 11.51 | -16.45 | -0.59 |
| futures_long_short | Transformer static | 26.90 | 24.70 | -2.20 | -0.14 |
| spot_long_only | GRU static | -3.25 | -2.25 | 1.00 | 0.04 |
| spot_long_only | HMM + LSTM static | 0.04 | -5.35 | -5.39 | -0.81 |
| spot_long_only | LSTM static | 4.04 | 6.02 | 1.98 | 0.07 |
| spot_long_only | RNN static | 2.92 | -5.70 | -8.62 | -0.48 |
| spot_long_only | Transformer static | -1.33 | 0.00 | 1.33 | N/A |

### Cost-aware variable-weight portfolio

| execution_mode | return_pct_2025_only | return_pct_native_history | return_pct_delta_native_minus_2025_only | sharpe_2025_only | sharpe_native_history | max_drawdown_pct_native_history |
| --- | --- | --- | --- | --- | --- | --- |
| futures_long_only | 1.42 | -5.51 | -6.93 | 0.21 | -0.61 | 15.54 |
| futures_long_short | 17.75 | 15.51 | -2.24 | 1.26 | 1.10 | 11.42 |
| spot_long_only | 1.66 | 4.57 | 2.92 | 0.23 | 0.60 | 6.11 |

The complete comparisons are in `training_window_comparison.csv` and `portfolio_training_window_comparison.csv`.

## Interpretation

- Futures long/short is the only valid short-selling case. Spot and the futures long-only control both clamp all short entries to zero.
- The raw Freqtrade comparison isolates strategy behavior after exchange fees. The portfolio comparison is the relevant cost-aware allocation validation because it adds modeled slippage and, for futures, observed funding.
- Spot and futures long-only can look close for slow Bollinger trades, but they are not duplicates: the candles, trained neural weights, HMM parameters, and funding treatment differ.
- Do not tune after reading this holdout. A rule change now needs a later untouched test period.
