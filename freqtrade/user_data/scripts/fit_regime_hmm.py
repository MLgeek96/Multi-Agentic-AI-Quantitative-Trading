from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIRECTORY = ROOT / "user_data" / "strategies"
if str(STRATEGY_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(STRATEGY_DIRECTORY))

from regime_hmm import FEATURE_NAMES, build_regime_features


DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT")


def state_zscores(state_statistics: pd.DataFrame) -> pd.DataFrame:
    standard_deviation = state_statistics.std(ddof=0).replace(0, 1.0)
    return (state_statistics - state_statistics.mean()) / standard_deviation


def assign_state_labels(state_statistics: pd.DataFrame) -> dict[int, str]:
    zscore = state_zscores(state_statistics)
    crisis_score = (
        1.5 * zscore["volatility_168h"]
        + zscore["volatility_24h"]
        - zscore["return_24h"]
        - 1.5 * zscore["drawdown_168h"]
    )
    crisis_state = int(crisis_score.idxmax())

    remaining = [state for state in state_statistics.index if state != crisis_state]
    trend_score = (
        zscore.loc[remaining, "trend_strength_120h"]
        + 0.5 * zscore.loc[remaining, "return_24h"].abs()
        + 0.25 * zscore.loc[remaining, "volatility_ratio"]
    )
    trend_state = int(trend_score.idxmax())
    sideways_state = next(
        int(state) for state in state_statistics.index if state not in (crisis_state, trend_state)
    )
    return {
        crisis_state: "crisis",
        trend_state: "trend",
        sideways_state: "sideways",
    }


def fit_pair(source_path: Path, output_directory: Path, start: str, end: str) -> dict:
    raw = pd.read_csv(source_path, compression="gzip")
    raw["date"] = pd.to_datetime(raw["open_time"], utc=True)
    raw = raw.sort_values("date").set_index("date")
    features = build_regime_features(raw)
    development = features.loc[start:end].dropna()
    raw_development = raw.loc[development.index]

    scaler = StandardScaler()
    scaled = scaler.fit_transform(development)

    candidates = []
    for seed in (11, 22, 33, 42, 77):
        model = GaussianHMM(
            n_components=3,
            covariance_type="diag",
            n_iter=200,
            tol=1e-4,
            random_state=seed,
            min_covar=1e-4,
        )
        model.fit(scaled)
        candidates.append((float(model.score(scaled)), seed, model))
    fit_score, seed, model = max(candidates, key=lambda candidate: candidate[0])

    states = model.predict(scaled)
    state_frame = development.copy()
    state_frame["state"] = states
    state_statistics = state_frame.groupby("state")[FEATURE_NAMES].mean()
    state_statistics["observations"] = state_frame.groupby("state").size()
    state_statistics["mean_close"] = raw_development.groupby(states)["close"].mean()
    labels = assign_state_labels(state_statistics)

    symbol = str(raw["symbol"].iloc[0])
    variances = np.asarray(model._covars_, dtype=float)
    payload = {
        "model": "three-state diagonal Gaussian HMM",
        "symbol": symbol,
        "development_period": {"start": start, "end": end},
        "feature_names": FEATURE_NAMES,
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
                **{
                    column: float(value)
                    for column, value in row.items()
                },
            }
            for state, row in state_statistics.iterrows()
        },
        "fit": {
            "selected_seed": seed,
            "log_likelihood": fit_score,
            "iterations": int(model.monitor_.iter),
            "converged": bool(model.monitor_.converged),
            "candidate_scores": {
                str(candidate_seed): candidate_score
                for candidate_score, candidate_seed, _ in candidates
            },
        },
    }

    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / f"{symbol}_3state_hmm.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"path": str(output_path), **payload}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit frozen three-state HMM regime models.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31 23:00:00")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    arguments = parser.parse_args()

    summaries = []
    for symbol in (value.upper() for value in arguments.symbols):
        source_path = arguments.source / f"{symbol}_1h.csv.gz"
        if not source_path.is_file():
            raise FileNotFoundError(f"Missing prepared futures data: {source_path}")
        summaries.append(
            fit_pair(source_path, arguments.output, arguments.start, arguments.end)
        )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
