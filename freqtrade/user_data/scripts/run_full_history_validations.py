from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
USER_DATA = ROOT / "freqtrade" / "user_data"
RESULTS_ROOT = ROOT / "freqtrade" / "validation_runs" / "2026_native_history_scenarios"
MODEL_ROOT = USER_DATA / "models"

FUTURES_PAIRS = {
    "BTC/USDT:USDT": 2150,
    "ETH/USDT:USDT": 2150,
    "SOL/USDT:USDT": 1893,
    "XRP/USDT:USDT": 2145,
    "BNB/USDT:USDT": 2110,
    "DOGE/USDT:USDT": 1958,
}
SPOT_PAIRS = {
    "BTC/USDT": 2150,
    "ETH/USDT": 2150,
    "SOL/USDT": 1927,
    "XRP/USDT": 2150,
    "BNB/USDT": 2150,
    "DOGE/USDT": 2150,
}


@dataclass(frozen=True)
class Run:
    slug: str
    long_short_strategy: str
    long_only_strategy: str
    base_config: str
    full_history_config: str | None = None
    freqai_model: str | None = None
    uses_hmm: bool = False


RUNS = (
    Run(
        "bollinger",
        "BollingerBreakout40D",
        "BollingerBreakout40DLongOnly",
        "config_baseline.json",
    ),
    Run(
        "rnn",
        "SequenceBreakoutStrategy",
        "SequenceBreakoutLongOnlyStrategy",
        "config_freqai_rnn.json",
        "config_full_history_{market}rnn.json",
        "PyTorchSequenceRegressor",
    ),
    Run(
        "gru",
        "SequenceBreakoutStrategy",
        "SequenceBreakoutLongOnlyStrategy",
        "config_freqai_gru.json",
        "config_full_history_{market}gru.json",
        "PyTorchSequenceRegressor",
    ),
    Run(
        "lstm",
        "SequenceBreakoutStrategy",
        "SequenceBreakoutLongOnlyStrategy",
        "config_freqai_lstm.json",
        "config_full_history_{market}lstm.json",
        "PyTorchSequenceRegressor",
    ),
    Run(
        "transformer",
        "SequenceBreakoutStrategy",
        "SequenceBreakoutLongOnlyStrategy",
        "config_freqai_transformer.json",
        "config_full_history_{market}transformer.json",
        "PyTorchSequenceRegressor",
    ),
    Run(
        "hmm_trend",
        "HMMTrendOnlyStrategy",
        "HMMTrendOnlyLongOnlyStrategy",
        "config_hmm_regime.json",
        uses_hmm=True,
    ),
    Run(
        "hmm_switching",
        "HMMRegimeSwitchingStrategy",
        "HMMRegimeSwitchingLongOnlyStrategy",
        "config_hmm_regime.json",
        uses_hmm=True,
    ),
    Run(
        "hmm_defensive",
        "HMMRegimeDefensiveStrategy",
        "HMMRegimeDefensiveLongOnlyStrategy",
        "config_hmm_regime.json",
        uses_hmm=True,
    ),
    Run(
        "hmm_trend_defensive",
        "HMMTrendOnlyDefensiveStrategy",
        "HMMTrendOnlyDefensiveLongOnlyStrategy",
        "config_hmm_regime.json",
        uses_hmm=True,
    ),
    Run(
        "hmm_lstm",
        "HMMRegimeLSTMStrategy",
        "HMMRegimeLSTMLongOnlyStrategy",
        "config_hmm_lstm.json",
        "config_full_history_{market}hmm_lstm.json",
        "PyTorchSequenceRegressor",
        uses_hmm=True,
    ),
)


def market_prefix(mode: str) -> str:
    return "spot_" if mode == "spot_long_only" else ""


def hmm_config(mode: str) -> str:
    return (
        "config_hmm_full_history_spot.json"
        if mode == "spot_long_only"
        else "config_hmm_full_history_futures.json"
    )


