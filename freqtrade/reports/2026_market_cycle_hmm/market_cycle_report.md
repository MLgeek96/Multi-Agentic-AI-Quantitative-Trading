# BTC, ETH, and altcoin-season HMM research

This extension tests the market-cycle hypothesis described in the referenced Binance Square post while preserving the original 2026 signal directions. The source is a third-party opinion article, so its Bitcoin-season, Ethereum-season, and altcoin-season narrative is treated as a testable hypothesis rather than a fact.

## Design

- Training: 2020-10-15 through 2025-12-31; validation: 2026-01-01 through 2026-09-17.
- Model: frozen three-state diagonal Gaussian HMM using 30-day relative momentum, normalized relative-strength shares, BTC/alt and ETH/BTC correlations, and alt breadth. No 2026 observations are used to fit, select, or label states.
- Mapping: each state receives one unique season label by maximizing its training-period mean 30-day relative momentum for the BTC, ETH, or four-coin alt bucket. Candidate fits are rejected unless every state actually favors its assigned bucket and every state occupies at least 10% of training observations.
- Causality: features are known after day T close; HMM state and target weights are applied to T+1 returns.
- Equal buckets: one third BTC, one third ETH, and one third altcoins. When all four alt signals are active, each has 8.33% absolute target weight. An inactive bucket remains cash.
- Experimental tilt: 50% to the HMM-favored bucket and 25% to each other bucket. It is compared against, not substituted for, equal buckets.
- Capital and costs: USDT 1,000,000; 10 bps fee and 10 bps slippage per side, observed funding, and the same square-root impact model as the USDT 1 million audit.

## Frozen HMM state mapping

| state | label | observations | occupancy_pct | bitcoin_relative_momentum_30d | ethereum_relative_momentum_30d | altcoin_relative_momentum_30d |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | altcoin_season | 557.0000 | 29.2542 | -0.0990 | -0.0843 | 0.1832 |
| 1 | bitcoin_season | 660.0000 | 34.6639 | 0.0607 | -0.0386 | -0.0221 |
| 2 | ethereum_season | 687.0000 | 36.0819 | -0.0180 | 0.0665 | -0.0485 |

Selected fit seed: 77; log likelihood: -15748.50; minimum state occupancy: 29.25%; minimum assigned-bucket semantic margin: 8.28 percentage points; converged: True.

## 2026 cycle mapping diagnostic

| cycle | days | share_of_validation_pct | average_confidence_pct | next_day_bitcoin_return_bps | next_day_ethereum_return_bps | next_day_altcoin_return_bps | expected_bucket_led_next_day_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bitcoin_season | 80 | 30.77 | 98.16 | -2.76 | -8.21 | 0.72 | 35.00 |
| ethereum_season | 127 | 48.85 | 99.67 | 25.37 | 34.54 | 24.89 | 33.33 |
| altcoin_season | 53 | 20.38 | 97.03 | -70.45 | -81.78 | -92.04 | 28.30 |

The last available classification on **2026-09-17** is **ethereum_season** at 100.00% confidence: BTC 0.00%, ETH 100.00%, altcoins 0.00%. This is the state at the data cutoff, not a current real-time signal.

## USDT 1 million portfolio comparison

| portfolio | final_equity_usdt | profit_usdt | return_pct | sharpe | max_drawdown_pct | total_turnover_x | market_impact_cost_usdt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Original variable allocator | 1,161,514.08 | 161,514.08 | 16.15 | 1.16 | 9.70 | 18.67 | 4,410.64 |
| Signal equal buckets | 1,264,735.51 | 264,735.51 | 26.47 | 1.04 | 16.78 | 21.44 | 6,485.30 |
| Signal 50/25/25 cycle tilt | 1,255,139.68 | 255,139.68 | 25.51 | 1.04 | 15.03 | 28.29 | 7,940.88 |
| Long-only equal-bucket benchmark | 804,751.23 | -195,248.77 | -19.52 | -0.31 | 46.92 | 1.00 | 173.64 |

The 50/25/25 HMM tilt **did not improve** Sharpe versus equal buckets in this validation. It reduced maximum drawdown, but also reduced final return and increased turnover. It must not be promoted merely because its final return is positive; the state labels were mapped in sample and the 2026 period is short.

## Monte Carlo comparison

