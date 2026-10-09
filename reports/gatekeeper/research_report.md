# HMM Gatekeeper Architecture Review

The attached proposal was implemented as a hierarchy rather than parallel strategies:

1. **HMM allocation throttle:** the HMM never selects long or short. High-volatility state receives full size; low-volatility state receives the selected fractional size.
2. **Core alpha:** Bollinger breakout with a 40-day center, 1.5-standard-deviation bands, and middle-band exit.
3. **Trend confirmation:** new long entries require bullish MA/momentum confirmation and new shorts require symmetric bearish confirmation. Once accepted, a position remains active until the Bollinger exit; a temporary confirmation change does not close it.

Parameters were selected on six rolling half-year folds from 2022–2024. The frozen final comparison covers 2025-01-01 through 2026-09-16.

## Selected gatekeeper

- HMM features: `macro_volume`
- HMM trailing window: 365 days; refit every 60 days
- Low-volatility position multiplier: 0.50
- Entry confirmation: `ma`

## Layer ablation, 2025–2026

| model | total_return | maximum_drawdown | sharpe_ratio_zero_risk_free | average_daily_turnover | average_gross_exposure |
| --- | --- | --- | --- | --- | --- |
| pure_breakout | 64.31% | -12.23% | 1.488 | 3.99% | 37.6% |
| confirmation_only | 52.8% | -15.4% | 1.291 | 3.89% | 36.37% |
| hmm_throttle_only | 38.38% | -13.99% | 1.108 | 4.62% | 34.11% |
| full_gatekeeper | 36.4% | -14.6% | 1.058 | 4.51% | 33.22% |

## Calendar split

| model | period | total_return | maximum_drawdown | sharpe_ratio_zero_risk_free |
| --- | --- | --- | --- | --- |
| pure_breakout | 2025 | 29.84% | -12.23% | 1.404 |
| pure_breakout | 2026_ytd | 26.55% | -7.83% | 1.595 |
| confirmation_only | 2025 | 22.06% | -15.4% | 1.102 |
| confirmation_only | 2026_ytd | 25.19% | -7.78% | 1.533 |
| hmm_throttle_only | 2025 | 13.83% | -13.99% | 0.818 |
| hmm_throttle_only | 2026_ytd | 21.57% | -7.92% | 1.471 |
| full_gatekeeper | 2025 | 12.62% | -14.6% | 0.749 |
| full_gatekeeper | 2026_ytd | 21.12% | -7.79% | 1.452 |

## What each result actually does

- **`pure_breakout`:** enters long when price closes above the 40-day upper band and short below the lower band, then exits at the 40-day middle band. There is no MA gate and no HMM sizing adjustment.
- **`confirmation_only`:** uses the same entries and exits, but a new long requires MA(10) above MA(50), while a new short requires MA(10) below MA(50). The confirmation is checked on entry only; it does not prematurely close an accepted trade.
- **`hmm_throttle_only`:** keeps every pure breakout trade, but the selected two-state HMM cuts position size to 50% in its low-volatility state and restores full size in its high-volatility state. The HMM cannot choose trade direction.
- **`full_gatekeeper`:** applies both the MA entry gate and the HMM position-size throttle.

All four variants use the same inverse-volatility portfolio allocator, a 50% per-asset cap, a 100% gross-exposure cap, a 20% annualized volatility target, next-day execution, and 10 bps cost per unit of turnover.

## Position episodes and trading costs

| model | position_episodes | profitable_episode_rate | average_holding_days | transaction_cost_return | net_contribution |
| --- | --- | --- | --- | --- | --- |
| pure_breakout | 33 | 45.5% | 28.8 | 2.49% | 53.41% |
| confirmation_only | 33 | 45.5% | 28.1 | 2.43% | 46.1% |
| hmm_throttle_only | 33 | 48.5% | 28.8 | 2.88% | 35.48% |
| full_gatekeeper | 33 | 48.5% | 28.1 | 2.82% | 34.07% |

`net_contribution` is the arithmetic sum of daily portfolio-return contributions assigned to position episodes, not the compounded portfolio return. Costs on sign flips are split between closing the old position and opening the new one. The exact daily reconciliation is in `daily_trading_log.csv.gz`; the readable entry-to-exit view is in `trade_ledger.csv`.

## Verdict

The hierarchy did not improve on the pure breakout control and should remain rejected.

The relevant decision is not whether the gatekeeper is theoretically appealing, but whether `full_gatekeeper` improves both Sharpe and drawdown relative to `pure_breakout` across development folds, final evaluation, and stressed costs. If it only lowers exposure and return without improving drawdown efficiency, the HMM is adding complexity rather than useful information.

## Review notes

- The throttle formulation fixes the earlier conceptual problem: HMM state no longer creates counter-trend trades.
- Long and short confirmations are symmetric; the screenshot's long-only wording would otherwise bias a futures backtest.
- The no-HMM breakout remains the mandatory control. HMM complexity is accepted only if it adds incremental evidence after costs.
- 2025 was already examined in earlier work, so this is an extended backtest rather than a pristine holdout.
- Funding, intraday spread, and event-driven fills remain unmodeled.

## Audit files

- `equity_curves.csv`: chart-ready equity, drawdown, exposure, and daily-return series for every model.
- `trade_ledger.csv`: one row per BTC/ETH directional position episode, including dates, direction, weights, underlying move, P&L contribution, and allocated costs.
- `daily_trading_log.csv.gz`: every model/date/symbol decision and rebalance, including prior-close signal, HMM state, target/applied weights, turnover, gross contribution, costs, and net contribution.
- `all_model_signals.csv.gz` and `all_model_portfolios.csv.gz`: full raw model outputs for independent checking.
