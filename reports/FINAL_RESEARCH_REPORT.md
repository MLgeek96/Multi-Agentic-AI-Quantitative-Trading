# Final Crypto Trading Strategy Research Report

**Prepared:** 28 September 2026  
**Latest validated hourly market data:** 17 September 2026, 23:00 UTC  
**Latest common daily comparison:** 16 September 2026  
**Status:** research wrap-up; no strategy is approved for live capital

## 1. Purpose and scope

This report consolidates the completed research in this repository into one decision document. It separates the latest six-coin Freqtrade validation from the earlier BTC/ETH daily, pattern, classical-model, macro, and regime experiments. Results are reported as they were generated; previously viewed periods are not relabeled as pristine holdouts.

The main final experiment tests ten standalone strategy variants on BTC, ETH, SOL, XRP, BNB, and DOGE. It evaluates Binance USD-M futures long/short, futures long-only, and Spot long-only execution. The headline test runs from 1 January through 17 September 2026. Neural and HMM parameters are frozen before the 2026 test, with no 2026 refit. The primary HMMs were fit through 2024; the separate native-history HMM robustness run was fit through 2025.

The report is prepared on 28 September 2026, but it does not claim results for 18–28 September because validated candles for those dates are not present in the completed experiment.

## 2. Executive conclusion

The strongest evidence favors a simple 40-day Bollinger breakout or a controlled ensemble built around it. Added HMM, macro, and defensive-routing complexity did not earn its cost.

- In the primary six-coin futures long/short test, LSTM had the highest standalone return at **28.56%**; RNN had the best standalone closed-trade Sharpe at **1.06**; and the simple Bollinger control returned **25.90%**.
- The cost-aware variable ensemble returned **17.75%**, with **1.26 Sharpe** and **9.39% maximum drawdown** after a 10 bps fee, 5 bps modeled slippage, and observed futures funding.
- Adding the HMM risk gate to that portfolio reduced drawdown to **6.14%**, but return fell to **9.00%**. The gate is therefore a risk-reduction ablation, not the preferred return model.
- Every standalone HMM variant lost money in the primary 2026 six-coin test.
- Long-only transfer was weak. With 2025-only neural training, the variable portfolio returned **1.42%** on futures long-only and **1.66%** on Spot. With native-history training it returned **-5.51%** and **4.57%**, respectively.
- All six coins declined during the test. Short positions supplied approximately **77%** of LSTM profit and **91%** of simple Bollinger profit. The headline result is therefore materially dependent on short selling during a bearish sample.
- Longer neural training history did not consistently help. In futures long/short, RNN fell from **27.96%** to **11.51%**, while LSTM fell from **28.56%** to **23.71%**.
- Earlier BTC/ETH studies reach the same broad conclusion: Bollinger breakout remains the strongest control, while standalone HMM switching, macro-regime combinations, and pattern strategies do not pass the final robustness screen.

**Final research decision:** retain Bollinger 40-day breakout as the benchmark; retain the variable ensemble as a research candidate; reject HMM as a standalone alpha engine; do not deploy any result without a new untouched period, multi-seed neural checks, and live-like execution validation.

## 3. Research inventory

