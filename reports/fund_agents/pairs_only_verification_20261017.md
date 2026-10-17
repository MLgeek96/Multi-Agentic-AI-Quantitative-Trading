# Pairs fund integration verification

Verified 17 October 2026. The active `fund_agents` system connects only the
teammate's daily Pairs PM. The Crypto PM adapter, runtime calls, capital fields,
cash/USDT fields, diagnostics, PM memo, risk state, and portal components have
been removed from the active workflow. Historical standalone crypto research
and earlier financial records are retained separately.

## Source inspected

An authenticated fetch of
[MLgeek96/financial-econometrics-project](https://github.com/MLgeek96/financial-econometrics-project)
and remote reference inspection found `main` at
`5d42b0463f5d690926b3d29f7647882189b45214`. There was no newer remote commit
than the four numerical modules already vendored locally. The current change
integrates their policy more fully into the Pairs-only fund rather than
claiming another upstream import.

The local source record includes the upstream revision, individual file
hashes, local import adaptation, and verification date. Every proposal checks
the numerical files against their recorded local hashes. Saved diagnostics
include that provenance, configured pair mandate, and effective policy.

## Implemented changes

- Pairs is the sole PM in the coordinator, risk gate, holdings, proposals,
  reports, AI reply envelopes, exports, and investor portal. The active fund
  imports neither `crypto_agents` nor `crypto_quant` and no longer depends on
  `hmmlearn` through its requirements file.
- Formation thresholds are configurable and match the teammate's defaults.
  Qualification uses frozen history, with no fallback to an unqualified pair.
  The default research mandate remains V/MA on XNYS in USD.
- The holding limit uses `ceil(multiplier × opening-session OU half-life)`,
  bounded below by one and above by the configured hard session cap. Defaults
  are 2.5 and 45 sessions. It recomputes the entry estimate from history ending
  at the confirmed opening session; later observations cannot extend it. An
  invalid entry estimate uses the hard cap.
- Existing corrections preserve signed beta, correct residual forecast
  standardization, block invalid OU and extreme-divergence entries, retain
  closed-market holdings, and keep both legs linked through risk scaling.
- New account/state paths and `pairs-fund-v2` prevent accidental continuation
  of the old two-PM portfolio. Legacy snapshots/config fields are rejected.
  Old cycles are excluded from the active report index and report endpoint.
- The former USD 1.5M Crypto mandate is central cash. The illustrative account
  reconciles to USD 5M: USD 1.5M Pairs, USD 1.5M Momentum reserve, USD 2M cash.
- The Stripe-inspired portal shows the current Pairs source and policy,
  signed targets, independent risk, Phantom Book, PM and Chair evidence,
  architecture, and linked intention ledger. Investor brief exports include
  source and revision. Missing Phantom Book figures remain unavailable.
- README, architecture, run guide, and the complete investor speaking script
  reflect the Pairs-only system. Older PPTX decks are identified as historical.

## Measured verification

Commands run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
node --test tests/test_investor_portal.cjs
.\.venv\Scripts\python.exe -m fund_agents
.\.venv\Scripts\python.exe -m fund_agents --config config/fund_agents.research.json --as-of 2026-08-28 --pairs-prices .codex_work/friend-pairs/data/cache/asset_prices.csv
```

All **86 Python tests** and **10 portal regression tests** passed. Checks
include future-data exclusion, missing sessions, invalid OU, frozen entry time
stops, unqualified formation, source drift, negative beta, common scaling,
symbol gross before netting, dated FX, persistent breakers, exact approvals,
idempotency, atomic rollback, AI claims without trading authority, legacy
report exclusion, retired PM rejection, and absence of Crypto runtime imports.
`git diff --check` passed.

| Result | Synthetic demo | Historical research |
| --- | ---: | ---: |
| Valuation date | 2025-03-10 | 2026-08-28 |
| Pairs status | READY | READY |
| Fund status | INTENTS_RECORDED | NO_ACTION |
| Supplied marked NAV | USD 5,000,000 | USD 5,000,000 |
| Approved gross | USD 1,200,000 | USD 0 |
| Signal | ENTRY SHORT SPREAD | STAY FLAT |
| Spread Z-score | 2.673794 | 0.014613 |
| Signed Kalman beta | 0.365589 | 0.819832 |
| Formation gate | Disabled for invented data | Qualified on frozen history |
| Linked intention groups | 1 | 0 |
| Fills | 0 | 0 |
| PM and Chair model replies | NOT_REQUESTED | NOT_REQUESTED |

Latest verified cycles are
`4ce33457-6c31-4de6-b213-a32962e2d7b7` (demo) and
`c371cce4-e9c0-4ec5-9abe-305671af33a7` (research), stored under the ignored
`runs/fund_agents/pairs_only/` directories. Both contain no Crypto fields,
have unchanged before/after snapshots, and preserve zero-fill receipts.
The demo's repeat receipt is idempotent and already recorded rather than a fill.

The historical V/MA formation result has return correlation `0.886147`,
Engle–Granger p-value `0.005280`, and formation half-life `53.039572` sessions.
These are formation diagnostics rather than investment returns. The supplied
price matrix SHA-256 is
`1d8cff4c14188cfef425999855e182835224a00b5b0ab1e8b1473c8307dd9120`.

Browser inspection confirmed that an old two-PM cycle URL falls back to an
indexed Pairs cycle and that the active overview, Pairs diagnostics, source,
architecture, and linked targets show the new mandate. The 11-page investor
DOCX was rendered through the packaged renderer with native Word PDF conversion
and every page was visually inspected.

## Limits of this evidence

The inspected equity cache ends in August 2026. It does not support a current
October signal or establish forward trading history. The upstream standalone
backtest and ensemble outputs are not imported as fund returns.

The fund records intentions only: no exchange orders, fills, charged fees,
realized P&L, or reconciled consolidated return series. Momentum, automatic
model calls, executable quote/lot/borrow checks, linked-leg fill handling,
financing, accounting, investor authentication, and hosting remain future work.
Risk controls constrain targets and do not guarantee realized losses or returns.
Local hashes and append-only triggers are content and process controls rather
than independent external attestation. Free-text AI claims require human review.
