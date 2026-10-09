from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
USER_DATA = ROOT / "freqtrade" / "user_data"
RESULTS_ROOT = ROOT / "freqtrade" / "validation_runs" / "2026_scenarios"


@dataclass(frozen=True)
class Run:
    slug: str
    strategy: str
    base_config: str
    static_config: str | None = None
    freqai_model: str | None = None


RUNS = (
    Run("bollinger", "BollingerBreakout40DLongOnly", "config_baseline.json"),
    Run(
        "rnn",
        "SequenceBreakoutLongOnlyStrategy",
        "config_freqai_rnn.json",
        "config_static_holdout_{market}_rnn.json",
        "PyTorchSequenceRegressor",
    ),
    Run(
        "gru",
        "SequenceBreakoutLongOnlyStrategy",
        "config_freqai_gru.json",
        "config_static_holdout_{market}_gru.json",
        "PyTorchSequenceRegressor",
    ),
    Run(
        "lstm",
        "SequenceBreakoutLongOnlyStrategy",
        "config_freqai_lstm.json",
        "config_static_holdout_{market}_lstm.json",
        "PyTorchSequenceRegressor",
    ),
    Run(
        "transformer",
        "SequenceBreakoutLongOnlyStrategy",
        "config_freqai_transformer.json",
        "config_static_holdout_{market}_transformer.json",
        "PyTorchSequenceRegressor",
    ),
    Run("hmm_trend", "HMMTrendOnlyLongOnlyStrategy", "config_hmm_regime.json"),
    Run(
        "hmm_switching",
        "HMMRegimeSwitchingLongOnlyStrategy",
        "config_hmm_regime.json",
    ),
    Run(
        "hmm_defensive",
        "HMMRegimeDefensiveLongOnlyStrategy",
        "config_hmm_regime.json",
    ),
    Run(
        "hmm_trend_defensive",
        "HMMTrendOnlyDefensiveLongOnlyStrategy",
        "config_hmm_regime.json",
    ),
    Run(
        "hmm_lstm",
        "HMMRegimeLSTMLongOnlyStrategy",
        "config_hmm_lstm.json",
        "config_static_holdout_{market}_hmm_lstm.json",
        "PyTorchSequenceRegressor",
    ),
)


def config_name(template: str, mode: str) -> str:
    if "{market}" not in template:
        return template
    market = "spot" if mode == "spot_long_only" else ""
    return template.format(market=market).replace("holdout__", "holdout_")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run frozen-2025 long-only validations.")
    parser.add_argument(
        "--mode",
        choices=("futures_long_only", "spot_long_only", "all"),
        default="all",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    modes = (
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
            if run.static_config:
                command.extend(
                    [
                        "--config",
                        str(USER_DATA / config_name(run.static_config, mode)),
                    ]
                )
            command.extend(
                [
                    "--config",
                    str(USER_DATA / scenario_config),
                    "--strategy",
                    run.strategy,
                    "--timerange",
                    "20260101-20260918",
                    "--fee",
                    "0.001",
                    "--export",
                    "signals",
                    "--backtest-directory",
                    str(destination),
                    "--notes",
                    f"{mode}-{run.slug}-static-2025-holdout-2026ytd",
                    "--cache",
                    "none",
                    "--no-color",
                ]
            )
            if run.freqai_model:
                command.extend(["--freqaimodel", run.freqai_model])
            print(f"RUN {mode}/{run.slug}", flush=True)
            subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
