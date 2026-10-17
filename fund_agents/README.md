# Pairs fund integration

`fund_agents` runs the daily Pairs PM from
[MLgeek96/financial-econometrics-project](https://github.com/MLgeek96/financial-econometrics-project)
through independent fund risk, linked intention records, a PM evidence memo,
and Committee Chair review. Pairs is the sole connected PM. Crypto is removed
from the active fund. Momentum remains an unconnected cash reserve.

The four imported numerical modules were already pinned at `5d42b04`. The
remote checked on 17 October 2026 still points to that commit. This update
completes their pairs-only integration and aligns formation thresholds and the
OU half-life holding policy with the teammate's settings.

## Run the demonstration

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-fund.txt
.\.venv\Scripts\python.exe -m fund_agents
.\.venv\Scripts\python.exe -m fund_agents.dashboard
```

The deterministic demo uses invented V/MA prices, valued on 10 March 2025. It
exercises a linked pair entry, independent risk, tools, and persistence. It
records zero fills and leaves the confirmed account unchanged.

## Open the fund dashboard

Open <http://127.0.0.1:8765>. The Stripe-inspired Meridian workspace has six
views: Overview, Portfolio managers, Risk & protection, Committee review,
System flow, and Decision ledger. Pairs diagnostics include the strategy source,
pinned revision, effective policy, signed hedge beta, Z-score, frozen formation
qualification, holding limit, and OU forecasts. Forecasts are projections.

Use the evidence filter, saved cycle selector, workspace search (Ctrl/Cmd K),
and six-step investor tour. **Investor brief** downloads a text summary bound
to the selected cycle. **Decision ledger** exports the original JSON and copies
a local cycle link. **Refresh** discovers newly exported reports.

Only `pairs-fund-v2` cycles with exactly the Pairs PM are indexed. Old two-PM
cycles remain on disk and are excluded from the active portal. A stale link
falls back to a current indexed cycle. Missing measurements remain unavailable.
The portal reads saved JSON; it cannot run models, edit policy, or place orders.
It uses only local assets and Python's standard HTTP server. Use `--port 8766`
or `--reports path/to/reports` if needed. Hosting and investor authentication
remain future work. See [design notes](web/DESIGN.md).

## Run a historical research cycle

```powershell
.\.venv\Scripts\python.exe -m fund_agents `
  --config config/fund_agents.research.json `
  --as-of 2026-08-28 `
  --pairs-prices .codex_work/friend-pairs/data/cache/asset_prices.csv
```

The ignored teammate checkout is an inspection copy. Pass the location of its
`asset_prices.csv` or your own matrix. The first column is an exchange session
date; other columns are native-currency closes, such as `Date,V,MA`. The runner
does not download or forward-fill prices. It rejects duplicate columns and
missing, nonfinite, or nonpositive required session prices. Rows after the
valuation date cannot influence the signal. Research requires all relevant
exchange sessions to have closed. On holidays and weekends, the last actual
session provides valuation and no new pair intention.

The default mandate is V/MA on XNYS in USD. Formation history through
31 December 2024 gates new research entries before inference. The inspected
cache ends in August 2026; it cannot supply a current October cycle. The
28 August replay qualifies and stays flat. Upstream backtest results are not
imported as integrated fund returns.

## Strategy and local adaptations

The imported Kalman filter, OU model, forecast engine, and pair selector are
attributed in [SOURCE.json](vendor/pairs_trading/SOURCE.json). Each proposal
verifies local engine hashes and saves its source revision and policy. A
changed engine without an updated source record holds the cycle.

Default entry/exit/stop absolute Z thresholds are `1.25 / 0.10 / 3.50`, Kalman
Q/R are `1e-5 / 1e-3`, and formation thresholds are 10% cointegration p-value,
60% minimum return correlation, and 2–90 session half-life. The upstream
selector reports ADF and Johansen diagnostics; qualification uses its
Engle–Granger, correlation, and half-life gates. There is no fallback to an
unqualified pair. Invalid OU estimates or extreme divergence block new entries.

For confirmed holdings, the adapter recomputes OU half-life using only prices
through `opened_on`, freezes that entry estimate, and sets the time limit to
`min(45, max(1, ceil(2.5 × entry_half_life)))` sessions. Invalid entry estimates
use the hard 45-session cap. The multiplier and hard cap are configurable.
Both legs use the same confirmed opening session. Later estimates cannot
extend the trade. Entry/exit, divergence stops, and time stops remain visible
in the saved diagnostics.

The adapter corrects upstream residual forecast standardization and retains
the sign of hedge beta, including same-sign legs for negative beta. It converts
native prices to USD and sends both legs as one group to independent risk.
The upstream standalone backtest, financing, Yahoo downloader, and separate
ensemble are not run by the fund coordinator.

## Confirmed account positions

Without `--portfolio`, each run starts with explicitly flat positions and the
configured cash mandates. Recorded intentions never become holdings. Supply a
confirmed account with `--portfolio snapshot.json` when reviewing positions:

```json
{
  "as_of": "2026-08-28",
  "pairs_cash_usd": 1500000,
  "momentum_cash_usd": 1500000,
  "central_cash_usd": 2000000,
  "peak_nav_usd": 5000000,
  "holdings": [],
  "fx_to_usd": {"USD": 1.0}
}
```

Each nonzero holding requires `pm: "pairs"`, `group: "V~MA"`, `symbol`, signed
`units`, `entry_price_usd`, and an exchange-session `opened_on`. Supply both
legs and reconcile cash, short proceeds and liabilities consistently to actual
sleeve equity. Single-leg accounts are held for review. Legacy Crypto holdings
and config fields are rejected.

Additional equity pairs require explicit `asset1`, `asset2`, `calendar`, and
`currency` configuration and validated history. Both legs currently share one
declared session calendar. Non-USD pairs require an explicit USD conversion
and `fx_as_of` equal to the fund date; GBp needs a conversion per penny. The
synthetic demo requires disjoint symbols; research can share symbols across
pair groups, with gross concentration aggregated before netting.

## Capital and risk

| Mandate | USD | Status |
| --- | ---: | --- |
| Pairs | 1,500,000 | Connected |
| Momentum reserve | 1,500,000 | Cash pending integration |
| Central cash | 2,000,000 | Includes former Crypto allocation |
| Total | 5,000,000 | Illustrative paper mandate |

Pairs proposes gross exposure of 80% of its mandate, divided equally across
configured pairs. Fund risk caps gross at 80% of marked fund NAV and each
symbol at 20% across pair groups. It applies a 2% collateral buffer and 15 bps
turnover fee reserve to the smaller of Pairs equity and mandate. These are
reserves, not charged costs. Short proceeds do not enlarge the mandate.

A common scale preserves both signed dollar legs. Closed-market holdings
retain confirmed units. At 12% drawdown the standard fund gross ceiling halves;
the conservative envelope also applies a 0.75 multiplier. The 25% breaker
remains latched across restarts and requests exits on eligible sessions.
Missing inputs hold the cycle. Recorded approvals and snapshot hashes must
match exactly before an intention can be saved.

The Phantom Book compares proposed and approved gross and records exposure
removed. It does not measure rejected-trade returns or money saved. Its
NAV-minus-gross buffer is not spendable cash.

## AI PM diagnostics and memos

Pairs exposes `inspect_signals`, `inspect_model_health`, and `inspect_positions`.
The Chair exposes `inspect_cross_sleeve_exposure` (gross across pair groups),
`inspect_phantom_book`, and `inspect_pm_memos`. Every result has a digest.
Default calls and computed summaries do not mean an LLM ran.

Optional `--pm-responses path.json` accepts only `pairs` and `chair` envelopes:

```json
{"pairs": {"tool_names": ["inspect_signals", "inspect_model_health", "inspect_positions"], "reply": null}}
```

This exports exact `input_facts`, `input_sha256`, and `system_prompt`. Replace
`null` with `{model, input_sha256, output}` to import a reply with the same
diagnostic selection. `output` requires `summary`, `observations`, `risk_flags`,
`suggested_research`, and `metric_claims`. Structured metrics must match the
saved facts. Free text requires human review. Replies run after risk and have
no trading authority. Automatic provider calls remain pending.

## Outputs and reproducibility

New accounts use `runtime/pairs_fund.*.sqlite` and exports under
`runs/fund_agents/pairs_only/{demo,research}/`. Old stores are not migrated,
liquidated, or rewritten. Their records remain historical. The new schema
contains only Pairs proposals, fund risk, PM and Chair evidence, snapshots,
and receipts. Each run exports JSON and a closing-price CSV; no crypto inputs
or crypto audits are required. Dates cannot run backwards within an account;
use a separate account and store for another replay.

The fund package has no runtime import of `crypto_agents` or `crypto_quant`,
and its requirements do not include the legacy HMM dependency. Historical
research code elsewhere in the repository is retained separately.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/test_investor_portal.cjs
```

See [verification](../reports/fund_agents/pairs_only_verification_20261017.md)
and the [updated investor script](../presentations/roadshow_20261017/Investor_System_Walkthrough_and_QA.docx).
Executable quotes, board lots, borrow, linked-leg fills, financing, costs, and
reconciled accounting are required before reporting consolidated fund returns.
