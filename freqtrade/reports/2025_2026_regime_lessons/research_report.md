# Regime lessons applied: extended 2025–September 2026 OOS backtest

This is a research backtest, not a live-trading recommendation. The HMM/scaler remains fit only on 2020–2024 data. The evaluation ends at the latest complete checksum-verified daily archive, **2026-09-17 23:00 UTC**. The full 2025–2026 span is out of sample relative to model fitting, but 2025 was previously inspected, so **2026 YTD is the cleaner forward extension—not a pristine untouched holdout after this report is read**.

## What Lessons 12 and 13 add

- Judge regime detection by economic value after fees, drawdown, and switching—not classification accuracy alone.
- Keep probabilities and admit an explicit uncertain/transition state instead of forcing every gray-zone candle into trend or sideways.
- Use asymmetric switching: crisis protection should be immediate, while ordinary trend/sideways changes should require persistence.
- In uncertainty, prioritize risk reduction. Because this Freqtrade test uses indivisible 5,000 USDT slots rather than continuous sizing, the defensive implementation exits to cash and blocks new entries.
- Track switch frequency, uncertain-state share, and sleeve-level attribution so a regime router cannot hide excessive churn.

Implementation: crisis probability at or above 45% routes to cash immediately; trend/sideways requires confidence at or above 55% for three consecutive hourly candles; all other observations are `uncertain`. These thresholds were carried from the frozen model/local protocol, not selected on 2025–2026 results.

Sources: [Lesson 12: Regime Detection](https://waylandz.com/quant-book-en/Lesson-12-Regime-Detection/) and [Lesson 13: Regime Misjudgment and Systemic Collapse](https://waylandz.com/quant-book-en/Lesson-13-Regime-Misjudgment-and-Systemic-Collapse/).

## Full OOS results: 2025-01-01 through 2026-09-17

All results use 10,000 USDT starting capital, two 5,000 USDT slots, 1x leverage, and 0.10% fees per side. Funding, slippage, market impact, and liquidation dynamics remain excluded.

| model | return | max_drawdown | wallet_sharpe | profit_factor | trades | btc_return | eth_return |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HMM three sleeve | -0.73% | 22.12% | 0.048 | 0.992 | 151 | -5.04% | 4.31% |
| HMM defensive three sleeve | -9.48% | 21.71% | -0.431 | 0.864 | 121 | -3.06% | -6.42% |
| HMM trend only | 4.38% | 17.39% | 0.257 | 1.072 | 84 | 6.01% | -1.63% |
| HMM defensive trend only | 1.6% | 17.47% | 0.138 | 1.037 | 61 | 7.27% | -5.67% |
| Bollinger breakout control | 107.47% | 9.03% | 1.359 | 3.658 | 33 | 16.0% | 91.47% |

The defensive policy changed three-sleeve return by **-8.75 percentage points** and trend-only return by **-2.78 percentage points** versus their otherwise identical raw-HMM versions. A negative delta is still useful: it means the proposed protection cost more opportunity/turnover than it saved in this sample and should not be promoted merely because it sounds safer.

### Defensive exit attribution

| model | exit_reason | trades | net_profit_usdt | mean_net_return |
| --- | --- | --- | --- | --- |
| HMM defensive three sleeve | crisis_cash | 13 | 2731.31 | 4.21% |
| HMM defensive three sleeve | mean_reversion_middle | 26 | 2454.44 | 1.89% |
| HMM defensive three sleeve | trend_middle | 3 | -859.06 | -5.72% |
| HMM defensive three sleeve | uncertain_cash | 79 | -5274.97 | -1.34% |
| HMM defensive trend only | crisis_cash | 16 | 3026.42 | 3.79% |
| HMM defensive trend only | uncertain_cash | 39 | -1079.11 | -0.55% |
| HMM defensive trend only | trend_middle | 6 | -1787.4 | -5.96% |

The uncertainty rule is the failure point: it repeatedly crystallized small transition losses. The lesson is to test gradual exposure scaling or entry blocking separately from forced liquidation; combining all three in one hard cash switch is too blunt for this hourly model.

## Calendar split

| model | period | return | max_drawdown | wallet_sharpe |
| --- | --- | --- | --- | --- |
| HMM three sleeve | 2025 | 12.67% | 8.25% | 0.818 |
| HMM three sleeve | 2026_ytd | -11.89% | 20.3% | -1.194 |
| HMM defensive three sleeve | 2025 | -2.62% | 9.42% | -0.148 |
| HMM defensive three sleeve | 2026_ytd | -7.04% | 16.79% | -0.9 |
| HMM trend only | 2025 | 19.58% | 4.66% | 1.32 |
| HMM trend only | 2026_ytd | -12.71% | 17.39% | -1.684 |
| HMM defensive trend only | 2025 | 16.75% | 4.68% | 1.234 |
| HMM defensive trend only | 2026_ytd | -12.98% | 14.79% | -2.537 |
| Bollinger breakout control | 2025 | 54.71% | 9.03% | 1.391 |
| Bollinger breakout control | 2026_ytd | 18.04% | 3.3% | 1.651 |

## Router health

| symbol | observations | actual_start | actual_end | mean_confidence | raw_switches | defensive_committed_switches | uncertain_share | transition_pending_share | crisis_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTCUSDT | 15000 | 2025-01-01T00:00:00+00:00 | 2026-09-17T23:00:00+00:00 | 0.979 | 370 | 330 | 4.69% | 4.16% | 6.53% |
| ETHUSDT | 15000 | 2025-01-01T00:00:00+00:00 | 2026-09-17T23:00:00+00:00 | 0.979 | 356 | 311 | 4.29% | 3.86% | 10.53% |

`raw_switches` counts every argmax-label flip. `defensive_committed_switches` ignores uncertain rows and counts only changes among committed trend/sideways/crisis states. `transition_pending_share` isolates the three-candle hysteresis cost; the remainder of uncertain time comes from confidence below 55%.

## Interpretation rules

1. Prefer the simplest survivor that improves return/drawdown after fees across both assets; do not select a policy from 2025–2026 total return alone.
2. Treat the no-HMM Bollinger strategy as the economic-value control. If the router lowers Sharpe without a material drawdown benefit, it has not earned its complexity.
3. The defensive variant is an ablation, not a tuned winner. Validate confirmation lengths only on rolling 2022–2024 folds before freezing another future test.
4. Add historical funding, bid/ask slippage, a one-candle execution delay, and partial exposure scaling before any deployment decision.
