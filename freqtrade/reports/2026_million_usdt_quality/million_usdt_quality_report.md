# USD 1 million capacity and backtest-quality report

This report reprices the frozen six-coin 2026 portfolio weights from 2026-01-01 through 2026-09-17 with a starting wallet of **USDT 1,000,000**. It adds a capacity-sensitive market-impact estimate and audits the research against the cited backtesting-pitfalls checklist.

## Result at the primary 10 bps slippage assumption

| portfolio | initial_equity_usdt | final_equity_usdt | profit_usdt | return_pct | sharpe | max_drawdown_pct | market_impact_cost_usdt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Ensemble equal | 1,000,000.00 | 1,249,319.64 | 249,319.64 | 24.93 | 0.88 | 23.07 | 7,413.39 |
| Ensemble equal + HMM gate | 1,000,000.00 | 1,148,231.60 | 148,231.60 | 14.82 | 0.80 | 14.83 | 17,082.82 |
| Ensemble variable | 1,000,000.00 | 1,161,514.08 | 161,514.08 | 16.15 | 1.16 | 9.70 | 4,410.64 |
| Ensemble variable + HMM gate | 1,000,000.00 | 1,070,401.89 | 70,401.89 | 7.04 | 0.83 | 6.29 | 5,084.16 |

These are portfolio-layer results. The target weights are unchanged from the frozen 2026 run, so differences from the earlier percentage results come from increasing slippage from 5 to 10 bps and adding the square-root market-impact estimate. Starting capital alone does not multiply percentage return; it converts the return into dollar P&L and can change return only through capacity-dependent costs.

## Slippage stress

| portfolio | slippage_bps_per_side | final_equity_usdt | profit_usdt | return_pct | max_drawdown_pct |
| --- | --- | --- | --- | --- | --- |
| Ensemble equal | 5.00 | 1,262,418.01 | 262,418.01 | 26.24 | 22.94 |
| Ensemble equal | 10.00 | 1,249,319.64 | 249,319.64 | 24.93 | 23.07 |
| Ensemble equal | 20.00 | 1,223,520.87 | 223,520.87 | 22.35 | 23.35 |
| Ensemble equal | 30.00 | 1,198,243.96 | 198,243.96 | 19.82 | 23.62 |
| Ensemble equal + HMM gate | 5.00 | 1,175,950.84 | 175,950.84 | 17.60 | 14.04 |
| Ensemble equal + HMM gate | 10.00 | 1,148,231.60 | 148,231.60 | 14.82 | 14.83 |
| Ensemble equal + HMM gate | 20.00 | 1,094,720.37 | 94,720.37 | 9.47 | 16.39 |
| Ensemble equal + HMM gate | 30.00 | 1,043,680.68 | 43,680.68 | 4.37 | 17.95 |
| Ensemble variable | 5.00 | 1,172,400.63 | 172,400.63 | 17.24 | 9.50 |
| Ensemble variable | 10.00 | 1,161,514.08 | 161,514.08 | 16.15 | 9.70 |
| Ensemble variable | 20.00 | 1,140,038.22 | 140,038.22 | 14.00 | 10.08 |
| Ensemble variable | 30.00 | 1,118,952.79 | 118,952.79 | 11.90 | 10.46 |
| Ensemble variable + HMM gate | 5.00 | 1,084,520.09 | 84,520.09 | 8.45 | 6.19 |
| Ensemble variable + HMM gate | 10.00 | 1,070,401.89 | 70,401.89 | 7.04 | 6.29 |
| Ensemble variable + HMM gate | 20.00 | 1,042,709.70 | 42,709.70 | 4.27 | 6.94 |
| Ensemble variable + HMM gate | 30.00 | 1,015,727.73 | 15,727.73 | 1.57 | 7.91 |

## Per-coin capacity for Ensemble variable

| symbol | orders | median_order_usdt | max_order_usdt | median_adv_usdt | max_participation_pct | p95_impact_bps | impact_cost_usdt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BTC | 105 | 3,617.1913 | 272,127.4111 | 11,196,709,636.0729 | 0.0039 | 0.7594 | 206.4010 |
| ETH | 196 | 2,198.5330 | 269,309.7668 | 9,048,379,094.6976 | 0.0037 | 0.8328 | 319.4650 |
| SOL | 136 | 1,913.8441 | 245,018.1910 | 2,042,167,575.3652 | 0.0129 | 2.2869 | 521.9307 |
| XRP | 141 | 1,440.1571 | 268,240.8281 | 736,556,947.6385 | 0.0679 | 3.4708 | 1,070.2996 |
| BNB | 133 | 2,963.1963 | 272,335.6724 | 411,469,735.6325 | 0.1293 | 3.7874 | 1,403.0140 |
| DOGE | 145 | 1,414.1225 | 270,266.2069 | 573,695,079.9565 | 0.1132 | 3.7268 | 889.5280 |

Capacity model: `impact rate = daily volatility × sqrt(order notional / trailing ADV)`. ADV and volatility use 30 prior days and are shifted one day, so the execution estimate does not use future liquidity or volatility. Quote volume is approximated as the sum of hourly `close × base volume`. This is an analytical approximation, not historical order-book reconstruction.

## Per-coin dollar P&L attribution for Ensemble variable

