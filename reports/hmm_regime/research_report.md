# Two-State HMM Regime Baseline

This is a research backtest, not a live-trading recommendation. This first baseline uses only BTC and ETH return/volatility features; no macro data was supplied.

## Baseline design

- One shared two-state diagonal-Gaussian HMM is refit every 30 days on at most two years of trailing observations.
- States are relabeled after every fit: the state with greater BTC/ETH return variance is **high volatility**. Filtered probabilities use only data known by that close.
- High volatility: trade the majority direction of MACD(12,26,9), SMA(20/100), and RSI(14) above 55 or below 45. Two of three votes are required.
- Low volatility: enter long below the 20-day lower Bollinger Band or short above the upper band (2 standard deviations), then exit near the rolling mean.
- BTC and ETH signals are independent. The portfolio can be long one and short the other simultaneously, but each instrument has one net position.
- Signals formed at a daily close earn returns starting the next day. Sizing is inverse-volatility, capped at 50% per asset and 100% gross, then scaled down to a 20% annual volatility target.
- Trading cost is 10 bps per unit of one-way turnover. Funding, borrow constraints, spread history, liquidation, and market impact are not modeled.

The fitted regime was high-volatility on 41.8% of classified days and low-volatility on 58.2%. Mean estimated one-day persistence was 0.967 for high vol and 0.971 for low vol.

## Results

| period | observations | total_return | maximum_drawdown | sharpe_ratio_zero_risk_free | average_gross_exposure | btc_benchmark_return | equal_weight_benchmark_return |
| --- | --- | --- | --- | --- | --- | --- | --- |
| development | 730 | -6.37% | -20.4% | -0.094 | 24.24% | -11.3% | -24.41% |
| holdout | 731 | -21.21% | -35.32% | -0.565 | 29.74% | 98.07% | 65.52% |

Returns attributed to the regime that generated the prior close's applied position:

| period | regime | strategy | days | compounded_return | cost_return |
| --- | --- | --- | --- | --- | --- |
| development | high_volatility | momentum | 161 | 7.1% | 1.36% |
| development | low_volatility | mean_reversion | 569 | -12.57% | 3.67% |
| holdout | high_volatility | momentum | 462 | -12.78% | 6.53% |
| holdout | low_volatility | mean_reversion | 269 | -9.66% | 2.18% |

## How to select parameters without fooling yourself

1. Freeze the HMM structure first: compare 2 versus 3 states with walk-forward log likelihood, state stability, and minimum state occupancy—not strategy P&L. Keep two states unless a third state is persistent and interpretable across folds.
2. Tune only a small, economically sensible grid on the development period. Suggested tests: HMM training 365/730/1095 days; refit 14/30/60 days; SMA 10/50, 20/100, 50/200; Bollinger window 20/40 and width 1.5/2.0/2.5; momentum votes 2/3 or 3/3.
3. Use anchored or rolling walk-forward folds and rank configurations by median out-of-sample Sharpe, drawdown, turnover, and consistency across BTC and ETH. Do not choose on total return alone.
4. Leave 2024–2025 as untouched holdout while selecting on earlier folds. Apply a deflated-Sharpe or multiple-testing haircut when many configurations are tried.
5. Add macro variables as an ablation, not all at once. Start with stationary, lagged features such as S&P 500 return, VIX change, and 10-year-yield change. Retain a feature only if it improves several walk-forward folds after costs and does not make state labels unstable.
6. Stress costs to 15–30 bps and add perpetual funding before considering deployment. Re-run with one-bar and one-day extra execution delays to expose timing sensitivity.

## Reading this baseline

A weak or negative holdout result is useful evidence against these exact default rules; it is not a prompt to tune on the holdout. The next defensible experiment is a small development-only grid plus a no-HMM control (momentum-only and Bollinger-only) so the incremental value of regime switching is measurable.
