from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from pandas import DataFrame


FEATURE_NAMES = [
    "return_24h",
    "volatility_24h",
    "volatility_168h",
    "volatility_ratio",
    "trend_strength_120h",
    "drawdown_168h",
    "volume_z_168h",
]


def build_regime_features(dataframe: DataFrame) -> DataFrame:
    """Build the causal observations used by both HMM fitting and filtering."""
    close = dataframe["close"].astype(float)
    log_close = np.log(close.replace(0, np.nan))
    return_1h = log_close.diff()
    volatility_24h = return_1h.rolling(24).std(ddof=0)
    volatility_168h = return_1h.rolling(168).std(ddof=0)
    moving_average_120h = close.rolling(120).mean()
    rolling_high_168h = close.rolling(168).max()
    log_volume = np.log1p(dataframe["volume"].astype(float))
    volume_mean = log_volume.rolling(168).mean()
    volume_std = log_volume.rolling(168).std(ddof=0).replace(0, np.nan)

    features = DataFrame(index=dataframe.index)
    features["return_24h"] = log_close.diff(24)
    features["volatility_24h"] = volatility_24h
    features["volatility_168h"] = volatility_168h
    features["volatility_ratio"] = volatility_24h / volatility_168h.replace(0, np.nan)
    features["trend_strength_120h"] = (close / moving_average_120h - 1).abs()
    features["drawdown_168h"] = close / rolling_high_168h - 1
    features["volume_z_168h"] = (log_volume - volume_mean) / volume_std
    return features[FEATURE_NAMES].replace([np.inf, -np.inf], np.nan)


def load_hmm_parameters(model_path: Path) -> dict:
    return json.loads(model_path.read_text(encoding="utf-8"))


def _logsumexp(values: np.ndarray, axis: int | None = None) -> np.ndarray:
    maximum = np.max(values, axis=axis, keepdims=True)
    result = maximum + np.log(np.exp(values - maximum).sum(axis=axis, keepdims=True))
    if axis is not None:
        result = np.squeeze(result, axis=axis)
    return result


def causal_filter(features: DataFrame, parameters: dict) -> DataFrame:
    """Run the HMM forward filter without using any future observations."""
    result = DataFrame(index=features.index)
    result["regime_state"] = -1
    result["regime"] = "unknown"
    result["regime_confidence"] = 0.0
    for regime in ("trend", "sideways", "crisis"):
        result[f"regime_{regime}_prob"] = 0.0

    valid = features.notna().all(axis=1)
    if not valid.any():
        return result

    mean = np.asarray(parameters["scaler_mean"], dtype=float)
    scale = np.asarray(parameters["scaler_scale"], dtype=float)
    observations = (features.loc[valid, FEATURE_NAMES].to_numpy(dtype=float) - mean) / scale

    start_probability = np.clip(np.asarray(parameters["startprob"], dtype=float), 1e-12, 1.0)
    transition = np.clip(np.asarray(parameters["transmat"], dtype=float), 1e-12, 1.0)
    state_means = np.asarray(parameters["means"], dtype=float)
    state_variances = np.clip(np.asarray(parameters["variances"], dtype=float), 1e-8, None)
    state_labels = {int(state): label for state, label in parameters["state_labels"].items()}

    log_start = np.log(start_probability)
    log_transition = np.log(transition)
    log_alpha: np.ndarray | None = None
    probabilities = np.zeros((len(observations), len(start_probability)), dtype=float)

    for row_number, observation in enumerate(observations):
        log_emission = -0.5 * np.sum(
            np.log(2 * np.pi * state_variances)
            + (observation - state_means) ** 2 / state_variances,
            axis=1,
        )
        if log_alpha is None:
            log_alpha = log_start + log_emission
        else:
            log_prediction = _logsumexp(log_alpha[:, None] + log_transition, axis=0)
            log_alpha = log_prediction + log_emission
        log_alpha = log_alpha - _logsumexp(log_alpha)
        probabilities[row_number] = np.exp(log_alpha)

    states = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    valid_index = features.index[valid]
    result.loc[valid_index, "regime_state"] = states
    result.loc[valid_index, "regime"] = [state_labels[state] for state in states]
    result.loc[valid_index, "regime_confidence"] = confidence
    for regime in ("trend", "sideways", "crisis"):
        state = next(state for state, label in state_labels.items() if label == regime)
        result.loc[valid_index, f"regime_{regime}_prob"] = probabilities[:, state]
    return result


def apply_defensive_router(
    filtered: DataFrame,
    *,
    confidence_threshold: float = 0.55,
    crisis_probability_threshold: float = 0.45,
    confirmation_candles: int = 3,
) -> DataFrame:
    """Add an asymmetric, causal transition policy to filtered HMM output.

    Crisis de-risking is immediate.  Trend/sideways activation requires the
    same candidate state for ``confirmation_candles`` consecutive rows.  A
    low-confidence or not-yet-confirmed observation is explicitly routed to
    ``uncertain`` so a strategy can reduce risk instead of forcing a sleeve.
    """
    if not 0.0 < confidence_threshold <= 1.0:
        raise ValueError("confidence_threshold must be in (0, 1]")
    if not 0.0 < crisis_probability_threshold <= 1.0:
        raise ValueError("crisis_probability_threshold must be in (0, 1]")
    if confirmation_candles < 1:
        raise ValueError("confirmation_candles must be positive")

    required = {
        "regime",
        "regime_confidence",
        "regime_crisis_prob",
    }
    missing = required.difference(filtered.columns)
    if missing:
        raise ValueError(f"filtered regimes are missing columns: {sorted(missing)}")

    result = filtered.copy()
    result["raw_regime"] = result["regime"].astype(str)
    result["regime_transition_pending"] = False
    result["regime_candidate"] = ""
    result["regime_confirmation_count"] = 0

    active_regime: str | None = None
    candidate_regime: str | None = None
    candidate_count = 0
    routed: list[str] = []
    pending: list[bool] = []
    candidates: list[str] = []
    counts: list[int] = []

    for row in result.itertuples():
        raw_regime = str(row.raw_regime)
        confidence = float(row.regime_confidence)
        crisis_probability = float(row.regime_crisis_prob)

        if raw_regime == "unknown":
            routed_regime = "unknown"
            candidate_regime = None
            candidate_count = 0
            is_pending = False
        elif crisis_probability >= crisis_probability_threshold:
            # Missing a crisis is costlier than a false alarm, so this branch
            # deliberately bypasses the normal confirmation delay.
            routed_regime = "crisis"
            active_regime = "crisis"
            candidate_regime = None
            candidate_count = 0
            is_pending = False
        elif confidence < confidence_threshold or raw_regime not in {"trend", "sideways"}:
            routed_regime = "uncertain"
            candidate_regime = None
            candidate_count = 0
            is_pending = False
        elif raw_regime == active_regime:
            routed_regime = raw_regime
            candidate_regime = None
            candidate_count = 0
            is_pending = False
        else:
            if candidate_regime == raw_regime:
                candidate_count += 1
            else:
                candidate_regime = raw_regime
                candidate_count = 1
            if candidate_count >= confirmation_candles:
                active_regime = raw_regime
                routed_regime = raw_regime
                candidate_regime = None
                candidate_count = 0
                is_pending = False
            else:
                routed_regime = "uncertain"
                is_pending = True

        routed.append(routed_regime)
        pending.append(is_pending)
        candidates.append(candidate_regime or "")
        counts.append(candidate_count)

    result["regime"] = routed
    result["regime_transition_pending"] = pending
    result["regime_candidate"] = candidates
    result["regime_confirmation_count"] = counts
    return result