| Research block | Universe and period | Methods | Main result | Decision |
| --- | --- | --- | --- | --- |
| Pattern + momentum | BTC/ETH, Spot and futures; 2024–2025 holdout | Double reversal, triangles, flags | No method passed the minimum robustness screen | Reject |
| Daily adaptive portfolio | BTC/ETH Spot; 943-day validation | Adaptive SMA trend; Bollinger/RSI-filtered trend | Adaptive trend +10.09%; filtered version -7.23% | Keep baseline only for paper evaluation |
| Classical model selection | BTC/ETH futures; 2024–2025 holdout | MA, Bollinger mean reversion, Bollinger breakout, grid proxy, momentum, HMM, ridge | Selected Bollinger breakout +50.46%, Sharpe 1.112 | Retain as control |
| Two-state HMM baseline | BTC/ETH futures; 2024–2025 holdout | Momentum/mean-reversion regime switch | -21.21% holdout | Reject |
| Macro/volume HMM | BTC/ETH futures; 2025–Sep 2026 | Crypto, macro, volume, combined ablations | Selected combined -21.30%; breakout control +64.31% | Reject combined model |
| Gatekeeper | BTC/ETH futures; 2025–Sep 2026 | Breakout, MA gate, HMM throttle, both | Full gatekeeper +36.40% versus pure breakout +64.31% | Reject hierarchy |
| 2025 sequence baseline | BTC/ETH futures | Bollinger, RNN, GRU, LSTM, Transformer | Bollinger +54.71%; LSTM +51.97% | Retain simple control |
| 2025 altcoin transfer | SOL/XRP/BNB/DOGE futures | Bollinger, three neural gates, HMM variants | Bollinger +21.22% | Evidence of partial transfer |
| Three-state HMM | BTC/ETH futures, 2025 | Trend, sideways, switching, HMM+LSTM | Trend only +19.58%; combined +12.89%; sideways -11.01% | Trend sleeve only survived 2025 |
| Extended HMM lessons | BTC/ETH futures, 2025–Sep 2026 | Raw and defensive routers | Trend only +4.38%; defensive trend +1.60%; Bollinger +107.47% | Defensive exits rejected |
| 2026 daily forward validation | BTC/ETH Spot/futures | Reselected classical, macro, HMM, gatekeeper | Futures L/S strong Bollinger +26.55%; long-only MA +12.15% | Freeze; next test must be later |
| 2026 six-coin validation | Six coins; three execution modes | Ten standalone variants and four portfolios | Primary LSTM +28.56%; variable portfolio +17.75% | Main final comparison |

## 4. Main six-coin experiment

### 4.1 Experiment count

- Six coins: BTC, ETH, SOL, XRP, BNB, DOGE.
- Ten standalone variants.
- Three execution modes: futures long/short, futures long-only, Spot long-only.
- Two training designs: one static 2025 fit and pair-specific native history through 2025.
- Four portfolio construction methods per execution mode.
- Design matrix: `10 strategies × 6 coins × 3 modes × 2 training designs = 360` strategy/coin applications.
- Reported aggregates: 60 standalone strategy rows and 24 portfolio rows. These are scenario repetitions, not 60 or 360 distinct strategies.

### 4.2 Ten standalone variants

| Group | Variant | Definition |
| --- | --- | --- |
| Rule control | Bollinger 40d | Cross 40-day, 1.5-standard-deviation outer band; exit at middle band |
| Neural gate | RNN static | Bollinger entry plus correctly signed RNN 24-hour forecast above 0.20% magnitude |
| Neural gate | GRU static | Same rule and data; GRU architecture |
| Neural gate | LSTM static | Same rule and data; LSTM architecture |
| Neural gate | Transformer static | Same rule and data; Transformer architecture |
| HMM | HMM trend | Trade only the HMM trend sleeve |
| HMM | HMM trend defensive | Trend sleeve plus uncertainty/hysteresis and immediate crisis de-risking |
| HMM | HMM switching | Trend breakout plus sideways mean reversion; crisis to cash |
| HMM | HMM defensive | Full switching strategy plus uncertainty/hysteresis |
| Hybrid | HMM + LSTM static | HMM switching with LSTM confirmation on entries |

### 4.3 Primary standalone results

These are combined six-coin, futures long/short results using the static 2025 neural fit. Maximum drawdown is shown as a positive loss magnitude.

| Strategy | Trades | Long | Short | Return | Max drawdown | Sharpe | Profit factor | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Bollinger 40d | 45 | 30 | 15 | 25.90% | 11.90% | 0.93 | 2.08 | Benchmark retained |
| RNN static | 31 | 16 | 15 | 27.96% | 5.21% | 1.06 | 3.26 | Candidate; stability required |
| GRU static | 35 | 24 | 11 | 9.07% | 8.29% | 0.35 | Does not justify complexity |
| LSTM static | 37 | 21 | 16 | 28.56% | 6.02% | 1.02 | Highest return; candidate only |
| Transformer static | 17 | 1 | 16 | 26.90% | 2.50% | 0.97 | Too sparse and short-dominated |
| HMM trend | 73 | 35 | 38 | -7.73% | 17.39% | -0.68 | Reject |
| HMM trend defensive | 46 | 20 | 26 | -5.27% | 10.73% | -0.53 | Reject |
| HMM switching | 237 | 118 | 119 | -15.83% | 26.30% | -1.93 | Reject |
| HMM defensive | 211 | 105 | 106 | -14.48% | 24.40% | -2.00 | Reject |
| HMM + LSTM static | 123 | 54 | 69 | -10.63% | 18.05% | -1.43 | Reject |