def identifier_from_config(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["freqai"]["identifier"])


def prediction_path(identifier: str, pair: str) -> Path:
    base = pair.split("/")[0].lower()
    return (
        MODEL_ROOT
        / identifier
        / "backtesting_predictions"
        / f"cb_{base}_1767225600_prediction.feather"
    )


def base_command(run: Run, mode: str, scenario_config: str, strategy: str) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "freqtrade",
        "backtesting",
        "--userdir",
        str(USER_DATA),
        "--config",
        str(USER_DATA / run.base_config),
    ]
    if run.full_history_config:
        full_config = run.full_history_config.format(market=market_prefix(mode))
        command.extend(["--config", str(USER_DATA / full_config)])
    if run.uses_hmm:
        command.extend(["--config", str(USER_DATA / hmm_config(mode))])
    command.extend(
        [
            "--config",
            str(USER_DATA / scenario_config),
            "--strategy",
            strategy,
            "--timerange",
            "20260101-20260918",
            "--fee",
            "0.001",
            "--cache",
            "none",
            "--no-color",
        ]
    )
    if run.freqai_model:
        command.extend(["--freqaimodel", run.freqai_model])
    return command


def ensure_native_pair_predictions(
    run: Run, mode: str, scenario_config: str, strategy: str
) -> None:
    if not run.freqai_model or not run.full_history_config:
        return
    full_config = run.full_history_config.format(market=market_prefix(mode))
    identifier = identifier_from_config(USER_DATA / full_config)
    pairs = SPOT_PAIRS if mode == "spot_long_only" else FUTURES_PAIRS
    for pair, train_days in pairs.items():
        if prediction_path(identifier, pair).is_file():
            print(f"CACHE {mode}/{run.slug}/{pair}", flush=True)
            continue
        command = base_command(run, mode, scenario_config, strategy)
        command.extend(
            [
                "--config",
                str(USER_DATA / f"config_native_train_{train_days}d.json"),
                "--pairs",
                pair,
                "--export",
                "none",
                "--notes",
                f"native-pair-fit-{mode}-{run.slug}-{pair}",
            ]
        )
        print(
            f"FIT {mode}/{run.slug}/{pair}: {train_days} usable history days",
            flush=True,
        )
        subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run inception-to-2025 training with an untouched 2026 holdout."
    )
    parser.add_argument(
        "--mode",
        choices=("futures_long_short", "futures_long_only", "spot_long_only", "all"),
        default="all",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    modes = (
        ("futures_long_short", "config_validation_sixcoin.json"),
        ("futures_long_only", "config_validation_sixcoin.json"),
        ("spot_long_only", "config_validation_sixcoin_spot.json"),
    )
    for mode, scenario_config in modes:
        if args.mode not in ("all", mode):
            continue
        for run in RUNS:
            destination = RESULTS_ROOT / mode / run.slug
            destination.mkdir(parents=True, exist_ok=True)
            if list(destination.glob("*.zip")) and not args.force:
                print(f"SKIP {mode}/{run.slug}: result archive already exists", flush=True)
                continue

            strategy = (
                run.long_short_strategy
                if mode == "futures_long_short"
                else run.long_only_strategy
            )
            ensure_native_pair_predictions(run, mode, scenario_config, strategy)
            command = base_command(run, mode, scenario_config, strategy)
            if run.freqai_model:
                command.extend(
                    [
                        "--config",
                        str(USER_DATA / "config_native_prediction_replay.json"),
                    ]
                )
            command.extend(
                [
                    "--export",
                    "signals",
                    "--backtest-directory",
                    str(destination),
                    "--notes",
                    f"{mode}-{run.slug}-full-history-through-2025-holdout-2026ytd",
                ]
            )
            if run.freqai_model:
                # The prediction cache was trained pair-by-pair on native histories.
                # A one-year loader window is sufficient for deterministic replay.
                pass
            print(f"RUN {mode}/{run.slug}", flush=True)
            subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
