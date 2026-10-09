# Research report index

Start with the consolidated wrap-up:

- `FINAL_RESEARCH_REPORT.md` — final narrative, results, decisions, limitations, and wrap-up checklist.
- `FINAL_PARAMETER_MANIFEST.json` — machine-readable effective parameters and authoritative source index.

The dated or method-specific directories below are retained as the audit trail. Their results are not independent experiments when they reuse the same 2025 or 2026 observations.

| Directory | Scope |
| --- | --- |
| `pattern_momentum/` | BTC/ETH structural patterns with momentum confirmation |
| `daily_portfolio/` | BTC/ETH adaptive daily Spot portfolio |
| `hmm_regime/` | Two-state BTC/ETH daily HMM baseline |
| `model_selection/` | Development-selected classical and statistical controls |
| `macro_regime/` | Macro/volume HMM ablations |
| `gatekeeper/` | HMM throttle and entry-confirmation hierarchy |
| `cross_market_validation/` | Frozen Spot and futures transfer test for 2025 |
| `forward_2026_validation/` | Parameters selected through 2025 and tested on 2026 |

The latest six-coin Freqtrade reports are under `freqtrade/reports/2026_sixcoin_validation/`, `freqtrade/reports/2026_execution_scenarios/`, and `freqtrade/reports/2026_native_history_scenarios/`. The USDT 1 million capacity, market-impact, Monte Carlo, and line-by-line quality audit is under `freqtrade/reports/2026_million_usdt_quality/`.

The BTC/ETH/altcoin-season HMM, equal-bucket portfolio, and experimental 50/25/25 cycle tilt are under `freqtrade/reports/2026_market_cycle_hmm/`.