### 4.4 Per-coin attribution

Each number is that coin's percentage-point contribution to the shared 10,000 USDT wallet. Rows reconcile to the strategy return; they are not buy-and-hold coin returns.

| Strategy | BTC | ETH | SOL | XRP | BNB | DOGE | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Bollinger 40d | 5.46% | 8.77% | 4.52% | 2.12% | 0.50% | 4.53% | 25.90% |
| RNN static | 1.45% | 11.69% | 3.20% | -1.22% | 4.84% | 8.01% | 27.96% |
| GRU static | 1.85% | 8.07% | -1.30% | -0.48% | 1.29% | -0.37% | 9.07% |
| LSTM static | 0.09% | 11.89% | 5.02% | 4.34% | 2.59% | 4.63% | 28.56% |
| Transformer static | 1.87% | 7.70% | 4.08% | 3.17% | 3.53% | 6.55% | 26.90% |
| HMM trend | -0.35% | -4.72% | -2.86% | 1.14% | -0.22% | -0.71% | -7.73% |
| HMM trend defensive | -0.84% | -4.22% | -1.66% | -0.28% | -0.52% | 2.23% | -5.27% |
| HMM switching | -1.98% | -4.34% | -5.24% | -3.46% | -0.42% | -0.39% | -15.83% |
| HMM defensive | -2.80% | -3.91% | -3.76% | -5.07% | -0.50% | 1.56% | -14.48% |
| HMM + LSTM static | -0.92% | -0.14% | 1.43% | -4.53% | -4.10% | -2.36% | -10.63% |

The successful models were concentrated in ETH and in short exposure. During the same test, buy-and-hold changes were BTC -13.98%, ETH -18.52%, SOL -19.90%, XRP -31.06%, BNB -14.54%, and DOGE -35.58%.

### 4.5 Portfolio results after fee, slippage, and funding

| Portfolio | Return | Annualized volatility | Sharpe | Max drawdown | Average gross exposure | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Equal ensemble | 27.12% | 49.01% | 0.93 | 22.82% | 79.90% | Return-high, risk-high control |
| Equal ensemble + HMM gate | 19.44% | 29.99% | 0.98 | 13.46% | 46.88% | HMM lowers exposure and return |
| Variable ensemble | 17.75% | 19.77% | 1.26 | 9.39% | 44.95% | Preferred research portfolio |
| Variable ensemble + HMM gate | 9.00% | 12.42% | 1.04 | 6.14% | Lowest drawdown, insufficient return improvement |

At 2, 5, and 10 bps one-way slippage, the variable-plus-HMM portfolio returned 9.86%, 9.00%, and 7.58%, respectively. The risk gate remained profitable but did not beat the ungated variable portfolio on Sharpe or return.

### 4.6 Execution-mode transfer

| Mode | Best standalone by reported Sharpe | Standalone return | Variable portfolio return | Variable portfolio Sharpe | Max drawdown |
| --- | --- | ---: | ---: | ---: | ---: |
| Futures long/short | RNN static | 27.96% | 17.75% | 1.26 | 9.39% |
| Futures long-only | RNN static | 5.99% | 1.42% | 0.21 | 10.69% |
| Spot long-only | LSTM static | 4.04% | 1.66% | 0.23 | 11.20% |

The long-only results do not support presenting the futures long/short result as a general directional forecasting edge.

### 4.7 Native-history robustness check

| Strategy | 2025-only training | Native-history training | Difference |
| --- | ---: | ---: | ---: |
| Bollinger 40d | 25.90% | 25.90% | 0.00 pp |
| RNN static | 27.96% | 11.51% | -16.45 pp |
| GRU static | 9.07% | 7.64% | -1.42 pp |
| LSTM static | 28.56% | 23.71% | -4.85 pp |
| Transformer static | 26.90% | 24.70% | -2.20 pp |
| HMM trend | -7.73% | -6.64% | 1.09 pp |
| HMM trend defensive | -5.27% | -6.16% | -0.89 pp |
| HMM switching | -15.83% | -15.49% | 0.33 pp |
| HMM defensive | -14.48% | -17.11% | -2.63 pp |
| HMM + LSTM static | -10.63% | 0.24% | 10.87 pp |

