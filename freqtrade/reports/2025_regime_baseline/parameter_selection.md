# Parameter selection protocol for the three-regime strategy

This protocol deliberately keeps 2025 out of parameter selection. The completed 2025 runs in
this folder are now a **consumed benchmark**: they can diagnose the design, but must not be used
to choose a winning parameter set. There is no complete 2026 data in the repository yet.

## 1. Rolling development folds

Use expanding training windows and one-year validation windows:

| Fold | Fit HMM and choose scaling on | Validate trading rules on |
|---|---|---|
| 1 | 2020-01-01 through 2021-12-31 | 2022 |
| 2 | 2020-01-01 through 2022-12-31 | 2023 |
| 3 | 2020-01-01 through 2023-12-31 | 2024 |

Refit the scaler and HMM inside every fold. Do not reuse the frozen 2020–2024 HMM when scoring
2022–2024, because that would let the regime model see its validation years. Use causal forward
probabilities, never full-sample Viterbi decoding or smoothed probabilities.

For an LSTM candidate, keep the inner schedule used by this baseline: trailing 365 days, predict
the next 90 days, and then retrain. Every prediction must come from a model whose training window
ends before that prediction.

## 2. Small staged grids

Avoid one large Cartesian product. Tune one component at a time and keep the previous component's
robust region, not merely its single best point.

### A. Router and crisis control: 4 candidates

- HMM confidence threshold: `{0.50, 0.60}`
- Crisis probability threshold: `{0.35, 0.50}`
- Keep three states, diagonal covariance, the same seven causal features, and five initializations.

### B. Trend sleeve: 4 candidates

- Bollinger window: `{20 days, 40 days}`
- Band width: `{1.5, 2.0}` standard deviations
- Keep EMA 24/120, MACD 12/26/9, and RSI 55/45 fixed for this first grid.

### C. Sideways sleeve: 6 candidates

- First compare **disabled** against enabled.
- If enabled, test window `{3 days, 7 days}`, width `{1.5, 2.0}`, but evaluate one window change
  and one width change around the baseline rather than all combinations.
- Keep the RSI 35/65 gate fixed initially.

The disable control is essential: the 2025 sideways-only result was negative, so this sleeve must
earn its place independently.

### D. LSTM gate: 4 candidates, then seeds

- No neural gate (control)
- Sign only: threshold `0`
- Absolute predicted 24-hour return: `{0.2%, 0.5%}`
- Keep the current 48-hour input, 32 hidden units, one layer, and 24-hour target fixed.

Only if one LSTM rule beats the no-neural control on median validation performance should it be
repeated with seeds `{11, 42, 77}`. Architecture searches across RNN, GRU, LSTM, and Transformer
come later; the prior 2025 experiment already showed that extra architecture complexity is not
automatically useful.

## 3. Selection score and rejection rules

For every candidate record each fold separately. Prefer a simple robust score:

```text
score = median(fold daily Sharpe) - 0.5 * median(fold max drawdown)
```

Apply these hard rejection rules before ranking:

1. Positive net return in at least two of three folds.
2. Positive aggregate return at a 0.20% fee per side.
3. No single asset contributes more than 80% of total profit.
4. At least 30 total validation trades, unless the rule is explicitly a low-frequency sleeve.
5. The combined model must beat both its trend-only and sideways-only controls on median fold
   score. Otherwise keep the stronger control.
6. An LSTM version must beat the deterministic version after costs across at least two seeds.

Do not use 2025 to break ties. If two configurations are close, choose the simpler one.

## 4. Cost and execution stress

Run each survivor with fees of 0.05%, 0.10%, and 0.20% per side. Then add explicit adverse
slippage of 0.02% and 0.05% per fill. Historical perpetual funding and mark-price data are absent
from the local archive, so obtain and align them before making a live-trading claim.

Also test a one-candle execution delay. This is particularly important for the crisis switch:
the current backtest can react at the next simulated fill, while a live model needs time to close
positions after a state change.

## 5. Final evaluation

After the development protocol is frozen, run it once on a genuinely unseen period. The current
files stop at 2025-12-31, so the honest next holdout is complete 2026 data after it exists. Until
then, use dry-run trading for execution validation and do not label further 2025 iterations as
out-of-sample tests.
