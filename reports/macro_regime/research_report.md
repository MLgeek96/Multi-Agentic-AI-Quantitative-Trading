# Combined HMM + Macro Relationships + Volume

The current model now combines: (1) a two-state HMM; (2) BTC/ETH return and volatility; (3) lagged S&P 500, Nasdaq, VIX, 10-year-yield, and effective-fed-funds changes; (4) 60-day rolling crypto/macro correlations; and (5) volume surprise plus taker-buy imbalance. It does **not** assume a permanent inverse relationship. Rolling correlations and ridge coefficients are allowed to change sign.

The small grid was selected on six half-year folds from 2022 through 2024. The final period is 2025-01-01 through 2026-09-16. Because 2025 was already viewed in earlier research, this is an extended backtest rather than a pristine unseen holdout.

## 2025–2026 results

| label | rule_pair | confirmation | total_return | maximum_drawdown | sharpe_ratio_zero_risk_free | average_daily_turnover |
| --- | --- | --- | --- | --- | --- | --- |
| crypto_only | momentum_mean_reversion | none | -6.33% | -22.25% | -0.11 | 11.04% |
| crypto_volume | momentum_mean_reversion | none | -10.46% | -30.53% | -0.259 | 23.63% |
| crypto_macro | momentum_mean_reversion | none | -37.84% | -47.01% | -1.48 | 11.41% |
| macro_volume | momentum_mean_reversion | none | -33.4% | -44.33% | -1.158 | 14.43% |
| selected_combined | breakout_flat | none | -21.3% | -22.2% | -1.585 | 5.55% |
| bollinger_breakout_control | breakout_all_regimes | none | 64.31% | -12.23% | 1.488 | 3.99% |

### Calendar split

| label | period | total_return | maximum_drawdown | sharpe_ratio_zero_risk_free |
| --- | --- | --- | --- | --- |
| selected_combined | 2025 | -12.82% | -14.44% | -1.494 |
| selected_combined | 2026_ytd | -9.72% | -10.98% | -1.726 |
| bollinger_breakout_control | 2025 | 29.84% | -12.23% | 1.404 |
| bollinger_breakout_control | 2026_ytd | 26.55% | -7.83% | 1.595 |

The development-selected combined candidate used `macro_volume`, a 365-day HMM window, `breakout_flat`, and `none` macro/volume confirmation. It returned **-21.30%**, with Sharpe **-1.585** and maximum drawdown **-22.20%**.

During the final period, median BTC correlations were 0.406 with the S&P 500 and -0.057 with 10-year-yield changes. ETH correlations were 0.463 and -0.056, respectively. The equity relationship was positive, while the rate relationship was weakly negative—not a stable blanket inverse relationship.

## How to fine-tune responsibly

1. Tune feature sets and HMM state quality separately from trade-rule thresholds. Reject HMM fits with unstable state labels, tiny state occupancy, or implausibly short persistence.
2. Keep grids small: HMM windows 365/730/1095 days, refits 30/60/90 days, breakout windows 20/40/60, band widths 1.5/2.0/2.5, and confirmation thresholds 0/0.05/0.10 daily volatility.
3. Select by median walk-forward Sharpe with penalties for dispersion, drawdown, turnover, and near-zero exposure. Do not select on the final-period return.
4. Check coefficient-sign stability. A supposed inverse rate relationship that changes sign in most refits is not a dependable trading rule.
5. Require ablations: crypto-only HMM, +volume, +macro relationships, +both, and a no-HMM technical control. The combined model is useful only if it improves consistently after costs.
6. Before deployment, add perpetual funding and an hourly event-driven execution test. Daily closes cannot represent intraday band or grid fills.
