# Crypto and pairs PM integration

The local fund coordinator connects your existing Crypto PM to the daily pairs
engine from [MLgeek96/financial-econometrics-project](https://github.com/MLgeek96/financial-econometrics-project).
Both PMs expose diagnostic tools for advisory AI memos. Quantitative targets pass
local crypto risk and then independent fund risk before linked intentions are
recorded. Momentum remains an unconnected cash reserve.

## Open the fund dashboard

```powershell
.\.venv\Scripts\python.exe -m fund_agents.dashboard
```

Open <http://127.0.0.1:8765>. The dashboard uses Python's standard library and
local HTML/CSS/JavaScript; it needs no frontend install, CDN, or network data.
It reads existing JSON cycles under `runs/fund_agents/`. Generate a demo below
if that directory is empty, then click **Refresh reports**. Use `--port 8766`
for another port or `--reports path/to/reports` for another report directory.

- **Fund overview:** marked account NAV, approved target gross, snapshot
  drawdown, capital mandates, and connected PM status.
- **Risk monitor:** fund and symbol exposure limits, collateral and fee reserves,
  signed target legs, scaling outcomes, and confirmed holdings.
- **Portfolio managers:** crypto specialist diagnostics, pair Z-score, signed
  Kalman beta, formation health, OU forecasts, and PM diagnostic memos.
- **System flow:** select each component to inspect responsibilities, source
  modules, and the selected cycle's actual evidence.
- **Decision ledger:** exact approval hashes, both account snapshots, linked
  intention receipts, and original JSON export.

The newest generated cycle is selected initially. The selector lets you inspect
earlier demo or historical cycles; every view uses that same selection. Refresh
discovers newly exported cycles while retaining an existing selection. Demo
inputs and historical valuation dates are explicitly labeled. Missing risk
metrics remain unavailable, including during input holds. A forward OU chart
shows model projections, not historical performance. The dashboard is read-only
and localhost-only; it does not run strategies, modify risk limits, change
accounts, or record orders. Consolidated performance remains unimplemented.

## Run the demonstration

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-fund.txt
.\.venv\Scripts\python.exe -m fund_agents
```

The demo generates deterministic invented crypto and equity inputs. It exercises
both PMs, a signed pair entry, diagnostic tool calls, risk, and SQLite persistence.
It records zero fills and leaves the input account unchanged.

## Run a historical research cycle

```powershell
.\.venv\Scripts\python.exe -m fund_agents `
  --config config/fund_agents.research.json `
  --as-of 2026-08-28 `
  --pairs-prices .codex_work/friend-pairs/data/cache/asset_prices.csv `
  --crypto-data-dir live/market_data
```

The teammate checkout is an ignored inspection copy created during integration.
For another checkout, pass the location of the teammate's `asset_prices.csv` or
your own close matrix. Its first column contains exchange session dates and its
other columns contain native-currency prices, such as `Date,V,MA`. The runner does
not fetch or forward-fill equity prices. Every expected pair session must have
finite positive prices for both legs. Extra rows after `--as-of` are excluded.

The default research mandate is V/MA on the US session calendar, selected from
the teammate's saved qualified formation results. The adapter independently
checks that pair on sessions through 31 December 2024, before the research
decision date. The equity cache inspected during integration ends in August
2026; it cannot supply an October run. Historical replays do not establish live
October trading history.

Research requires a completed UTC crypto candle. Equity prices are checked
against the configured exchange calendar: on weekends and exchange holidays,
the last actual equity session provides valuation and no new pair order. The
closing-price export preserves that session date alongside the fund date.

## Confirmed account positions

Without `--portfolio`, the cycle explicitly starts from the configured cash
mandates and flat positions. Recorded intentions never become holdings. To
review an existing account, supply a confirmed snapshot:

```json
{
  "as_of": "2026-08-28",
  "crypto_cash_usd": 1500000,
  "pairs_cash_usd": 1500000,
  "momentum_cash_usd": 1500000,
  "central_cash_usd": 500000,
  "peak_nav_usd": 5000000,
  "usdt_to_usd": 1.0,
  "valuation_note": "USDT valued at USD 1 by paper-account convention",
  "holdings": [],
  "fx_to_usd": {"USD": 1.0}
}
```

A pair holding uses `pm: "pairs"`, `group: "V~MA"`, `symbol`, signed `units`,
`entry_price_usd`, and `opened_on`. Supply both legs with the same opening session.
A crypto holding uses `pm: "crypto"` and `group: "spot:BTCUSDT"` or
`"spot:ETHUSDT"`; its units must be nonnegative. Cash and signed marked holdings
must reconcile to actual sleeve equity. Include short proceeds and liabilities
consistently in the supplied account; the runner does not synthesize financing.

Add pairs in the configuration using `asset1`, `asset2`, `calendar`, and
`currency`. A pair currently shares one declared session calendar across both
legs. Different-session or 24/7 crypto pairs need their own calendar adaptation.
For non-USD pairs, the snapshot must contain that currency's USD conversion and
`fx_as_of` equal to the fund date. GBp prices require a USD conversion per penny.
USDT's configurable valuation convention is exposed in the crypto diagnostics.

## Capital and risk

The default proposed USD 5 million fund assigns USD 1.5 million each to crypto,
pairs, and the pending momentum sleeve, plus USD 0.5 million of central cash.
The pairs engine proposes gross exposure of 80% of its mandate, divided equally
among configured pairs before fund risk. Cash can remain unused.

Fund risk limits gross exposure to 80% of marked fund NAV and each symbol's
gross exposure across sleeves to 20%. It also limits each connected sleeve to
the smaller of its original mandate and current marked equity, with a 2%
collateral buffer and a 15 bps fee reserve. Short proceeds do not increase the
collateral mandate. Gross exposure is counted before any cross-sleeve netting.
If a limit binds, one common factor scales actionable target groups, preserving
each pair's signed dollar hedge relationship. Closed-market holdings retain
their units. A breached 25% fund drawdown breaker remains latched in SQLite and
requests exits only on eligible sessions.

The Crypto PM retains its original signal, sizing, liquidity, stop, and drawdown
checks. Its persistent risk state is stored inside the fund account rather than
reusing the standalone crypto database. A missing PM input holds the entire
fund cycle. Risk decisions and their input snapshots must match the persisted
approval exactly before Execution records a group.

## AI PM diagnostics and memos

Each representative has three callable read-only tools: `inspect_signals`,
`inspect_model_health`, and `inspect_positions`. Every call records its output
and content digest. Default runs call all three and export computed evidence
without claiming that an LLM ran.

Optional imported AI selections and replies use `--pm-responses path.json`:

```json
{
  "pairs": {
    "tool_names": ["inspect_signals", "inspect_model_health", "inspect_positions"],
    "reply": null
  }
}
```

This exports the exact `input_facts`, `input_sha256`, and `system_prompt` for the
chosen diagnostics. An imported model reply can replace `null` with an object
containing `model`, that `input_sha256`, and `output`. The output schema is the
same as `crypto_agents.research`: `summary`, `observations`, `risk_flags`,
`suggested_research`, and `metric_claims`. Structured metric claims must exactly
match computed facts. Free-text claims require human review. Keep the same tool
selection when importing a reply so its facts digest matches.

Memos run after risk and have no trading authority. Automatic model-provider
calls and autonomous LLM tool selection remain separate work. The dashboard
displays the saved diagnostic evidence and imported memo validation status.

## Outputs and reproducibility

Each cycle writes a JSON report, a closing-price CSV, and a crypto quality audit
under `runs/fund_agents/`. JSON includes both proposals, independent risk reviews,
PM tools and memos, confirmed account snapshots, and grouped execution receipts.
SQLite files under `runtime/` preserve append-only decisions, intentions, cycles,
and latched fund and crypto risk states. Repeating identical intentions does not
duplicate them. Account dates cannot move backwards; use a new `account_key`
and state path for an independent historical replay.

These directories are ignored by Git. The standalone daily paper ledger and
October schedule are separate. A future pair fill adapter must add actual quote
checks, board lots, borrow availability, two-leg fill handling, costs, and
accounting before reporting trading P&L or consolidated fund performance.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The imported numerical engines and their exact source revision are recorded in
[`vendor/pairs_trading/SOURCE.json`](vendor/pairs_trading/SOURCE.json).
Integration corrections live in `pairs.py`: signed beta sizing, spread forecast
standardization, invalid OU guards, divergence entry protection, confirmed
position state, exchange sessions, and a 45-session default time stop.
