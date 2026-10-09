# Agent implementation and data-quality evidence

Verified 9 October 2026, Singapore time. This is an implementation report, not a
new trading-performance result. See `ARCHITECTURE.md` for interfaces and commands.

## Delivered

Local Meta, Regime, Signal, Position, Risk and Execution modules, frozen contracts,
validated offline-only config, SQLite state and append-only events, idempotent
approved-intent recording, persistent drawdown breaker, stop/profit requests,
cash/name/gross/fee/liquidity constraints, and an optional imported LLM Research
reply with schema, facts-digest and metric-claim validation.

Existing adaptive SMA selection and inverse-volatility target math are reused.
A regression test compares the agent's target weights with the existing daily
decision function. New record-only receipts never mutate portfolios or claim fills.
Historical reports remain as originally prepared, with their original limitations.

The public daily runner now refuses stale, missing, malformed, duplicate or
unordered data before processing its paper ledger. Future archive preparation
runs export per-dataset audit and checksum lineage; historical manifests were not
retroactively relabeled or regenerated.

## Verification

`python -m unittest discover -s tests -q`: **51 tests passed**.

Coverage includes baseline parity, risk reduction and veto, prior-only liquidity,
breaker persistence across SQLite restarts, stop requests without fills, exact
persisted approval verification, account isolation, repeated-intent handling,
append-only events, transaction rollback, unknown-input holds, prior-only HMM
training, synthetic/research separation, imported LLM output having no trading
effect, false metric/digest rejection, snapshot causality and source fingerprint
changes, corruption/freshness checks, and unchanged ledgers after data failure.
The original research tests also pass. Optional Freqtrade/Torch suites are outside
this count and were not rerun for this local agent change.

| Local CLI check | Result | Fills |
|---|---|---|
| Synthetic normal | Two approved intents recorded | 0 |
| Synthetic reduced-name limit | Two resized intents recorded | 0 |
| Synthetic flagged data | DATA_QUALITY_VETO | 0 |
| Synthetic impaired equity | BREAKER_LATCHED, buys rejected | 0 |
| Spot daily replay, 16 Sep 2026 | Structural PASS; NO_ACTION | 0 |
| Prior-only HMM replay, 16 Sep 2026 | Structural PASS; NO_ACTION; trained through 15 Sep | 0 |

## Actual data audit findings

| Dataset | Rows | Audit date/window | Result |
|---|---:|---|---|
| BTC Spot daily cache | 2,500 | Through 16 Sep 2026 | PASS for that historical window |
| ETH Spot daily cache | 2,500 | Through 16 Sep 2026 | PASS for that historical window |
| Both daily caches | 2,500 each | Expected last close label 8 Oct 2026 | FAIL: stale; actual last label 16 Sep |
| BTC Spot hourly | 58,817 | 1 Jan 2020–17 Sep 2026 | FAIL: 31 missing bars; 8 invalid close boundaries |
| ETH Spot hourly | 58,817 | 1 Jan 2020–17 Sep 2026 | FAIL: 31 missing bars; 8 invalid close boundaries |

One BTC anomaly was checked against the SHA-256-verified raw
`BTCUSDT-1h-2020-12.zip`: the 21 Dec 2020 14:00 UTC bar reports a close timestamp
of 13:47:20.521 UTC. This is present in the source archive, not introduced by the
new gate. Other shortened bars include exchange outage periods. The source rows
remain untouched and no inferred replacement timestamps or prices are created.

Normalized input byte identities:

- BTC hourly: `00da9f4d70ccdf71f6afa23e68758462c0123cbf6e46abfbe51f433d99601ad3`
- ETH hourly: `85d6175e2ef96948db543973cae6ee1e34329bb51b32cc3c66b5d3459b70758c`

Detailed audits are generated under ignored `runs/quality/`; the agent CLI also
exports its own window audit beside every JSON cycle report. Structural PASS does
not establish independent source authenticity, historical universe membership,
listing eligibility, execution liquidity or investment merit. Only BTC/ETH Spot
inputs were audited for this integration; this is not a six-coin/futures audit.

## Remaining scope

The daily cache must be refreshed before current October paper evaluation. This
implementation did not install a schedule, backfill assignment ledgers, call an
LLM provider or enable exchange execution. Imported LLM replies are advisory and
their free-text claims require human review. No agent-strategy profitability claim
is made. Risk and HMM example settings need a separately validated experiment.

The private repository packages source, tests, configs, this evidence summary and
existing reports. Runtime databases, raw datasets, processed caches, model files,
backtest ZIPs, credentials and raw LLM transcripts are excluded by `.gitignore`.
`scripts/check_publication.py` validates staged content before publishing.
