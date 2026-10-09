# BTC/ETH Daily Portfolio — Walk-Forward Comparison

Both models re-select the SMA pair independently for BTC and ETH every day using only trailing observations. The baseline requires a positive trend and non-negative trailing training Sharpe. `trend_bb_rsi` adds fixed confirmation gates: RSI(14) must be 45–70 and price must remain inside its 20-day, two-standard-deviation Bollinger Bands. Active assets receive capped inverse-volatility weights, then the portfolio is scaled to its annualized volatility target.

| period | model | observations | total_return | maximum_drawdown | sharpe_ratio_zero_risk_free | btc_benchmark_return | equal_weight_benchmark_return | closed_round_trips |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| development | adaptive_trend | 730 | -5.61% | -15.658% | -0.18331551156735693 | -11.397% | -25.399% | 18 |
| validation | adaptive_trend | 943 | 10.089% | -23.778% | 0.321172860559578 | 42.346% | 10.768% | 29 |
| development | trend_bb_rsi | 730 | -7.321% | -16.981% | -0.30694974567726446 | -11.397% | -25.399% | 61 |
| validation | trend_bb_rsi | 943 | -7.226% | -13.839% | -0.18392186159308208 | 42.346% | 10.768% | 89 |

## Interpretation

The Bollinger/RSI filter changed validation return from 10.09% to -7.23% and maximum drawdown from -23.78% to -13.84%. It did not improve return, so it remains an experimental variant rather than the live default.

This walk-forward comparison includes the configured 10 bps turnover charge. Indicator thresholds are standard fixed values rather than parameters selected on validation performance. It does not include taxes, exchange outages, bid/ask spread history, or market impact. The October 2026 evaluation remains untouched and is logged separately by the daily runner.
