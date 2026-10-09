# 2026 Forward Validation After Selection Through 2025

All parameter choices were ranked on eight half-year folds from 1 January 2022
through 31 December 2025. The choices were then frozen and evaluated from
`2026-01-01` through `2026-09-17` (end exclusive), giving
**259 daily observations** through 16 September 2026.

Spot is evaluated long/cash. Futures is evaluated both long/cash and
long/short. Every portfolio applies a close-known signal to the following
day's return, charges 10 bps per unit of one-way
turnover, targets 20% annualized volatility, caps each asset at 50%, and caps
gross exposure at 100%.

## Core requested models

| execution_mode | model | total_return | maximum_drawdown | sharpe_ratio_zero_risk_free | average_daily_turnover | average_gross_exposure |
| --- | --- | --- | --- | --- | --- | --- |
| futures_long_only | strong_bollinger_40_1.5 | 6.59% | -8.86% | 0.652 | 2.08% | 20.68% |
| futures_long_only | bollinger_breakout_reselected | 5.31% | -9.58% | 0.552 | 2.08% | 19.52% |
| futures_long_only | full_gatekeeper_reselected | 2.86% | -8.17% | 0.387 | 1.75% | 18.29% |
| futures_long_only | hmm_switch_reselected | -8.81% | -18.64% | -1.034 | 3.79% | 14.98% |
| futures_long_only | macro_regime_reselected | -6.71% | -7.16% | -2.177 | 2.21% | 2.53% |
| futures_long_short | strong_bollinger_40_1.5 | 26.55% | -7.83% | 1.595 | 3.72% | 35.89% |
| futures_long_short | bollinger_breakout_reselected | 23.7% | -7.82% | 1.485 | 3.71% | 33.95% |
| futures_long_short | full_gatekeeper_reselected | 21.2% | -7.84% | 1.476 | 2.87% | 31.8% |
| futures_long_short | hmm_switch_reselected | -8.59% | -27.27% | -0.602 | 6.15% | 24.73% |
| futures_long_short | macro_regime_reselected | -1.94% | -3.78% | -0.948 | 2.78% | 1.81% |
| spot_long_only | strong_bollinger_40_1.5 | 6.59% | -8.86% | 0.652 | 2.08% | 20.69% |
| spot_long_only | bollinger_breakout_reselected | 5.32% | -9.57% | 0.552 | 2.09% | 19.52% |
| spot_long_only | full_gatekeeper_reselected | 2.85% | -8.18% | 0.387 | 1.75% | 18.29% |
| spot_long_only | macro_regime_reselected | -0.14% | -0.79% | -0.131 | 1.2% | 0.6% |
| spot_long_only | hmm_switch_reselected | -7.3% | -19.11% | -0.81 | 3.92% | 14.54% |

## Best test Sharpe in each execution mode

| execution_mode | model | total_return | maximum_drawdown | sharpe_ratio_zero_risk_free | average_daily_turnover | average_gross_exposure |
| --- | --- | --- | --- | --- | --- | --- |
| futures_long_only | ma_crossover_reselected | 12.15% | -7.23% | 1.069 | 2.32% | 25.43% |
| futures_long_short | strong_bollinger_40_1.5 | 26.55% | -7.83% | 1.595 | 3.72% | 35.89% |
| spot_long_only | ma_crossover_reselected | 12.14% | -7.24% | 1.068 | 2.32% | 25.44% |

## Validation status

This run does not use 2026 observations for parameter ranking. It is therefore
a correctly separated forward test for the re-selection procedure. However,
2026 had already been inspected in earlier futures reports, so it is not a
globally pristine holdout for the overall research project. No parameters
should now be changed in response to this table; the next clean confirmation
must use later data.

The Spot source is complete daily public-API data through 16 September 2026.
The futures source is complete hourly USD-M data through 17 September 2026;
the comparison deliberately stops one day earlier so every mode uses the same
dates. Macro series are available through 15–16 September and are lagged by
one day.

Funding, borrow availability, liquidation, historical bid/ask spreads, market
impact, and intraday fill sequencing are not modeled. Cost stress at 5, 10,
20, and 30 bps is reported separately without reselecting parameters.
