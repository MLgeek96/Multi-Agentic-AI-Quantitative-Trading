# Pattern + Momentum Strategy Research

Generated from the checked Binance candles in this workspace. This is a research artifact, not financial advice or a live-trading system.

## Design

- Structural timeframe: completed 4-hour candles resampled from 1-hour data.
- Execution timeframe: 1-hour, with signals filled at the next available open.
- Strategies: double-top/bottom reversal, ascending/descending triangle breakout, bull/bear flag continuation.
- Confirmation: volume greater than 1.5x the prior 20-bar average, RSI exhaustion/divergence gate, and MACD direction plus slope.
- Risk: logical pattern invalidation stop, projected pattern target, minimum 3.0 reward/risk at the actual modeled fill, and at most 1% account risk.
- Management: breakeven at +1R; from +2R, a stop retaining 33% of maximum favorable excursion; one position per strategy; 25% drawdown kill-switch.
- Costs: configured fee and slippage on both entry and exit. Same-bar stop/target collisions resolve to the stop.

## Holdout results (2024-01-01 through 2025-12-31)

| market | symbol | strategy | trades | total_return_pct | max_drawdown_pct | sharpe | profit_factor | expectancy_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| usdt_futures | BTCUSDT | double_reversal | 20 | -3.911 | -8.209 | -0.392 | 0.641 | 0.017 |
| usdt_futures | BTCUSDT | flag_breakout | 2 | -2.08 | -2.516 | -1.485 | 0.0 | -1.093 |
| usdt_futures | BTCUSDT | triangle_breakout | 9 | -3.573 | -5.736 | -0.724 | 0.441 | -0.393 |
| usdt_futures | ETHUSDT | double_reversal | 9 | 10.634 | -2.701 | 1.159 | 9.126 | 1.143 |
| usdt_futures | ETHUSDT | flag_breakout | 1 | -1.047 | -1.047 | -0.707 | 0.0 | -1.047 |
| usdt_futures | ETHUSDT | triangle_breakout | 13 | -4.913 | -6.694 | -0.732 | 0.147 | -0.386 |
| spot | BTCUSDT | double_reversal | 9 | -0.446 | -3.625 | -0.064 | 0.919 | -0.191 |
| spot | BTCUSDT | flag_breakout | 1 | -1.027 | -1.458 | -0.946 | 0.0 | -1.107 |
| spot | BTCUSDT | triangle_breakout | 5 | -4.43 | -4.949 | -1.442 | 0.0 | -1.121 |
| spot | ETHUSDT | double_reversal | 3 | 2.959 | -0.956 | 0.889 | 19.984 | 0.972 |
| spot | ETHUSDT | flag_breakout | 1 | -1.047 | -1.047 | -0.707 | 0.0 | -1.047 |
| spot | ETHUSDT | triangle_breakout | 7 | -2.461 | -3.25 | -0.48 | 0.0 | -0.354 |

Zero trades or weak results are retained rather than hidden. A strategy should not be selected from this table alone.

## Interpretation

None of the hypotheses passes a modest robustness screen of at least 20 holdout trades, positive return, positive Sharpe, and profit factor above 1. Positive holdout rows were: usdt_futures ETHUSDT double_reversal (9 trades); spot ETHUSDT double_reversal (3 trades). Sparse positive rows are hypotheses for further testing, not evidence of a deployable edge.

## Signal funnel

| market | symbol | strategy | patterns | confirmed | volume_reject | rsi_reject | macd_reject |
| --- | --- | --- | --- | --- | --- | --- | --- |
| usdt_futures | BTCUSDT | double_reversal | 235 | 100 | 113 | 9 | 13 |
| usdt_futures | BTCUSDT | flag_breakout | 15 | 4 | 9 | 2 | 0 |
| usdt_futures | BTCUSDT | triangle_breakout | 174 | 79 | 79 | 6 | 10 |
| usdt_futures | ETHUSDT | double_reversal | 183 | 67 | 101 | 3 | 12 |
| usdt_futures | ETHUSDT | flag_breakout | 7 | 2 | 3 | 1 | 1 |
| usdt_futures | ETHUSDT | triangle_breakout | 133 | 62 | 55 | 8 | 8 |
| spot | BTCUSDT | double_reversal | 228 | 100 | 112 | 7 | 9 |
| spot | BTCUSDT | flag_breakout | 17 | 4 | 11 | 2 | 0 |
| spot | BTCUSDT | triangle_breakout | 166 | 71 | 83 | 4 | 8 |
| spot | ETHUSDT | double_reversal | 184 | 74 | 99 | 3 | 8 |
| spot | ETHUSDT | flag_breakout | 10 | 1 | 6 | 1 | 2 |
| spot | ETHUSDT | triangle_breakout | 127 | 50 | 63 | 6 | 8 |

## Important limitations

- The available files are 1-hour candles. The specification's preferred 15-minute execution layer is not yet present.
- Perpetual funding, liquidation mechanics, variable fees, spread history, order-book depth, latency, and market impact are not in the source data and are therefore not modeled.
- OHLC bars do not reveal the path within a candle. The engine uses a deliberately conservative stop-first rule.
- The development/holdout split is a first defense against overfitting, not proof of future profitability. Parameters have not been optimized on the holdout set.
- BTC and ETH are tested independently; portfolio correlation and simultaneous account-level exposure are not modeled.

## Files

- `summary.csv`: development and holdout metrics.
- `candidate_summary.csv`: pattern detections and confirmation outcomes.
- `candidates.csv`: every structural signal, including rejected momentum gates.
- `trades.csv`: completed simulated trades.
- `audit_log.csv`: reconciled entry and exit fill references.
- `rejections.csv`: execution-stage rejections, primarily the 1:3 gate.
- `equity.csv.gz`: timestamped mark-to-market curves.
