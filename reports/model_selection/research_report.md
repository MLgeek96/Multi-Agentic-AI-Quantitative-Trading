# BTC/ETH Development-Only Model Selection

All tests use the local hourly Binance USD-M futures files listed in `source_manifest.json`, aggregated to complete UTC days. Parameters were selected only from four rolling six-month folds inside 2022–2023. The 2024–2025 holdout was evaluated only after one configuration per family had been frozen.

The attached reference was implemented as MA crossover (including optional MACD and volume confirmation), Bollinger mean reversion, Bollinger breakout, and a dynamic-grid proxy. The grid result is a daily-close staged-exposure approximation, not a simulation of intraday limit-order fills.

## Default baselines and development-selected models

| stage | family | period | total_return | maximum_drawdown | sharpe_ratio_zero_risk_free | average_daily_turnover | average_gross_exposure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| default_baseline | ma_crossover | development | -10.78% | -36.86% | -0.174 | 9.93% | 43.63% |
| default_baseline | ma_crossover | holdout | -15.34% | -22.35% | -0.292 | 10.44% | 47.53% |
| default_baseline | bollinger_mean_reversion | development | -15.55% | -24.3% | -0.378 | 5.06% | 23.55% |
| default_baseline | bollinger_mean_reversion | holdout | -3.64% | -20.22% | -0.026 | 5.4% | 25.54% |
| default_baseline | bollinger_breakout | development | -1.03% | -28.72% | 0.064 | 4.82% | 25.13% |
| default_baseline | bollinger_breakout | holdout | -16.47% | -28.55% | -0.424 | 5.35% | 27.69% |
| default_baseline | dynamic_grid | development | -28.3% | -28.89% | -1.505 | 3.68% | 9.08% |
| default_baseline | dynamic_grid | holdout | -7.04% | -15.76% | -0.303 | 5.12% | 10.54% |
| default_baseline | momentum_only | development | 11.75% | -22.21% | 0.382 | 11.48% | 34.59% |
| default_baseline | momentum_only | holdout | -0.15% | -24.54% | 0.093 | 14.27% | 37.23% |
| default_baseline | hmm_switch | development | -6.37% | -20.4% | -0.094 | 6.89% | 24.24% |
| default_baseline | hmm_switch | holdout | -21.21% | -35.32% | -0.565 | 11.92% | 29.74% |
| default_baseline | linear_regression | development | -16.86% | -46.43% | -0.354 | 16.13% | 38.34% |
| default_baseline | linear_regression | holdout | -49.05% | -52.86% | -1.533 | 28.77% | 37.54% |
| development_selected | ma_crossover | development | 13.9% | -21.87% | 0.423 | 4.39% | 43.69% |
| development_selected | ma_crossover | holdout | 7.44% | -23.89% | 0.276 | 5.05% | 46.51% |
| development_selected | bollinger_mean_reversion | development | -9.26% | -22.07% | -0.221 | 3.49% | 17.4% |
| development_selected | bollinger_mean_reversion | holdout | -31.21% | -35.11% | -1.256 | 2.5% | 15.8% |
| development_selected | bollinger_breakout | development | 42.76% | -13.97% | 1.01 | 3.38% | 31.87% |
| development_selected | bollinger_breakout | holdout | 50.46% | -13.86% | 1.112 | 4.25% | 35.81% |
| development_selected | dynamic_grid | development | -18.0% | -18.88% | -0.946 | 3.69% | 6.84% |
| development_selected | dynamic_grid | holdout | -6.11% | -14.09% | -0.253 | 3.98% | 8.96% |
| development_selected | momentum_only | development | 7.37% | -17.25% | 0.315 | 7.05% | 14.81% |
| development_selected | momentum_only | holdout | 2.2% | -16.63% | 0.147 | 8.03% | 16.68% |
| development_selected | hmm_switch | development | 0.2% | -19.97% | 0.102 | 8.46% | 29.9% |
| development_selected | hmm_switch | holdout | -32.06% | -37.27% | -0.92 | 12.57% | 31.97% |
| development_selected | linear_regression | development | 5.28% | -37.03% | 0.229 | 15.34% | 34.92% |
| development_selected | linear_regression | holdout | -53.56% | -55.92% | -1.83 | 24.8% | 32.2% |

## Outcome

The highest selected-model holdout Sharpe was **1.112** for **bollinger_breakout**, with return **50.46%** and maximum drawdown **-13.86%**. This is a comparison result, not sufficient evidence for deployment.

`selected_parameters.json` contains the frozen choices. `development_candidate_scores.csv` and `development_fold_metrics.csv` show why each choice won. `cost_stress.csv` applies 5, 10, 20, and 30 bps per unit of one-way turnover without reselecting parameters.

## Selection rule

The robust development score is median fold Sharpe minus penalties for Sharpe dispersion, worst fold drawdown, turnover, and near-zero exposure. Total return is reported but is not the selection objective. HMM state estimation and linear regression are both walk-forward; a close's signal is applied to the following day's return.

## Important limitations

- Perpetual funding, order-book spreads, liquidation, latency, and market impact are absent.
- The daily grid proxy cannot establish whether real intraday grid orders would fill in a favorable sequence. That requires an hourly event-driven fill model.
- Seeing the holdout means it must now remain locked. Any additional ideas should be selected on earlier data or a later forward period, not tuned to 2024–2025.
- A linear model can be useful as a control, but a positive in-sample coefficient or forecast is not proof of a stable market relationship.
