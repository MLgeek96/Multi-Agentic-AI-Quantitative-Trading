# Mandate: Algorithmic Trading Strategy Project (25%)
**Target:** Automated Out-of-Sample Portfolio Strategy  
**Execution Window (Test Period):** 1 October 2026 – 23 October 2026 (Week 11 Final Evaluation)  
**Team Structure:** 4–5 Members (Mandatory explicit attribution of individual responsibilities)  
**Deliverables:** Live-tested Strategy Code, Presentation Deck, and Portfolio Daily Closing Prices CSV  

---

## 0. Repository Implementation Decision and Current Status (16 September 2026)

### What the API does—and does not do

The exchange API supplies **market data**. The strategy code in this repository computes the forecast, signal, target weights, paper orders, and KPIs. Signals are not downloaded from Binance.

The implemented workflow uses Binance's public Spot REST market-data endpoint and therefore requires **no API key**. Authenticated account/order endpoints are intentionally disabled. Real-money execution is not required for the daily paper evaluation unless the instructor explicitly says otherwise; if execution evidence is required, add a separate Binance Spot Testnet adapter only after paper results and controls are approved.

```text
Binance public daily candles
            │
            ▼
Eligibility + continuity validation
            │
            ▼
Daily trailing-window parameter selection
            │
            ▼
Trend/quality signal ──► capped inverse-volatility weights
            │
            ▼
Paper rebalance + costs + unique order references
            │
            ▼
Closing-price CSV + signal/order ledgers + KPI JSON
```

### Selected assignment strategy

* **Universe:** `BTCUSDT` and `ETHUSDT` Spot. The first strategy iteration deliberately focuses on these two assets; they remain supplemental instruments until the class's mandatory core assets are supplied.
* **Forecast:** Daily long/cash adaptive trend model. Each asset selects among 10/50, 20/100, and 30/150 SMA pairs using its trailing 365-day net-of-cost Sharpe ratio.
* **Signal gate:** A long allocation requires both a positive trend and non-negative trailing training Sharpe; otherwise the asset remains in cash.
* **Bollinger/RSI experiment:** A comparison variant additionally requires RSI(14) between 45 and 70 and price inside 20-day, two-standard-deviation Bollinger Bands. It is implemented but not selected as the live default because it reduced validation return.
* **Portfolio construction:** Capped inverse-volatility allocation, 40% maximum per asset, scaled to a 20% annualized portfolio-volatility target. No leverage or shorting.
* **Friction:** 10 bps charged on paper turnover.
* **Model update:** Parameters and weights are re-estimated after every completed UTC daily candle.

### Implemented components

| Requirement | Implementation | Status |
| :--- | :--- | :--- |
| Public daily ingestion | `crypto_quant/binance_public.py` | Complete and live-tested |
| Eligibility check | Listing date must precede 1 Aug 2025; configured assets verified | Complete |
| Automated model update | Rolling parameter selection in `crypto_quant/daily_portfolio.py` | Complete |
| Forecast and target holdings | Daily signal and volatility-aware target weights | Complete |
| Paper execution | Turnover, fees, positions, order references, closed trade episodes | Complete |
| Required closing-price file | `live/portfolio_closing_prices.csv` | Ready; rows begin 1 Oct 2026 |
| KPI monitoring | `live/portfolio_kpis.json` and `live/portfolio_daily.csv` | Ready; awaiting test window |
| Missed-run recovery | Backfills every unprocessed test date | Complete |
| Duplicate-run safety | Date/symbol upserts and persisted state | Complete |
| Historical walk-forward test | `reports/daily_portfolio/` | Complete |
| Local scheduling | `scripts/install_daily_task.ps1` | Script ready; not installed |
| Authenticated exchange orders | Deliberately absent | Not required unless instructor confirms |

### Current research verdict

For BTC/ETH over the walk-forward validation period (1 Jan 2024–31 Jul 2026), the adaptive-trend baseline returned **10.09%** with **-23.78%** maximum drawdown. The Bollinger/RSI-confirmed version returned **-7.23%** with **-13.84%** maximum drawdown. BTC buy-and-hold returned **42.35%**, while equal-weight BTC/ETH returned **10.77%**. The added filters reduced drawdown but materially harmed return, so they remain experimental. Neither version yet satisfies the goal of beating the market. Do not tune on the October 2026 evaluation window.

