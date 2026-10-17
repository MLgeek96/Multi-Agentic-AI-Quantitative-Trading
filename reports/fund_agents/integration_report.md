# Crypto and pairs PM integration verification

**Implemented:** 14 October 2026

**Scope:** local Crypto and Pairs PM coordination with advisory AI evidence and
record-only execution

The teammate's daily pairs engine is connected alongside the existing Crypto PM
through `fund_agents`. Both submit quantitative target groups to independent fund
risk and expose callable diagnostics for PM memos. The existing crypto strategy
and its local risk checks remain the Crypto PM's engine. The
[run guide](../../fund_agents/README.md) contains the commands and account schema.

## Source and ownership

The pairs numerical engines come from
[MLgeek96/financial-econometrics-project at revision 5d42b04](https://github.com/MLgeek96/financial-econometrics-project/tree/5d42b0463f5d690926b3d29f7647882189b45214/pairs_trading).
The imported files are `kalman_filter.py`, `ou_process.py`,
`forecasting_engine.py`, and `pair_selection.py`. Attribution and original and
local file hashes are recorded in
[SOURCE.json](../../fund_agents/vendor/pairs_trading/SOURCE.json).
Forecasting imports use the local namespace; numerical corrections and the PM
adapter are maintained separately in `fund_agents/pairs.py`.

| Component | Implementation |
| --- | --- |
| Crypto PM | Adapter over `crypto_agents.MetaAgent`, including its original final local risk veto |
| Pairs PM | Teammate Kalman hedge estimation, OU projections and spread rules; confirmed holdings supplied explicitly |
| PM representatives | Three callable diagnostic tools per PM and optional imported LLM selections and digest-checked replies |
| Fund coordinator | Shared USD valuation, separate PM proposals, final fund risk and one atomic audit cycle |
| Fund risk | Capital and fee reserves, gross exposure before netting, symbol limits, linked hedge scaling, persistent drawdown breaker |
| Execution | Grouped intentions with both pair legs, tied to exact persisted risk and account snapshot; zero fills |

The proposed USD 5 million allocation is used as an illustrative initial account:
USD 1.5 million for each connected PM, USD 1.5 million reserved for momentum, and
USD 0.5 million held centrally. The momentum engine is not connected.

## Integration corrections

The adapter retains the sign of Kalman beta when sizing the second leg. It
standardizes the OU residual forecast without subtracting the regression
intercept twice. Invalid OU projections become unavailable diagnostics and block
new entries. New positions are also blocked at extreme spread divergence.

Confirmed positions reach the forecast engine, enabling holding and exit rules.
A configurable 45-session time stop supplements those rules. Each expected
exchange session must contain both valid prices; prices are not filled across
missing sessions. Equity holidays and weekends retain confirmed quantities and
the last actual session date. Foreign-currency pairs require dated explicit FX.
Risk scales entire groups rather than resizing each pair leg independently.

The imported standalone updater has a fixed historical end date of 1 January
2025, and the source data loader can forward-fill and back-fill missing prices.
The integrated runner instead accepts an explicit completed `as_of` and uses a
local matrix without applying either fill operation. Existing fills in a supplied
cache cannot be detected or undone; that cache remains signal research data.

## Verified runs

The full repository suite passed **73 tests**, including **22 new fund integration
tests**. Checks cover both PMs, pair grouping and scaling, overlapping gross
exposure, negative beta, time stops, dated FX, stale data, equity weekends,
future-data exclusion, duplicate intention prevention, exact approval binding,
rollback, persistent breakers, and AI replies without trading authority.

The deterministic demo completed with both PMs ready and three linked intention
groups: BTC, ETH, and the two-leg V/MA group. Filled units remained zero and the
confirmed portfolio was unchanged.

The historical **28 August 2026** replay completed using the existing local
Binance daily cache and the teammate's `asset_prices.csv`. V/MA passed the
adapter's frozen formation screen through 31 December 2024, with an Engle-Granger
p-value of approximately 0.00528. On the replay date, its spread Z-score was
approximately 0.01461, so the Pairs PM stayed flat. The Crypto PM proposed ETH
exposure of approximately USD 496,998.64 after its local risk checks, and BTC
remained flat. Fund risk recorded one crypto intention group and zero fills.
The USD 5 million NAV was the supplied initial account, not earned performance.

Reusing the August equity cache for **16 September 2026** correctly produced
`INPUT_HOLD` for the Pairs PM because later expected sessions were missing.
Python compilation, source-file provenance and whitespace checks also passed.

## Remaining operational work

Default PM memos contain computed diagnostics. Imported AI replies and tool
selections are supported; automatic LLM provider calls and autonomous tool
selection are not connected. Execution records intentions, so it does not produce
paper fills, charged fees, a consolidated return history, or new October trading
records. Executable quote validation, board lots, borrow availability, two-leg
fill handling and fund accounting belong to a future fill adapter.

The research configuration initially uses V/MA with a US session calendar.
Additional same-session pairs can use the existing adapter with declared
calendars, currency valuations and formation checks. Mixed-session pairs need
additional calendar logic. The presentation files retain their earlier design
content; README and architecture documentation describe the new implementation.