Native-history variable-portfolio results were 15.51% for futures long/short, -5.51% for futures long-only, and 4.57% for Spot long-only. Architecture rankings are not stable enough to designate one neural model as production-ready.

## 5. Effective parameter specification

The machine-readable companion is `reports/FINAL_PARAMETER_MANIFEST.json`. This section records the effective parameters needed to interpret and reproduce the main final experiment.

### 5.1 Common execution parameters

| Parameter | Value |
| --- | --- |
| Timeframe | 1 hour |
| Symbols | BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT |
| Primary market | Binance USD-M isolated perpetual futures |
| Validation window | 2026-01-01 through 2026-09-17 23:00 UTC |
| Initial wallet | 10,000 USDT |
| Maximum open trades | 6 |
| Fixed standalone stake | 1,666.66666667 USDT |
| Leverage | 1.0× |
| Standalone fee | 10 bps per side |
| Standalone funding/slippage | Excluded |
| Portfolio fee | 10 bps per unit of one-way turnover |
| Portfolio slippage | 5 bps per unit of one-way turnover |
| Portfolio funding | 4,680 observed Binance USD-M funding events |
| Signal timing | Hourly; portfolio samples at 23:00 UTC and applies weights to next daily return |

### 5.2 Bollinger control

| Parameter | Value |
| --- | ---: |
| Center window | 960 hours / 40 days |
| Band width | 1.5 standard deviations |
| Long entry | Fresh close cross above upper band |
| Short entry | Fresh close cross below lower band |
| Exit | Opposing cross of the middle band |
| Emergency stop | 25% |
| Trailing stop | Disabled |
| ROI exit | Disabled in practice; set to 100 to defer to signal exit |
| Startup history | 1,000 candles |

### 5.3 Sequence-model gates

All four neural variants share the trading rule, target, features, training loss, and optimizer settings. Only the sequence architecture changes.

| Parameter | Value |
| --- | --- |
| Base trade rule | Bollinger 40d control |
| Sequence length | 48 hourly candles |
| Prediction target | Next 24-hour log return |
| Entry threshold | Greater than +0.20% for long; less than -0.20% for short |
| Features | 18 causal features |
| Returns | 1h, 6h, 24h log returns |
| Candle features | Range, body |
| Volatility | 6h, 24h, 168h realized volatility |
| Trend distance | Price/MA distance at 24h, 120h, 960h |
| Volume | Log-volume change and 168h z-score |
| Momentum | RSI(14) divided by 100 |
| Calendar | Hour sine/cosine; weekday sine/cosine |
| 2025-static training | 365 days; one fit through 2025; 260-day backtest block prevents 2026 refit |
| Native-history training | Pair-specific 1,893–2,150 days futures and 1,927–2,150 days Spot |
| Internal validation | Chronological 90/10; no shuffle |
| Optimizer | AdamW |
| Loss | Huber |
| Learning rate | 0.0003 |
| Weight decay | 0.0001 |
| Epochs | Maximum 6 |
| Batch size | 128 |
| Early-stopping patience | 2 |
| Seed | 42 |
| Recurrent models | 1 layer, 32 hidden units, dropout 0.1 |
| Transformer | d_model 32, 4 heads, 1 layer, feed-forward 64, dropout 0.1 |

### 5.4 HMM and sleeve parameters

| Parameter | Value |
| --- | --- |
| Model | Pair-specific three-state diagonal-Gaussian HMM |
| States | Trend, sideways, crisis |
| Primary HMM fit window | 2020-01-01 through 2024-12-31 23:00 UTC |
| Native-history HMM fit window | Available history through 2025-12-31 23:00 UTC |
| Fit seeds | 11, 22, 33, 42, 77; choose highest likelihood |
| Maximum iterations | 200 |
| Fit tolerance | 0.0001 |
| HMM features | 24h return; 24h volatility; 168h volatility; volatility ratio; absolute 120h MA distance; 168h drawdown; 168h volume z-score |
| Causal inference | Forward-filtered probabilities only |
| Minimum state confidence | 55% |
| Crisis threshold | 45% probability; immediate cash exit |
| Defensive confirmation | 3 consecutive hourly observations for trend/sideways |
| Defensive uncertain handling | Block entry and exit to cash |
| Trend band | 20 days, 1.5 standard deviations |
| Trend confirmation | EMA(24) versus EMA(120), MACD(12,26,9), RSI above 55 or below 45 |
| Sideways band | 7 days, 2.0 standard deviations |
| Sideways RSI | Below 35 long; above 65 short |
| HMM emergency stop | 15% |
| HMM+LSTM trend threshold | ±0.20% forecast |
| HMM+LSTM sideways threshold | Correct forecast sign |