| symbol | price_pnl_usdt | funding_cost_usdt | fee_cost_usdt | slippage_cost_usdt | market_impact_cost_usdt | net_pnl_usdt | share_of_total_pnl_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BTC | -8,819.56 | 208.14 | 3,320.25 | 3,320.25 | 206.40 | -15,874.59 | -9.83 |
| ETH | 124,123.30 | 954.34 | 3,688.60 | 3,688.60 | 319.46 | 115,472.29 | 71.49 |
| SOL | -3,744.60 | 1,426.27 | 2,529.61 | 2,529.61 | 521.93 | -10,752.01 | -6.66 |
| XRP | 2,992.53 | 1,024.79 | 3,430.14 | 3,430.14 | 1,070.30 | -5,962.84 | -3.69 |
| BNB | 9,548.32 | 762.59 | 4,019.10 | 4,019.10 | 1,403.01 | -655.50 | -0.41 |
| DOGE | 84,101.52 | -547.07 | 2,236.16 | 2,236.16 | 889.53 | 79,286.73 | 49.09 |

The six net contributions add exactly to portfolio profit. A negative funding-cost number is a funding credit. Because capital compounds, these are dollar contributions calculated from each day's pre-return equity, not standalone per-coin backtests.

## Monte Carlo robustness

| portfolio | runs | positive_outcomes_pct | return_p05_pct | return_p50_pct | return_p95_pct | max_drawdown_p95_pct |
| --- | --- | --- | --- | --- | --- | --- |
| Ensemble equal | 1000 | 71.30 | -31.47 | 23.77 | 146.74 | 46.09 |
| Ensemble equal + HMM gate | 1000 | 69.70 | -23.68 | 14.51 | 79.69 | 34.42 |
| Ensemble variable | 1000 | 79.50 | -13.07 | 15.56 | 57.85 | 23.06 |
| Ensemble variable + HMM gate | 1000 | 71.60 | -10.26 | 7.43 | 30.80 | 16.73 |

The simulation uses 1,000 five-day block-bootstrap paths, perturbs price returns by ±10%, and perturbs fees, slippage, and impact by ±20%. It is a robustness distribution, not a forecast probability.

## 50% gross-return decay

| portfolio | base_return_pct | half_gross_return_pct |
| --- | --- | --- |
| Ensemble equal | 24.93 | 10.80 |
| Ensemble equal + HMM gate | 14.82 | 1.80 |
| Ensemble variable | 16.15 | 5.73 |
| Ensemble variable + HMM gate | 7.04 | 0.56 |

Gross market P&L is halved while observed funding and all execution costs remain fully charged.

## Line-by-line quality gate

Overall status: **FAIL** — 8 PASS, 3 PARTIAL, 8 FAIL, and 1 not applicable.

| check_id | check_item | status | evidence |
| --- | --- | --- | --- |
| 1.1 | Data coverage | PASS | Common six-coin history 2020-09-14 to 2026-09-17; more than five years. |
| 1.2 | Adjustment / roll handling | NOT_APPLICABLE | USD-M perpetuals do not expire or require a futures roll; raw exchange candles are used. |
| 1.3 | Survivorship bias | FAIL | The universe contains six currently surviving liquid coins and no delisted-contract history. |
| 1.4 | Timezone alignment | PASS | Candles, funding, signals, and portfolio dates are normalized to UTC. |
| 2.1 | Look-ahead bias | PARTIAL | Portfolio weights are lagged one day and principal rule/HMM checks exist, but not every neural variant has a fresh automated look-ahead run. |
| 2.2 | Data leakage | PASS | The primary models are frozen at 2025-12-31 and evaluated on 2026 without refitting. |
| 2.3 | Feature calculation | PARTIAL | Indicators are causal and execution is delayed, but the entire feature set lacks a single end-to-end mutation test. |
| 2.4 | Label definition | PASS | Future returns are training targets only; they are not available to the live feature matrix. |
| 3.1 | OOS versus training performance | FAIL | Comparable training-return records are not stored for every final method, so the >50% ratio cannot be verified. |
| 3.2 | Parameter stability +/-20% | FAIL | Bollinger has a coarse 20/40-day and 1.5/2.0/2.5 grid, not a complete +/-20% stability surface for every parameter and model. |
| 3.3 | Multiple-testing control | FAIL | Many strategies were explored; no project-wide Bonferroni, deflated-Sharpe, or probability-of-backtest-overfitting correction is complete. |
| 3.4 | Cross-period stability | FAIL | Several models and years fail the stated Sharpe >0.5 requirement. |
| 4.1 | Commission | PASS | The capacity run charges 10 bps per side. |
| 4.2 | Slippage | PASS | The capacity run reports 5, 10, 20, and 30 bps per-side scenarios. |
| 4.3 | Market impact | PARTIAL | Square-root impact is included; max modeled participation is 0.1293% but no order-book replay is available. |
| 4.4 | Funding costs | PASS | Observed Binance USD-M funding is charged at the portfolio layer. |
| 5.1 | Walk-forward validation | FAIL | The studies use chronological folds, but the final combined system does not have at least ten rolling validations. |
| 5.2 | Monte Carlo robustness | FAIL | 79.5% of 1,000 block-bootstrap perturbations finish positive; threshold is 90%. |
| 5.3 | Crisis stress test | FAIL | 2020 and 2022 appear in development history, but there is no separate full-system OOS crisis test; 2008 predates crypto. |
| 5.4 | 50% return decay | PASS | Halving gross price returns while retaining costs produces 5.73% for Ensemble variable. |

The strict rule is therefore **no live deployment yet**. The modelled USDT 1 million order sizes are small relative to reported exchange volume, but liquidity is not the main research blocker. Survivorship bias, incomplete project-wide multiple-testing correction, fewer than ten final walk-forward validations, and the absence of a separate crisis OOS test remain unresolved.

## Reproduction

```powershell
& '.\.freqtrade-venv\Scripts\python.exe' 'freqtrade/user_data/scripts/build_million_usdt_quality_report.py'
```

Inputs and assumptions are frozen in `config/million_usdt_backtest.json`. Detailed daily paths, individual Monte Carlo outcomes, the quality-gate CSV, and the per-coin capacity table are saved beside this report.

This is research, not financial advice or authorization to trade.
