# Frozen Cross-Market Validation

The parameters in this comparison were copied from the existing futures
development selections and were **not reselected on Spot or on the 2025
comparison period**. The common half-open validation window is
`2025-01-01` through `2026-01-01`. Every model uses next-day
execution, inverse-volatility sizing, a 50% per-asset cap, a 100% gross cap, a
20% annualized volatility target, and 10 bps per
unit of one-way turnover.

Three modes separate the source of performance:

- `spot_long_only`: ordinary Spot constraints; negative signals become cash.
- `futures_long_only`: futures prices with negative signals disabled.
- `futures_long_short`: the original signed perpetual-futures strategy.

## Core requested models

| execution_mode | model | total_return | maximum_drawdown | sharpe_ratio_zero_risk_free | average_daily_turnover | average_gross_exposure |
| --- | --- | --- | --- | --- | --- | --- |
| futures_long_only | strong_bollinger_breakout | 17.82% | -5.64% | 1.365 | 1.86% | 15.68% |
| futures_long_only | full_gatekeeper | 12.88% | -6.44% | 1.18 | 1.93% | 14.07% |
| futures_long_only | macro_regime | -1.19% | -3.9% | -0.207 | 1.7% | 2.39% |
| futures_long_only | hmm_switch | -4.16% | -5.98% | -0.392 | 4.96% | 9.03% |
| futures_long_short | strong_bollinger_breakout | 29.84% | -12.23% | 1.404 | 4.17% | 38.81% |
| futures_long_short | full_gatekeeper | 12.62% | -14.6% | 0.749 | 5.1% | 33.86% |
| futures_long_short | hmm_switch | -13.45% | -19.04% | -0.685 | 13.12% | 31.04% |
| futures_long_short | macro_regime | -12.82% | -14.44% | -1.494 | 6.31% | 8.66% |
| spot_long_only | strong_bollinger_breakout | 17.85% | -5.64% | 1.367 | 1.86% | 15.69% |
| spot_long_only | full_gatekeeper | 11.14% | -6.41% | 1.013 | 1.98% | 14.74% |
| spot_long_only | hmm_switch | -3.38% | -5.91% | -0.304 | 4.97% | 8.93% |
| spot_long_only | macro_regime | -2.5% | -4.14% | -0.396 | 1.76% | 3.92% |

## Best Sharpe in each execution mode

| execution_mode | model | total_return | maximum_drawdown | sharpe_ratio_zero_risk_free | average_daily_turnover | average_gross_exposure |
| --- | --- | --- | --- | --- | --- | --- |
| futures_long_only | gatekeeper_confirmation_only | 17.73% | -6.53% | 1.375 | 1.86% | 15.19% |
| futures_long_short | strong_bollinger_breakout | 29.84% | -12.23% | 1.404 | 4.17% | 38.81% |
| spot_long_only | gatekeeper_confirmation_only | 17.76% | -6.53% | 1.378 | 1.86% | 15.2% |

## Interpretation rules

This is a useful frozen-parameter transfer test, but not a new pristine
temporal holdout: 2025 has already appeared in earlier reports. Spot and
futures also have different microstructure and price formation. A result that
works only in `futures_long_short` may depend on short exposure; a result that
works in both long-only modes is stronger evidence that the directional rule
transfers across markets.

Funding, borrow availability, liquidation, bid/ask spread history, market
impact, and intraday fill sequencing remain unmodeled. `cost_stress.csv`
repeats the four core models at 5, 10, 20, and 30 bps without changing their
parameters.