### Inputs still required from the team/instructor

- [ ] Confirm BTC/ETH are allowed and add any mandatory class assets after they are announced.
- [ ] Confirm whether paper execution is accepted or Binance Spot Testnet order evidence is mandatory.
- [ ] Confirm starting capital, official benchmark, risk-free rate, and transaction-cost convention.
- [ ] Enter all four or five team-member names and assign one owner to each mandatory role.
- [ ] Initialize/connect the shared GitHub repository. This workspace is not currently a Git repository.
- [ ] Run and approve a revised strategy using development data only before freezing parameters.

### Daily operating procedure

1. Run after 00:00 UTC (08:00 Singapore time); 08:15 Singapore provides a close buffer.
2. Execute `scripts/run_daily.ps1`, or install the supplied Windows scheduled task once.
3. Check `live/run_manifest.json`; require the expected latest closed candle and `orders_enabled: false`.
4. Review `live/daily_signals.csv`, `live/paper_orders.csv`, and `live/portfolio_kpis.json`.
5. Commit the updated `live/portfolio_closing_prices.csv` and assignment ledgers to the shared repository.
6. If a run fails, rerun it. The pipeline backfills missed dates and is idempotent for dates already processed.

---

## 1. Executive Summary & Objective

The objective of this mandate is to construct, backtest, and automate an algorithmic trading model capable of beating the market under genuine out-of-sample conditions. 

The strategy must automatically update its model parameters and generate daily forecasts/signals across a diversified universe. Performance will be benchmarked over an active 23-day trading window (October 1 – October 23, 2026), evaluated across absolute profitability (P&L) and risk-adjusted metrics.

---

## 2. Investment Universe & Eligibility Constraints

1. **Mandatory Core Assets:** Must incorporate the base assets announced in class.
2. **Supplemental Instruments:** Open to digital currencies, ETFs, commodities, or liquid equities.
3. **Maturity / Liquidity Filter:** Every included asset must have continuous trading history dating back **before August 1, 2025** (at least one full year of trading history prior to August 1, 2026).
4. **Data Integrity:** Must record daily closing prices for every asset in the portfolio to compile the required closing price CSV deliverable.

---

## 3. Candidate Strategies (Selection Matrix)

Pick a single coherent framework or a multi-model ensemble:

| Strategy Style | Core Mechanics | Strengths | Operational Risks |
| :--- | :--- | :--- | :--- |
| **Momentum / Trend-Following** | Short-to-medium lookback windows on ETFs/crypto using moving average cross-overs or breakouts. | High returns during sustained macro trends. | Susceptible to whipsaws during range-bound markets. |
| **Statistical Arbitrage / Pairs Trading** | Mean-reverting spreads between cointegrated pairs (e.g., related equities, crypto vs. index). | Market-neutral; lower correlation to broad market shocks. | Spread breakdown or structural divergence risk. |
| **Multi-Factor Signals** | Blends fundamental/macro data, liquidity metrics, and volatility filters. | Consistent risk-adjusted performance across market regimes. | Factor crowding, data collection complexity. |
| **Sentiment & Macro-Driven** | NLP on macro/geopolitical news, economic data releases, or sentiment indices. | Anticipates volatility before pure price charts react. | High noise-to-signal ratio; execution latency. |

---

## 4. Key Performance Indicators (KPIs)

Your final review will evaluate the following primary and risk-adjusted metrics across the test window:

* **P&L / Total Return & Annualized Return:** Overall bottom-line capital growth.
* **Sharpe Ratio:** Excess return per unit of total risk (volatility).
* **Maximum Drawdown (MDD):** Peak-to-trough worst-case portfolio drop.
* **Annualized Volatility:** Standard deviation of daily strategy returns.
* **Win Rate:** Ratio of profitable round-trips to total closed positions.
* **Profit per Trade:** Average net dollar gain per executed order.
* **Trade Frequency & Holding Period:** Total trade count versus average duration held (detects overtrading and fee drag).
* **Drawdown Frequency & Duration:** Frequency and recovery speed from adverse performance drops.

---

## 5. Team Roles & Contribution Matrix (4–5 Members)

Every member must claim clear, individual ownership in the final documentation:

