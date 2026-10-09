"""Causal three-state HMM for BTC, ETH, and altcoin relative-performance seasons."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler


SEASONS = ("bitcoin_season", "ethereum_season", "altcoin_season")
FEATURE_NAMES = (
    "bitcoin_relative_momentum_30d",
    "ethereum_relative_momentum_30d",
    "altcoin_relative_momentum_30d",
    "bitcoin_strength_share_30d",
    "ethereum_strength_share_30d",
    "altcoin_strength_share_30d",
    "btc_alt_correlation_30d",
    "eth_btc_correlation_30d",
    "alt_breadth_vs_btc_30d",
)
ALTCOINS = ("SOL", "XRP", "BNB", "DOGE")


def bucket_returns(daily_close: pd.DataFrame) -> pd.DataFrame:
    returns = daily_close.astype(float).pct_change(fill_method=None)
    missing = set(("BTC", "ETH", *ALTCOINS)).difference(returns.columns)
    if missing:
        raise ValueError(f"Missing market-cycle symbols: {sorted(missing)}")
    return pd.DataFrame(
        {
            "bitcoin": returns["BTC"],
            "ethereum": returns["ETH"],
            "altcoins": returns[list(ALTCOINS)].mean(axis=1),
        },
        index=daily_close.index,
    )


def build_cycle_features(
    daily_close: pd.DataFrame,
    *,
    momentum_window: int = 30,
    correlation_window: int = 30,
) -> pd.DataFrame:
    """Build features known at each daily close; execution must occur later."""

    if momentum_window < 2 or correlation_window < 2:
        raise ValueError("Feature windows must be at least two days")
    returns = daily_close.astype(float).pct_change(fill_method=None)
    buckets = bucket_returns(daily_close)
    bucket_indices = (1.0 + buckets.fillna(0.0)).cumprod()
    momentum = np.log(bucket_indices).diff(momentum_window)
    relative = momentum.sub(momentum.mean(axis=1), axis=0)
    relative_scale = relative.std(axis=1, ddof=0).replace(0.0, np.nan)
    normalized_relative = relative.div(relative_scale, axis=0)
    exponentiated = np.exp(normalized_relative)
    strength_share = exponentiated.div(exponentiated.sum(axis=1), axis=0)

    log_close = np.log(daily_close.astype(float))
    asset_momentum = log_close.diff(momentum_window)
    alt_breadth = pd.concat(
        [asset_momentum[symbol] > asset_momentum["BTC"] for symbol in ALTCOINS],
        axis=1,
    ).mean(axis=1)

    features = pd.DataFrame(index=daily_close.index)
    features["bitcoin_relative_momentum_30d"] = relative["bitcoin"]
    features["ethereum_relative_momentum_30d"] = relative["ethereum"]
    features["altcoin_relative_momentum_30d"] = relative["altcoins"]
    features["bitcoin_strength_share_30d"] = strength_share["bitcoin"]
    features["ethereum_strength_share_30d"] = strength_share["ethereum"]
    features["altcoin_strength_share_30d"] = strength_share["altcoins"]
    features["btc_alt_correlation_30d"] = buckets["bitcoin"].rolling(
        correlation_window
    ).corr(buckets["altcoins"])
    features["eth_btc_correlation_30d"] = buckets["ethereum"].rolling(
        correlation_window
    ).corr(buckets["bitcoin"])
    features["alt_breadth_vs_btc_30d"] = alt_breadth
    return features[list(FEATURE_NAMES)].replace([np.inf, -np.inf], np.nan)


def assign_state_seasons(state_statistics: pd.DataFrame) -> dict[int, str]:
    """Assign one unique season to each state using relative-momentum means."""

    if len(state_statistics) != 3:
        raise ValueError("Exactly three states are required for season assignment")
    score_columns = {
        "bitcoin_season": "bitcoin_relative_momentum_30d",
        "ethereum_season": "ethereum_relative_momentum_30d",
        "altcoin_season": "altcoin_relative_momentum_30d",
    }
    states = [int(value) for value in state_statistics.index]
    best_score = -np.inf
    best_assignment: dict[int, str] | None = None
    for labels in itertools.permutations(SEASONS):
        assignment = dict(zip(states, labels))
        score = sum(
            float(state_statistics.loc[state, score_columns[label]])
            for state, label in assignment.items()
        )
        if score > best_score:
            best_score = score
            best_assignment = assignment
    if best_assignment is None:
        raise RuntimeError("Unable to assign HMM season labels")
    return best_assignment


def fit_cycle_hmm(
    features: pd.DataFrame,
    *,
    training_start: str,
    training_end: str,
    seeds: list[int],
    minimum_state_occupancy: float = 0.10,
) -> dict:
    """Fit a frozen diagonal Gaussian HMM and map its states without OOS data."""

    development = features.loc[training_start:training_end].dropna()
    if len(development) < 365:
        raise ValueError("At least 365 complete training observations are required")
    scaler = StandardScaler()
    scaled = scaler.fit_transform(development)
    candidates = []
    relative_columns = {
        "bitcoin_season": "bitcoin_relative_momentum_30d",
        "ethereum_season": "ethereum_relative_momentum_30d",
        "altcoin_season": "altcoin_relative_momentum_30d",
    }
    for seed in seeds:
        model = GaussianHMM(
            n_components=3,
            covariance_type="diag",
            n_iter=300,
            tol=1e-4,
            random_state=int(seed),
            min_covar=1e-4,
        )
        model.fit(scaled)
        states = model.predict(scaled)
        counts = np.bincount(states, minlength=3)
        minimum_occupancy = float(counts.min() / counts.sum())
        candidate_frame = development.copy()
        candidate_frame["state"] = states
        candidate_statistics = candidate_frame.groupby("state")[list(FEATURE_NAMES)].mean()
        labels = assign_state_seasons(candidate_statistics)
        semantic_margins = []
        for state, label in labels.items():
            assigned_column = relative_columns[label]
            competing = [
                column
                for column in relative_columns.values()
                if column != assigned_column
            ]
            semantic_margins.append(
                float(
                    candidate_statistics.loc[state, assigned_column]
                    - candidate_statistics.loc[state, competing].max()
                )
            )
        minimum_semantic_margin = min(semantic_margins)
        candidates.append(
            {
                "score": float(model.score(scaled)),
                "seed": int(seed),
                "model": model,
                "states": states,
                "minimum_occupancy": minimum_occupancy,
                "minimum_semantic_margin": minimum_semantic_margin,
            }
        )
    eligible = [
        candidate
        for candidate in candidates
        if candidate["minimum_occupancy"] >= minimum_state_occupancy
        and candidate["minimum_semantic_margin"] > 0.0
    ]
    if not eligible:
        raise RuntimeError(
            "No HMM candidate produced three occupied, semantically distinct season states"
        )
    selected = max(eligible, key=lambda candidate: candidate["score"])
    model = selected["model"]
    states = selected["states"]
    state_frame = development.copy()
    state_frame["state"] = states
    statistics = state_frame.groupby("state")[list(FEATURE_NAMES)].mean()
    statistics["observations"] = state_frame.groupby("state").size()
    statistics["occupancy_pct"] = statistics["observations"] / len(state_frame) * 100
    labels = assign_state_seasons(statistics)
    variances = np.asarray(model._covars_, dtype=float)
    return {
        "model": "three-state diagonal Gaussian HMM",
        "training_period": {
            "start": str(development.index.min()),
            "end": str(development.index.max()),
            "observations": int(len(development)),
        },
        "feature_names": list(FEATURE_NAMES),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "startprob": model.startprob_.tolist(),
        "transmat": model.transmat_.tolist(),
        "means": model.means_.tolist(),
        "variances": variances.tolist(),
        "state_labels": {str(state): label for state, label in labels.items()},
        "state_statistics": {
            str(state): {
                "label": labels[int(state)],
                **{column: float(value) for column, value in row.items()},
            }
            for state, row in statistics.iterrows()
        },
        "fit": {
            "selected_seed": int(selected["seed"]),
            "log_likelihood": float(selected["score"]),
            "minimum_state_occupancy": float(selected["minimum_occupancy"]),
            "minimum_semantic_margin": float(selected["minimum_semantic_margin"]),
            "required_minimum_state_occupancy": float(minimum_state_occupancy),
            "converged": bool(model.monitor_.converged),
            "iterations": int(model.monitor_.iter),
            "candidates": {
                str(candidate["seed"]): {
                    "log_likelihood": float(candidate["score"]),
                    "minimum_state_occupancy": float(candidate["minimum_occupancy"]),
                    "minimum_semantic_margin": float(candidate["minimum_semantic_margin"]),
                }
                for candidate in candidates
            },
        },
    }


def _logsumexp(values: np.ndarray, axis: int | None = None) -> np.ndarray:
    maximum = np.max(values, axis=axis, keepdims=True)
    result = maximum + np.log(np.exp(values - maximum).sum(axis=axis, keepdims=True))
    if axis is not None:
        result = np.squeeze(result, axis=axis)
    return result


def causal_cycle_filter(features: pd.DataFrame, parameters: dict) -> pd.DataFrame:
    """Apply only the HMM forward recursion; no backward smoothing is used."""

    result = pd.DataFrame(index=features.index)
    result["cycle_state"] = -1
    result["cycle"] = "unknown"
    result["cycle_confidence"] = 0.0
    for season in SEASONS:
        result[f"prob_{season}"] = 0.0

    names = parameters["feature_names"]
    valid = features[names].notna().all(axis=1)
    if not valid.any():
        return result
    mean = np.asarray(parameters["scaler_mean"], dtype=float)
    scale = np.asarray(parameters["scaler_scale"], dtype=float)
    observations = (features.loc[valid, names].to_numpy(dtype=float) - mean) / scale
    start_probability = np.clip(np.asarray(parameters["startprob"], dtype=float), 1e-12, 1.0)
    transition = np.clip(np.asarray(parameters["transmat"], dtype=float), 1e-12, 1.0)
    state_means = np.asarray(parameters["means"], dtype=float)
    state_variances = np.clip(np.asarray(parameters["variances"], dtype=float), 1e-8, None)
    labels = {int(state): label for state, label in parameters["state_labels"].items()}
    log_alpha: np.ndarray | None = None
    probabilities = np.zeros((len(observations), len(start_probability)), dtype=float)
    for row_number, observation in enumerate(observations):
        log_emission = -0.5 * np.sum(
            np.log(2 * np.pi * state_variances)
            + (observation - state_means) ** 2 / state_variances,
            axis=1,
        )
        if log_alpha is None:
            log_alpha = np.log(start_probability) + log_emission
        else:
            log_prediction = _logsumexp(
                log_alpha[:, None] + np.log(transition), axis=0
            )
            log_alpha = log_prediction + log_emission
        log_alpha -= _logsumexp(log_alpha)
        probabilities[row_number] = np.exp(log_alpha)

    states = probabilities.argmax(axis=1)
    valid_index = features.index[valid]
    result.loc[valid_index, "cycle_state"] = states
    result.loc[valid_index, "cycle"] = [labels[int(state)] for state in states]
    result.loc[valid_index, "cycle_confidence"] = probabilities.max(axis=1)
    for season in SEASONS:
        state = next(state for state, label in labels.items() if label == season)
        result.loc[valid_index, f"prob_{season}"] = probabilities[:, state]
    return result


def build_bucket_weights(
    directions: pd.DataFrame,
    cycles: pd.Series | None = None,
    *,
    favored_bucket_weight: float = 0.50,
    other_bucket_weight: float = 0.25,
) -> pd.DataFrame:
    """Allocate bucket gross weights while retaining each asset signal direction."""

    required = set(("BTC", "ETH", *ALTCOINS))
    missing = required.difference(directions.columns)
    if missing:
        raise ValueError(f"Missing direction columns: {sorted(missing)}")
    weights = pd.DataFrame(0.0, index=directions.index, columns=directions.columns)
    season_to_bucket = {
        "bitcoin_season": "bitcoin",
        "ethereum_season": "ethereum",
        "altcoin_season": "altcoins",
    }
    for date in directions.index:
        shares = {"bitcoin": 1 / 3, "ethereum": 1 / 3, "altcoins": 1 / 3}
        if cycles is not None:
            favored = season_to_bucket.get(str(cycles.get(date, "unknown")))
            if favored is not None:
                shares = {
                    bucket: favored_bucket_weight
                    if bucket == favored
                    else other_bucket_weight
                    for bucket in shares
                }
        if directions.at[date, "BTC"] != 0:
            weights.at[date, "BTC"] = (
                np.sign(directions.at[date, "BTC"]) * shares["bitcoin"]
            )
        if directions.at[date, "ETH"] != 0:
            weights.at[date, "ETH"] = (
                np.sign(directions.at[date, "ETH"]) * shares["ethereum"]
            )
        active_alts = [symbol for symbol in ALTCOINS if directions.at[date, symbol] != 0]
        if active_alts:
            per_alt = shares["altcoins"] / len(active_alts)
            for symbol in active_alts:
                weights.at[date, symbol] = np.sign(directions.at[date, symbol]) * per_alt
    return weights
