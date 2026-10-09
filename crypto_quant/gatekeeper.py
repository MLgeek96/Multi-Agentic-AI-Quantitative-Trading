"""Hierarchical HMM throttle + breakout + trend-confirmation ensemble."""

from __future__ import annotations

import numpy as np
import pandas as pd


def confirm_breakout_entries(
    breakout_signals: pd.DataFrame,
    ma_signals: pd.DataFrame,
    momentum_signals: pd.DataFrame,
    *,
    confirmation: str,
) -> pd.DataFrame:
    """Confirm new breakout entries without forcing premature exits.

    Long and short rules are symmetric. Once an entry is accepted, it remains
    active until the underlying Bollinger state exits or flips direction.
    """

    allowed = {"none", "ma", "momentum", "either", "both"}
    if confirmation not in allowed:
        raise ValueError(f"confirmation must be one of {sorted(allowed)}")
    breakout = breakout_signals.pivot(index="date", columns="symbol", values="signal")
    ma = ma_signals.pivot(index="date", columns="symbol", values="signal").reindex_like(breakout)
    momentum = momentum_signals.pivot(
        index="date", columns="symbol", values="signal"
    ).reindex_like(breakout)
    output = pd.DataFrame(0.0, index=breakout.index, columns=breakout.columns)

    for symbol in breakout.columns:
        accepted = 0.0
        for date in breakout.index:
            raw = float(breakout.at[date, symbol])
            ma_direction = float(ma.at[date, symbol])
            momentum_direction = float(momentum.at[date, symbol])
            if raw == 0:
                accepted = 0.0
            elif accepted == raw:
                pass
            else:
                ma_agrees = np.sign(ma_direction) == np.sign(raw)
                momentum_agrees = np.sign(momentum_direction) == np.sign(raw)
                confirmed = {
                    "none": True,
                    "ma": ma_agrees,
                    "momentum": momentum_agrees,
                    "either": ma_agrees or momentum_agrees,
                    "both": ma_agrees and momentum_agrees,
                }[confirmation]
                accepted = raw if confirmed else 0.0
            output.at[date, symbol] = accepted

    return _long_signals(output, strategy=f"breakout_confirmed_{confirmation}")


def apply_hmm_throttle(
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
    *,
    low_volatility_scale: float,
) -> pd.DataFrame:
    """Use HMM state only to size positions, never to choose direction."""

    if not 0 <= low_volatility_scale <= 1:
        raise ValueError("low_volatility_scale must be in [0, 1]")
    frame = signals.merge(
        regimes[["regime", "high_volatility_probability"]]
        .rename_axis("date")
        .reset_index(),
        on="date",
        how="inner",
    )
    frame["hmm_throttle"] = np.where(
        frame["regime"].eq("high_volatility"), 1.0, low_volatility_scale
    )
    frame["unthrottled_signal"] = frame["signal"].astype(float)
    frame["signal"] = frame["unthrottled_signal"] * frame["hmm_throttle"]
    frame["strategy"] = "hmm_gatekeeper"
    return frame


def _long_signals(matrix: pd.DataFrame, *, strategy: str) -> pd.DataFrame:
    frame = matrix.rename_axis("date").reset_index().melt(
        id_vars="date", var_name="symbol", value_name="signal"
    )
    frame.insert(2, "strategy", strategy)
    return frame