The primary HMM files are under `freqtrade/user_data/regime_models/`; full-history futures and Spot fits are under `regime_models_full_history/` and `regime_models_spot_full_history/`. These JSON files contain the fitted scaler, initial probabilities, transition matrices, state means, and variances for every coin.

### 5.5 Ensemble and allocation parameters

| Parameter | Value |
| --- | --- |
| Voting models | Bollinger, RNN, GRU, LSTM, Transformer |
| Direction rule | At least 3 of 5 models agree long or short |
| Equal allocation | Direction divided by max(4, active coin count) |
| Variable allocation | Direction × vote confidence ÷ trailing volatility |
| Volatility lookback | 30 daily observations; minimum 20 |
| Covariance lookback | 30 daily observations |
| Per-coin cap | 25% absolute portfolio weight |
| Portfolio volatility target | 20% annualized |
| Maximum gross exposure | 100% |
| HMM gate | Trend 1.0; sideways 0.5; crisis/uncertain 0.0 |
| Rebalance | Daily at 23:00 UTC signal boundary |
| Return application | One-day lag |

## 6. Parameters for supporting research

### 6.1 Pattern + momentum

- Structural bars: 4h; execution bars: 1h.
- Lookbacks: double reversal 60 structural bars; triangle 30; flag 16.
- Maximum holding: 21 days, 14 days, and 10 days, respectively.
- Volume gate: greater than 1.5 times the prior 20-bar average.
- RSI(14): long range 45–78; short range 22–55; divergence lookback 24 bars.
- MACD: 12/26 with 9-period signal; direction and slope must confirm.
- Minimum reward/risk: 3.0; account risk per trade: 1%; maximum notional leverage: 1×.
- Stop buffer: 0.5 ATR; breakeven at +1R; retain 33% of favorable excursion after +2R.
- Fee: 4 bps per side; slippage: 2 bps per side; drawdown kill-switch: 25%.
- Result: no pattern family passed the holdout robustness screen.

### 6.2 BTC/ETH daily adaptive portfolio

- SMA candidates: 10/50, 20/100, 30/150; 365-day trailing parameter window.
- Require positive trend and non-negative trailing training Sharpe.
- Volatility window 30 days; covariance window 60 days; 20% annualized target.
- Maximum asset weight 40%; fee 10 bps per turnover.
- Experimental confirmation: Bollinger(20, 2.0) and RSI(14) between 45 and 70.
- Result: adaptive trend +10.09%; experimental filter -7.23%; neither beat BTC.

### 6.3 Classical selected parameters

| Family | Frozen 2022–2023 selection used for 2024–2025 test |
| --- | --- |
| MA crossover | Fast 10, slow 50, no filter |
| Bollinger mean reversion | Window 20, width 2.5, exit z 0.25 |
| Bollinger breakout | Window 40, width 1.5, exit z 0.0 |
| Dynamic-grid proxy | Center 20, step 1%, 4 levels, trend threshold 3%, trend MA 20/100 |
| Momentum only | SMA 10/50, RSI 60/40, 3 votes |
| Two-state HMM switch | 730-day fit, 60-day refit, SMA 20/100, Bollinger width 1.5 |
| Ridge regression | 365-day fit, 30-day refit, penalty 1.0, volatility threshold 0.10 |

The final 2026 re-selection differs by execution mode. The exact nested choices are preserved in `reports/forward_2026_validation/selected_parameters.json` and indexed by the companion manifest rather than silently replacing the earlier selection.

### 6.4 Macro-regime and gatekeeper selections

- Macro-regime selected candidate: `macro_regime_08`; macro+volume features; 365-day HMM window; `breakout_flat`; no confirmation; robust score -0.6268. Final return -21.30%.
- Gatekeeper selected candidate: `gatekeeper_33`; macro+volume features; 365-day HMM window; low-volatility size 0.50; MA entry confirmation; robust score 0.2313. Full gatekeeper returned 36.40% versus 64.31% for pure breakout.
- Cost stress in both studies: 5, 10, 20, and 30 bps per unit of one-way turnover.