| portfolio | runs | positive_outcomes_pct | return_p05_pct | return_p50_pct | return_p95_pct | max_drawdown_p95_pct |
| --- | --- | --- | --- | --- | --- | --- |
| Original variable allocator | 1000 | 78.10 | -13.21 | 14.55 | 57.88 | 22.97 |
| Signal equal buckets | 1000 | 76.60 | -25.29 | 25.40 | 128.08 | 39.25 |
| Signal 50/25/25 cycle tilt | 1000 | 75.80 | -24.96 | 24.88 | 119.57 | 40.56 |
| Long-only equal-bucket benchmark | 1000 | 28.20 | -62.89 | -22.52 | 64.72 | 68.12 |

These are 1,000 five-day block-bootstrap paths with ±10% return and ±20% execution-cost perturbations. They measure sensitivity, not forecast probabilities.

## Net P&L by execution cycle

| portfolio | cycle | days | net_pnl_usdt | average_daily_return_bps |
| --- | --- | --- | --- | --- |
| Original variable allocator | altcoin_season | 53 | 117,956.95 | 22.17 |
| Original variable allocator | bitcoin_season | 80 | 38,977.71 | 6.34 |
| Original variable allocator | ethereum_season | 127 | 4,579.42 | -0.36 |
| Signal equal buckets | altcoin_season | 53 | 287,352.68 | 50.84 |
| Signal equal buckets | bitcoin_season | 80 | -18,306.61 | 5.30 |
| Signal equal buckets | ethereum_season | 127 | -4,310.55 | -1.84 |
| Signal 50/25/25 cycle tilt | altcoin_season | 53 | 250,840.90 | 47.40 |
| Signal 50/25/25 cycle tilt | bitcoin_season | 80 | -36,396.94 | 0.98 |
| Signal 50/25/25 cycle tilt | ethereum_season | 127 | 40,695.72 | 1.36 |
| Long-only equal-bucket benchmark | altcoin_season | 53 | -331,957.81 | -82.18 |
| Long-only equal-bucket benchmark | bitcoin_season | 80 | -88,600.46 | -3.32 |
| Long-only equal-bucket benchmark | ethereum_season | 127 | 225,309.50 | 27.13 |

## Equal-bucket signal portfolio: per-coin contribution

| symbol | price_pnl_usdt | funding_cost_usdt | fee_cost_usdt | slippage_cost_usdt | market_impact_cost_usdt | net_pnl_usdt | share_of_total_pnl_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BTC | -5.16 | 288.50 | 4,426.93 | 4,426.93 | 451.84 | -9,599.35 | -3.63 |
| ETH | 214,815.07 | 3,610.23 | 4,236.61 | 4,236.61 | 749.47 | 201,982.15 | 76.30 |
| SOL | -7,214.23 | 1,951.92 | 2,899.61 | 2,899.61 | 805.46 | -15,770.82 | -5.96 |
| XRP | 11,109.72 | 1,958.43 | 3,787.41 | 3,787.41 | 1,411.21 | 165.25 | 0.06 |
| BNB | 11,173.23 | 693.51 | 4,355.57 | 4,355.57 | 1,597.02 | 171.56 | 0.06 |
| DOGE | 95,758.33 | 306.92 | 3,097.19 | 3,097.19 | 1,470.30 | 87,786.72 | 33.16 |

## Interpretation and decision

1. The HMM is a probabilistic clustering of relative momentum, normalized relative strength, breadth, and correlation. It does not observe a literal market-cycle label.
2. One-to-one state naming prevents all three states from being called “Bitcoin season,” but it cannot guarantee that the names remain economically stable out of sample.
3. The post also suggests BTC dominance, order books, news, sentiment, and on-chain data. Those are not present in this historical dataset, so they are not claimed here.
4. The equal-bucket portfolio is the governance baseline because its one-third sleeves are transparent. The HMM tilt remains experimental unless it improves multiple untouched periods after all costs.
5. This experiment reuses the already-inspected 2026 period and therefore is not a new pristine holdout.
6. In 2026, the bucket named by the HMM led the following day only about one third of the time. The cycle state is therefore descriptive, not demonstrated as a short-horizon predictor. Its near-100% probabilities are model-relative and are not calibrated real-world probabilities.

This is research, not financial advice or authorization to trade.