```
┌──────────────────────────────────────────────────────────────┐
│                      Portfolio Lead                          │
│        (Architecture, Risk Budgeting, Coordination)          │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
┌───────────────▼──────────────┐ ┌─────────────▼───────────────┐
│   Quant / Feature Engineer   │ │      Data & Pipeline Eng    │
│ (Alpha Signals, Indicators)  │ │ (APIs, Cleaning, Auto-Run)  │
└───────────────┬──────────────┘ └─────────────┬───────────────┘
                │                              │
┌───────────────▼──────────────┐ ┌─────────────▼───────────────┐
│   Backtest & Execution Eng   │ │ Reporting & Analytics Lead  │
│ (Engine, Slippage, Sizing)   │ │ (KPI Tracking, Deck, CSV)   │
└──────────────────────────────┘ └─────────────────────────────┘
```

* **Role 1: Portfolio Lead / Strategy Architect**
  * Defines strategy thesis, position sizing rules, leverage caps, and overall risk management parameters.
* **Role 2: Data Pipeline & Ingestion Engineer**
  * Automates historical data ingestion, daily price updates, and clean CSV output generation for submission.
* **Role 3: Quantitative Signal Specialist**
  * Engineers alpha indicators (trend filters, mean-reversion bands, or sentiment scores) and model re-estimation routines.
* **Role 4: Backtesting & Execution Specialist**
  * Builds the simulation engine, incorporating realistic transaction costs, execution delay, and automated daily rebalancing.
* **Role 5: Risk & Reporting Lead (If 5 members)**
  * Tracks real-time KPIs, monitors drawdown patterns, conducts benchmark attribution, and leads final slide construction.

---

## 6. End-to-End Implementation Milestones

### Phase 1: Universe Selection & Environment Setup (Days 1–4)
* [ ] Finalize team roles and document specific ownership areas.
* [x] Verify configured crypto compliance: each instrument traded before August 1, 2025.
* [ ] Confirm the configured universe includes the mandatory class assets.
* [ ] Set up the shared GitHub repository with choice of stack (Python recommended for ecosystem breadth; Julia/Rust/R allowed).
* [x] Construct automated daily Binance public-data ingestion pipeline.

### Phase 2: Signal Design & Automated Parameter Updates (Days 5–9)
* [x] Formulate adaptive daily SMA trend/quality alpha logic.
* [x] Implement automated trailing-window parameter updating each day.
* [x] Implement daily forecasts, volatility scaling, concentration caps, and target holdings.

### Phase 3: In-Sample Backtesting & Friction Accounting (Days 10–13)
* [x] Run development and validation walk-forward tests over past regimes.
* [x] Add 10 bps turnover friction.
* [x] Implement volatility sizing and concentration caps.
* [ ] Stress-test data outages, price shocks, and alternative fee assumptions.

### Phase 4: Live Out-of-Sample Test Window (1 Oct 2026 – 23 Oct 2026)
* [x] **Daily Run Routine:** Code and recovery behavior are ready; install the scheduler after team approval.
* [x] **Data Logging:** Required CSV and ledgers are generated automatically; test-window rows begin October 1.
* [x] **Performance Monitoring:** KPI, benchmark, turnover, order, and closed-trade outputs are implemented.

### Phase 5: Synthesis, Presentation & Final Submission (Week 11)
* [ ] Finalize the portfolio summary CSV containing all asset prices and timestamps.
* [ ] Compile the KPI performance dashboard (Sharpe, MDD, Annualized Return, Holding Period, etc.).
* [ ] Draft the presentation deck:
  1. Strategic rationale & economic thesis
  2. Mathematical and algorithmic implementation
  3. Risk controls & model updating pipeline
  4. Out-of-sample performance breakdown vs. expectations
  5. Individual member contribution statements
* [ ] Final code freeze and repository packaging.

---

## 7. Submission Checklist

- [ ] **Portfolio Daily Closing Prices File (`portfolio_closing_prices.csv`)** covering all holdings (generator ready; awaiting test dates).
- [x] **Reproducible Source Code** with an actionable `README.md` and dependency list (`requirements.txt`).
- [ ] **Final Presentation Slides (`.pdf` / `.pptx`)** explicitly detailing individual member contributions.
- [ ] **No Late Submissions:** Ensure deployment and presentation materials are uploaded prior to the Week 11 cutoff.