## 7. Evidence quality and limitations

### Strengths

- Checked Binance public candles with explicit market separation between Spot and USD-M futures.
- Causal indicators and next-bar or next-day application.
- Frozen parameter boundaries and development folds in the formal selection studies.
- Explicit controls and ablations for neural gates, HMM sleeves, macro features, and allocation gates.
- Long/short, futures long-only, and Spot long-only comparisons.
- Fee, slippage-scenario, funding, turnover, drawdown, and exposure reporting at the portfolio layer.
- Lookahead checks for principal Freqtrade rule/HMM strategies.

### Remaining weaknesses

- The 2026 test contains only about 260 days and a small number of long-duration breakout trades.
- Neural models use only seed 42 in the final comparison; multi-seed dispersion is unknown.
- The successful sample is bearish and short-dominated.
- Standalone Freqtrade rows exclude historical funding and slippage; only the portfolio overlay includes them.
- Slippage is modeled, not reconstructed from historical order books.
- The USDT 1 million extension adds an analytical square-root market-impact model, but still has no historical order-book replay, latency, exchange-outage, liquidation, or borrow-availability simulation.
- HMM state semantics can drift across samples even when state probabilities are causal.
- Several periods, especially 2025 and parts of 2026, were inspected by multiple studies and are no longer pristine.
- The September endpoint is incomplete relative to the 28 September report date.

### USDT 1 million capacity extension

The frozen six-coin portfolio weights were repriced from a **USDT 1,000,000** starting wallet without retuning. The extension charges 10 bps per-side fees, observed Binance USD-M funding, 5/10/20/30 bps slippage scenarios, and square-root market impact using trailing 30-day volatility and trailing 30-day quote-volume ADV. Both liquidity inputs are shifted one day.

At the primary 10 bps slippage setting:

| Portfolio | Final equity USDT | Profit USDT | Return | Sharpe | Max drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ensemble equal | 1,249,319.64 | 249,319.64 | 24.93% | 0.88 | 23.07% |
| Ensemble equal + HMM gate | 1,148,231.60 | 148,231.60 | 14.82% | 0.80 | 14.83% |
| Ensemble variable | 1,161,514.08 | 161,514.08 | 16.15% | 1.16 | 9.70% |
| Ensemble variable + HMM gate | 1,070,401.89 | 70,401.89 | 7.04% | 0.83 | 6.29% |

For the variable ensemble, the largest modeled order is USDT 272,335.67 and the maximum trailing-ADV participation is 0.1293%. Modeled market impact totals USDT 4,410.64. The result remains positive at 30 bps slippage (+11.90%), but only 79.5% of 1,000 block-bootstrap perturbations finish positive versus the referenced 90% quality threshold.

The line-by-line audit has **8 PASS, 3 PARTIAL, 8 FAIL, and 1 not applicable**, so the strict overall result is **FAIL / not live-approved**. The decisive unresolved items are survivorship bias, incomplete project-wide multiple-testing correction, incomplete ±20% parameter surfaces, fewer than ten final walk-forward rounds, and no separate full-system crisis OOS test. Full capacity, per-coin dollar attribution, Monte Carlo, return-decay, and gate results are in `freqtrade/reports/2026_million_usdt_quality/million_usdt_quality_report.md`.

### BTC, ETH, and altcoin-season extension

A separate three-state HMM was fit through 2025 using 30-day relative momentum and normalized strength for the BTC, ETH, and four-coin alt bucket, plus BTC/alt correlation, ETH/BTC correlation, and alt breadth. Each fit had to produce three occupied states that independently favored their assigned bucket; 2026 data was not used to fit or label the states. Signals and state-dependent weights are applied one day later.

The requested neutral allocation is defined as one-third BTC, one-third ETH, and one-third shared among active SOL/XRP/BNB/DOGE signals. With a USDT 1 million wallet and the same 10 bps fee, 10 bps slippage, observed funding, and market-impact assumptions:

| Portfolio | Return | Sharpe | Max drawdown | Turnover |
| --- | ---: | ---: | ---: | ---: |
| Original variable allocator | 16.15% | 1.16 | 9.70% | 18.67x |
| Signal equal buckets | 26.47% | 1.04 | 16.78% | 21.44x |
| Signal 50/25/25 HMM cycle tilt | 25.51% | 1.04 | 15.03% | 28.29x |
| Long-only equal-bucket benchmark | -19.52% | -0.31 | 46.92% | 1.00x |

