# BTC and ETH Freqtrade sequence-model baseline

## Bottom line

The pure Bollinger breakout was the best 2025 model in this controlled comparison. It returned
54.71% with a 9.03% wallet drawdown and a 1.40 daily-wallet Sharpe. LSTM came close on return at
51.97%, but its 10.21% drawdown was worse. GRU had the lowest drawdown at 6.28%, but gave up more
than half the baseline's profit. RNN was inferior to the baseline on both return and Sharpe. The
Transformer was the weakest neural gate: 2.16% return with an 8.16% drawdown and 0.20 Sharpe.

This does not establish a tradeable edge. Each model made only 12-19 trades, all five lost money
on BTC, and the results depend heavily on ETH. The correct baseline decision is to retain the
simple Bollinger version while the neural filters go through development-only tuning and
multi-seed stability tests.

## Final 2025 holdout results

| Strategy | Return | Max drawdown | Wallet Sharpe | Profit factor | Trades | Win rate | BTC return | ETH return |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Bollinger only | 54.71% | 9.03% | 1.40 | 2.98 | 19 | 36.84% | -0.78% | 55.49% |
| RNN gate | 40.16% | 8.95% | 1.16 | 2.65 | 15 | 33.33% | -12.55% | 52.71% |
| GRU gate | 24.69% | 6.28% | 1.11 | 2.43 | 13 | 46.15% | -0.45% | 25.14% |
| LSTM gate | 51.97% | 10.21% | 1.35 | 2.76 | 19 | 36.84% | -7.47% | 59.45% |
| Transformer gate | 2.16% | 8.16% | 0.20 | 1.11 | 12 | 33.33% | -5.68% | 7.84% |

All returns include a 0.10% entry fee and 0.10% exit fee. They exclude slippage and historical
funding because those series are not in the local archive. The backtest used 10,000 USDT initial
capital, 5,000 USDT stakes, at most two concurrent positions, isolated futures, and 1x leverage.

## What each strategy actually does

### Bollinger only

This is the control. On hourly candles it calculates a 40-day middle average (960 hours) and bands
1.5 standard deviations above and below it. A cross above the upper band opens a long; a cross
below the lower band opens a short. Longs exit when price crosses down through the middle band and
shorts exit when price crosses up through it. A 25% emergency stop exists, but every 2025 trade
closed through the middle-band rule.

It made eight longs and eleven shorts. Longs contributed 42.60 percentage points and shorts
12.11. ETH produced 55.49 percentage points, while BTC lost 0.78.

### RNN gate

The breakout and exit rules remain unchanged. A vanilla recurrent network sees the preceding 48
hourly feature vectors and forecasts the next 24-hour log return. The strategy accepts a long only
when the forecast is above +0.20%, and a short only when it is below -0.20%.

The gate removed four trades but did not materially reduce drawdown. Its short sleeve lost 1.35%
and BTC lost 12.55%, so the filter rejected useful trades or accepted the wrong BTC breakouts.

### GRU gate

GRU uses update and reset gates to retain information more selectively than a vanilla RNN. Every
other setting is identical. It produced the lowest drawdown and highest win rate, but only 13
trades and 24.69% return. Shorts supplied 20.01 percentage points of its 24.69% result.

This is the most defensive neural variant, not the best return model. Its smaller drawdown needs
confirmation across more folds and seeds before it deserves a risk-control role.

### LSTM gate

LSTM adds a separate memory cell with input, forget, and output gates. It nearly matched the
baseline return, but did so with higher drawdown. ETH returned 59.45 percentage points and BTC
lost 7.47, so the result is not a robust two-asset improvement.

The 2.74 percentage-point return gap versus the baseline is too small to justify the extra model
complexity when the neural model also has seed, retraining, monitoring, and model-drift risk.

### Transformer gate

The Transformer projects each hourly feature vector into 32 dimensions, adds a learned position
embedding, and applies one encoder layer with four self-attention heads and a 64-unit feed-forward
block. The last token summarizes the 48-hour window and feeds the same next-24-hour return head.
Every token is historical at prediction time, so the last token may attend to the full window
without a causal mask.

This baseline performed poorly. It accepted only 12 breakouts, won four, returned 2.16%, and had
an 8.16% drawdown. Its largest winner was one 28.03% ETH short. The other eleven trades lost
1,183.02 USDT in aggregate, so the small positive finish depended on that single trade. BTC had
one win and five losses for a -5.68% return. These settings provide no evidence that attention
improves the trading rule.

## Model and validation design

- The RNN, GRU, and LSTM each use one recurrent layer and 32 hidden units. The Transformer uses
  one 32-wide encoder layer, four attention heads, and a 64-unit feed-forward block. All neural
  runs use dropout 0.1, AdamW, Huber loss, batch size 128, up to six epochs, patience 2, and seed 42.
- Inputs are 18 causal features from the traded pair: returns, candle range and body, realized
  volatility, moving-average distance, RSI, volume change and z-score, and time-of-day/week cycles.
- Each pair is trained separately. No HMM state, stock index, interest-rate series, or cross-pair
  feature is used in these four runs.
- FreqAI uses a trailing 365-day training window and retrains every 90 days. The internal split is
  chronological 90/10 with no shuffle. The 2025 test uses successive out-of-sample forecasts.
- Random seeds are reset for each fold so architecture comparisons are repeatable.
- Freqtrade's lookahead-analysis found no bias in the Bollinger control: 20 tested signals, zero
  biased entries, zero biased exits. The neural variants were not run through that expensive
  signal-slicing audit; their features are causal and the future return appears only as the
  supervised training label.

## How to tune without overfitting

The 2025 holdout is now consumed because these results have been reviewed. Search only on rolling
90-day validation windows inside 2020-2024, freeze one specification, and wait for fresh
2026-or-later data for the next honest test. Reusing 2025 to select a tuned candidate would make it
an adaptive benchmark, not a clean holdout.

Use staged small grids instead of one large Cartesian search:

1. Tune the rule control first: band window 20/40/60 days and width 1.5/2.0. Keep the middle-band
   exit fixed.
2. Add simple controls before deep learning: momentum-only, Bollinger-only, ridge regression on
   next-period return, and a sign-classification model. A recurrent model must beat these after
   costs to justify its complexity.
3. Tune the forecast problem: sequence 24/48/168 hours, horizon 6/24/72 hours, and entry threshold
   0/0.20%/0.50%.
4. Tune capacity only after the forecast setup is stable: hidden size 16/32/64 and dropout
   0/0.1/0.2. Keep one layer initially.
5. Repeat surviving neural candidates across at least five fixed seeds. Reject candidates whose
   median result is good only because of one favorable initialization.

Rank candidates by median fold Sharpe, then apply penalties for maximum drawdown, very low trade
counts, seed dispersion, and concentration in one pair or direction. Do not pick the largest raw
return.

Run 0.05%, 0.10%, and 0.20% fee per side, add slippage scenarios, and obtain historical funding.
A model that fails at 0.20% per side or becomes unprofitable after realistic funding should not
advance to dry run.

## What is not tested yet

- 2026: the source data ends at 2025-12-31.
- HMM regime switching, stock indices, interest rates, and macro features.
- Historical funding, spread, market impact, liquidation behavior, and exchange outages.
- Momentum-only and linear/ridge controls.
- Multi-seed stability and development-only parameter selection.
- Formal lookahead-analysis for the custom neural strategy.

The next sensible experiment is not a larger Transformer. It is a compact rolling development
study that adds the simple controls, multiple seeds, and realistic costs, followed by a genuinely
new out-of-sample period.
