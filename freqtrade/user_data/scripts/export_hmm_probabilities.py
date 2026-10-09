from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parent
STRATEGY_DIRECTORY = ROOT / "user_data" / "strategies"
if str(STRATEGY_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(STRATEGY_DIRECTORY))

from regime_hmm import build_regime_features, causal_filter


DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT")
SEMANTIC_STATES = ("trend", "sideways", "crisis")


def model_state_map(parameters: dict) -> dict[str, int]:
    numeric_to_semantic = {
        int(state): label for state, label in parameters["state_labels"].items()
    }
    return {label: state for state, label in numeric_to_semantic.items()}


def transition_rows(symbol: str, parameters: dict) -> list[dict]:
    semantic_to_numeric = model_state_map(parameters)
    rows = []
    for from_state in SEMANTIC_STATES:
        from_number = semantic_to_numeric[from_state]
        for to_state in SEMANTIC_STATES:
            to_number = semantic_to_numeric[to_state]
            rows.append(
                {
                    "symbol": symbol,
                    "from_state": from_state,
                    "to_state": to_state,
                    "probability": float(parameters["transmat"][from_number][to_number]),
                }
            )
    return rows


def filter_symbol(
    symbol: str,
    source_directory: Path,
    model_directory: Path,
    warmup_start: str,
    start: str,
    end: str,
) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    source_path = source_directory / f"{symbol}_1h.csv.gz"
    model_path = model_directory / f"{symbol}_3state_hmm.json"
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    parameters = json.loads(model_path.read_text(encoding="utf-8"))
    raw = pd.read_csv(source_path, compression="gzip")
    raw["date"] = pd.to_datetime(raw["open_time"], utc=True)
    raw = raw.sort_values("date").set_index("date")
    warmup = raw.loc[warmup_start:end]
    filtered = causal_filter(build_regime_features(warmup), parameters)
    filtered = filtered.loc[start:end].copy()
    filtered.insert(0, "symbol", symbol)
    filtered["confidence_eligible"] = filtered["regime_confidence"] >= 0.55
    filtered["risk_on"] = filtered["regime_crisis_prob"] < 0.45

    semantic_to_numeric = model_state_map(parameters)
    valid = filtered["regime"] != "unknown"
    latest = filtered.loc[valid].iloc[-1]
    valid_filtered = filtered.loc[valid]
    summary_rows = []
    for state in SEMANTIC_STATES:
        numeric_state = semantic_to_numeric[state]
        probability_column = f"regime_{state}_prob"
        summary_rows.append(
            {
                "symbol": symbol,
                "state": state,
                "numeric_state": numeric_state,
                "selected_seed": int(parameters["fit"]["selected_seed"]),
                "start_probability": float(parameters["startprob"][numeric_state]),
                "self_transition_probability": float(
                    parameters["transmat"][numeric_state][numeric_state]
                ),
                "mean_2025_filtered_probability": float(
                    valid_filtered[probability_column].mean()
                ),
                "argmax_hours_2025": int((valid_filtered["regime"] == state).sum()),
                "argmax_pct_2025": float((valid_filtered["regime"] == state).mean()),
                "latest_time": valid_filtered.index[-1].isoformat(),
                "latest_filtered_probability": float(latest[probability_column]),
                "latest_argmax_regime": str(latest["regime"]),
                "latest_confidence": float(latest["regime_confidence"]),
                "confidence_eligible_pct_2025": float(
                    valid_filtered["confidence_eligible"].mean()
                ),
                "risk_off_pct_2025": float((~valid_filtered["risk_on"]).mean()),
            }
        )
    return filtered.reset_index(), transition_rows(symbol, parameters), summary_rows


def markdown_matrix(transitions: pd.DataFrame, symbol: str) -> str:
    matrix = (
        transitions.loc[transitions["symbol"] == symbol]
        .pivot(index="from_state", columns="to_state", values="probability")
        .reindex(index=SEMANTIC_STATES, columns=SEMANTIC_STATES)
    )
    lines = [
        f"### {symbol}",
        "",
        "| from \\ to | trend | sideways | crisis |",
        "| --- | ---: | ---: | ---: |",
    ]
    for state, row in matrix.iterrows():
        lines.append(
            f"| {state} | {row['trend']:.4f} | {row['sideways']:.4f} | {row['crisis']:.4f} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export fixed HMM transitions and causal hourly state probabilities."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=REPOSITORY_ROOT / "processed" / "usdt_futures",
    )
    parser.add_argument(
        "--models",
        type=Path,
        default=ROOT / "user_data" / "regime_models",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "2025_hmm_probabilities",
    )
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--warmup-start", default="2024-11-20 08:00:00+00:00")
    parser.add_argument("--start", default="2025-01-01 00:00:00+00:00")
    parser.add_argument("--end", default="2025-12-31 23:00:00+00:00")
    arguments = parser.parse_args()

    probability_frames = []
    transition_records = []
    summary_records = []
    for symbol in (value.upper() for value in arguments.symbols):
        probabilities, transitions, summaries = filter_symbol(
            symbol,
            arguments.source,
            arguments.models,
            arguments.warmup_start,
            arguments.start,
            arguments.end,
        )
        probability_frames.append(probabilities)
        transition_records.extend(transitions)
        summary_records.extend(summaries)

    probability_frame = pd.concat(probability_frames, ignore_index=True)
    transition_frame = pd.DataFrame(transition_records)
    summary_frame = pd.DataFrame(summary_records)

    probability_sums = probability_frame[
        ["regime_trend_prob", "regime_sideways_prob", "regime_crisis_prob"]
    ].sum(axis=1)
    valid = probability_frame["regime"] != "unknown"
    if not probability_sums.loc[valid].between(0.999999, 1.000001).all():
        raise ValueError("Filtered state probabilities do not sum to one")
    transition_sums = transition_frame.groupby(["symbol", "from_state"])[
        "probability"
    ].sum()
    if not transition_sums.between(0.999999, 1.000001).all():
        raise ValueError("Transition matrix rows do not sum to one")

    arguments.output.mkdir(parents=True, exist_ok=True)
    probability_frame.to_csv(
        arguments.output / "hourly_state_probabilities_2025.csv.gz",
        index=False,
        compression="gzip",
    )
    transition_frame.to_csv(arguments.output / "transition_probabilities.csv", index=False)
    summary_frame.to_csv(arguments.output / "state_probability_summary.csv", index=False)

    report_sections = [
        "# Six-asset HMM probability export",
        "",
        "Each transition matrix is fixed after fitting that asset on 2020-2024 data. Rows are the",
        "current hidden state and columns are the next hidden state. The hourly filtered probabilities",
        "are causal and time-varying; they use only observations available at that candle.",
        "",
    ]
    for symbol in (value.upper() for value in arguments.symbols):
        report_sections.extend([markdown_matrix(transition_frame, symbol), ""])
    (arguments.output / "transition_matrices.md").write_text(
        "\n".join(report_sections), encoding="utf-8"
    )
    print(
        f"Wrote {len(probability_frame):,} hourly rows, {len(transition_frame)} transitions, "
        f"and {len(summary_frame)} state summaries to {arguments.output}"
    )


if __name__ == "__main__":
    main()