The equal-bucket signal portfolio produced the highest final return, while the original variable allocator retained the best Sharpe and lowest drawdown among the active signal portfolios. The HMM tilt lowered drawdown slightly but also lowered return and increased turnover. Moreover, the HMM-named bucket led the following day only about one-third of the time, so cycle labels are retained as descriptive diagnostics rather than promoted to a production allocation rule. The full artifact is `freqtrade/reports/2026_market_cycle_hmm/market_cycle_report.md`.

## 8. Final strategy status

| Status | Strategy or component | Rationale |
| --- | --- | --- |
| Retain as benchmark | Bollinger 40d, width 1.5 | Strong, simple, reproducible, and consistently beats added HMM complexity |
| Retain for further research | Variable 3-of-5 ensemble | Best primary portfolio Sharpe after portfolio-level costs |
| Retain for stability testing | RNN and LSTM entry gates | Good primary results but unstable to training window and dependent on shorts |
| Diagnostic only | Transformer gate | Strong result but 17 trades, 16 of them short |
| Risk ablation only | HMM allocation gate | Lowers drawdown but also materially lowers return |
| Reject | HMM switching, defensive HMM, HMM+LSTM | Negative primary results and excessive turnover |
| Reject | Macro-regime combined model | Large negative final return; no incremental value over breakout |
| Reject | Full gatekeeper hierarchy | Underperforms pure breakout on return and Sharpe |
| Reject | Pattern + momentum families | No robust holdout survivor |
| Paper evaluation only | BTC/ETH adaptive daily trend | Positive validation but trails benchmarks |

## 9. Wrap-up checklist

- [x] Strategy universe and experiment counts reconciled.
- [x] Data and selection cutoffs stated explicitly.
- [x] Standalone, portfolio, execution-mode, and training-window results consolidated.
- [x] Per-coin attribution included.
- [x] Effective parameters and parameter-source registry recorded.
- [x] Successful and rejected components identified.
- [x] Known cost and execution omissions disclosed.
- [x] USDT 1 million capacity, market impact, slippage stress, Monte Carlo, return decay, and line-by-line quality gate added.
- [x] BTC/ETH/altcoin season HMM and equal-bucket allocation tested without 2026 refitting.
- [ ] Extend verified candles beyond 17 September only if a new report version is intentionally created.
- [ ] Run neural candidates over multiple seeds before any production decision.
- [ ] Reserve a genuinely new period; do not tune to the reported 2026 outcomes.
- [ ] Conduct exchange dry-run/paper execution with observed spread and fill slippage.
- [ ] Define a deployment stop criterion before committing capital.

## 10. Artifact map

| Purpose | Artifact |
| --- | --- |
| Machine-readable final parameters | `reports/FINAL_PARAMETER_MANIFEST.json` |
| Main six-coin report | `freqtrade/reports/2026_sixcoin_validation/validation_report.md` |
| Main standalone rows | `freqtrade/reports/2026_sixcoin_validation/standalone_freqtrade_results.csv` |
| Portfolio comparison | `freqtrade/reports/2026_sixcoin_validation/portfolio_comparison.csv` |
| Spot/futures scenarios | `freqtrade/reports/2026_execution_scenarios/validation_report.md` |
| Native-history robustness | `freqtrade/reports/2026_native_history_scenarios/validation_report.md` |
| BTC/ETH daily forward test | `reports/forward_2026_validation/research_report.md` |
| Classical model selection | `reports/model_selection/research_report.md` |
| Gatekeeper ablation | `reports/gatekeeper/research_report.md` |
| Macro-regime ablation | `reports/macro_regime/research_report.md` |
| Pattern study | `reports/pattern_momentum/research_report.md` |
| Main strategy implementations | `freqtrade/user_data/strategies/` |
| USDT 1 million capacity and quality audit | `freqtrade/reports/2026_million_usdt_quality/million_usdt_quality_report.md` |
| USDT 1 million assumptions | `config/million_usdt_backtest.json` |
| Market-cycle HMM report | `freqtrade/reports/2026_market_cycle_hmm/market_cycle_report.md` |
| Market-cycle assumptions | `config/market_cycle_hmm.json` |

This document is a research record, not financial advice or authorization to trade.
