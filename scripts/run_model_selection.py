#!/usr/bin/env python3
"""Tune rule/HMM/regression families on development folds, then test once."""

from __future__ import annotations

import argparse
from dataclasses import replace
from itertools import product
import json
from pathlib import Path
import sys
from typing import Callable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crypto_quant.hmm_regime import (  # noqa: E402
    HMMRegimeConfig,
    backtest_regime_strategy,
    build_regime_features,
    build_strategy_signals,
    load_daily_futures,
    performance_metrics,
    walk_forward_regime_probabilities,
)
from crypto_quant.strategy_selection import (  # noqa: E402
    DevelopmentFold,
    build_linear_regression_signals,
    build_rule_signals,
    score_development_folds,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "strategy_selection.json",
    )
    return parser.parse_args()


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def parameter_grids() -> dict[str, list[dict[str, object]]]:
    ma = [
        {"fast": fast, "slow": slow, "filter": filter_name}
        for (fast, slow), filter_name in product(
            [(5, 20), (10, 50), (20, 100)],
            ["none", "macd", "macd_volume"],
        )
    ]
    bollinger_mean_reversion = [
        {"window": window, "width": width, "exit_z": 0.25}
        for window, width in product([20, 40], [1.5, 2.0, 2.5])
    ]
    bollinger_breakout = [
        {"window": window, "width": width, "exit_z": 0.0}
        for window, width in product([20, 40], [1.5, 2.0, 2.5])
    ]
    grid = [
        {
            "center_window": center,
            "grid_step": step,
            "levels": 4,
            "trend_threshold": trend,
            "trend_fast": 20,
            "trend_slow": 100,
        }
        for center, step, trend in product([20, 40], [0.01, 0.02], [0.03, 0.06])
    ]
    momentum = [
        {
            "sma_fast": fast,
            "sma_slow": slow,
            "rsi_long": long_threshold,
            "rsi_short": 100.0 - long_threshold,
            "minimum_votes": votes,
        }
        for (fast, slow), long_threshold, votes in product(
            [(10, 50), (20, 100), (50, 200)], [55.0, 60.0], [2, 3]
        )
    ]
    hmm = [
        {
            "hmm_training_days": training,
            "hmm_retrain_days": retrain,
            "sma_fast": fast,
            "sma_slow": slow,
            "bollinger_width": width,
        }
        for (training, retrain), (fast, slow), width in product(
            [(365, 30), (730, 30), (730, 60)],
            [(10, 50), (20, 100)],
            [1.5, 2.0],
        )
    ]
    regression = [
        {
            "training_days": training,
            "retrain_days": 30,
            "ridge_penalty": ridge,
            "volatility_threshold": threshold,
        }
        for training, ridge, threshold in product(
            [365, 730], [1.0, 10.0], [0.05, 0.10]
        )
    ]
    return {
        "ma_crossover": ma,
        "bollinger_mean_reversion": bollinger_mean_reversion,
        "bollinger_breakout": bollinger_breakout,
        "dynamic_grid": grid,
        "momentum_only": momentum,
        "hmm_switch": hmm,
        "linear_regression": regression,
    }


def default_parameters() -> dict[str, dict[str, object]]:
    return {
        "ma_crossover": {"fast": 5, "slow": 20, "filter": "none"},
        "bollinger_mean_reversion": {"window": 20, "width": 2.0, "exit_z": 0.25},
        "bollinger_breakout": {"window": 20, "width": 2.0, "exit_z": 0.0},
        "dynamic_grid": {
            "center_window": 20,
            "grid_step": 0.02,
            "levels": 4,
            "trend_threshold": 0.06,
            "trend_fast": 20,
            "trend_slow": 100,
        },
        "momentum_only": {
            "sma_fast": 20,
            "sma_slow": 100,
            "rsi_long": 55.0,
            "rsi_short": 45.0,
            "minimum_votes": 2,
        },
        "hmm_switch": {
            "hmm_training_days": 730,
            "hmm_retrain_days": 30,
            "sma_fast": 20,
            "sma_slow": 100,
            "bollinger_width": 2.0,
        },
        "linear_regression": {
            "training_days": 365,
            "retrain_days": 30,
            "ridge_penalty": 10.0,
            "volatility_threshold": 0.05,
        },
    }


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])


def format_results(frame: pd.DataFrame) -> pd.DataFrame:
    displayed = frame[
        [
            "stage",
            "family",
            "period",
            "total_return",
            "maximum_drawdown",
            "sharpe_ratio_zero_risk_free",
            "average_daily_turnover",
            "average_gross_exposure",
        ]
    ].copy()
    for column in (
        "total_return",
        "maximum_drawdown",
        "average_daily_turnover",
        "average_gross_exposure",
    ):
        displayed[column] = (100.0 * displayed[column].astype(float)).round(2).astype(str) + "%"
    displayed["sharpe_ratio_zero_risk_free"] = displayed[
        "sharpe_ratio_zero_risk_free"
    ].astype(float).round(3)
    return displayed


def main() -> None:
    args = parse_args()
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    symbols = tuple(str(value).upper() for value in payload["symbols"])
    data_directory = resolve_path(payload["market_data_directory"])
    output = resolve_path(payload["output_directory"])
    output.mkdir(parents=True, exist_ok=True)
    base_config = HMMRegimeConfig(
        symbols=symbols,
        initial_equity=float(payload["initial_equity"]),
        fee_bps=float(payload["selection_fee_bps"]),
        risk_volatility_window=int(payload["risk_volatility_window"]),
        target_annual_volatility=float(payload["target_annual_volatility"]),
        maximum_asset_weight=float(payload["maximum_asset_weight"]),
        maximum_gross_exposure=float(payload["maximum_gross_exposure"]),
        covariance_window=int(payload["covariance_window"]),
    )
    base_config.validate()

    closes: list[pd.Series] = []
    volumes: list[pd.Series] = []
    source_manifest: list[dict[str, object]] = []
    for symbol in symbols:
        path = data_directory / f"{symbol}_1h.csv.gz"
        daily = load_daily_futures(path)
        closes.append(daily["close"].rename(symbol))
        volumes.append(daily["volume"].rename(symbol))
        source_manifest.append(
            {
                "symbol": symbol,
                "path": str(path.resolve()),
                "hourly_file_bytes": path.stat().st_size,
                "first_complete_day": daily["close"].first_valid_index().isoformat(),
                "last_complete_day": daily["close"].last_valid_index().isoformat(),
                "complete_days": int(daily["close"].notna().sum()),
            }
        )
    close_frame = pd.concat(closes, axis=1, join="inner").dropna().sort_index()
    volume_frame = pd.concat(volumes, axis=1, join="inner").reindex(close_frame.index)
    features = build_regime_features(
        close_frame, volatility_window=base_config.feature_volatility_window
    )
    folds = [
        DevelopmentFold(name, boundaries[0], boundaries[1])
        for name, boundaries in payload["development_folds"].items()
    ]
    grids = parameter_grids()
    defaults = default_parameters()

    regime_cache: dict[tuple[int, int], pd.DataFrame] = {}
    signal_cache: dict[str, pd.DataFrame] = {}
    portfolio_cache: dict[str, pd.DataFrame] = {}

    def cache_key(family: str, parameters: dict[str, object]) -> str:
        return family + ":" + json.dumps(parameters, sort_keys=True)

    def build_signals(family: str, parameters: dict[str, object]) -> pd.DataFrame:
        key = cache_key(family, parameters)
        if key in signal_cache:
            return signal_cache[key]
        if family in {
            "ma_crossover",
            "bollinger_mean_reversion",
            "bollinger_breakout",
            "dynamic_grid",
        }:
            signals = build_rule_signals(
                close_frame,
                family=family,
                parameters=parameters,
                volumes=volume_frame,
            )
        elif family == "momentum_only":
            signals = build_rule_signals(
                close_frame,
                family="momentum_vote",
                parameters=parameters,
            )
        elif family == "linear_regression":
            signals, _ = build_linear_regression_signals(close_frame, **parameters)
        elif family == "hmm_switch":
            training = int(parameters["hmm_training_days"])
            retrain = int(parameters["hmm_retrain_days"])
            regime_key = (training, retrain)
            hmm_config = replace(
                base_config,
                hmm_training_days=training,
                hmm_retrain_days=retrain,
                sma_fast=int(parameters["sma_fast"]),
                sma_slow=int(parameters["sma_slow"]),
                bollinger_standard_deviations=float(parameters["bollinger_width"]),
            )
            if regime_key not in regime_cache:
                print(f"Fitting HMM training={training} retrain={retrain} ...")
                regimes, _ = walk_forward_regime_probabilities(features, hmm_config)
                regime_cache[regime_key] = regimes
            signals = build_strategy_signals(
                close_frame, regime_cache[regime_key], hmm_config
            )
        else:
            raise ValueError(f"Unknown family {family!r}")
        signal_cache[key] = signals
        return signals

    def build_portfolio(family: str, parameters: dict[str, object]) -> pd.DataFrame:
        key = cache_key(family, parameters)
        if key not in portfolio_cache:
            portfolio_cache[key] = backtest_regime_strategy(
                close_frame, build_signals(family, parameters), base_config
            )
        return portfolio_cache[key]

    candidate_rows: list[dict[str, object]] = []
    fold_rows: list[dict[str, object]] = []
    selected: dict[str, dict[str, object]] = {}
    for family, candidates in grids.items():
        best_score = float("-inf")
        print(f"Selecting {family} from {len(candidates)} development-only candidates ...")
        for candidate_number, parameters in enumerate(candidates, start=1):
            portfolio = build_portfolio(family, parameters)
            score, fold_metrics = score_development_folds(portfolio, folds)
            candidate_id = f"{family}_{candidate_number:02d}"
            candidate_rows.append(
                {
                    "candidate_id": candidate_id,
                    "family": family,
                    "parameters": json.dumps(parameters, sort_keys=True),
                    **score,
                }
            )
            for record in fold_metrics.to_dict(orient="records"):
                fold_rows.append(
                    {
                        "candidate_id": candidate_id,
                        "family": family,
                        "parameters": json.dumps(parameters, sort_keys=True),
                        **record,
                    }
                )
            if float(score["robust_score"]) > best_score:
                best_score = float(score["robust_score"])
                selected[family] = parameters

    candidates = pd.DataFrame.from_records(candidate_rows).sort_values(
        ["family", "robust_score"], ascending=[True, False], kind="stable"
    )
    fold_metrics = pd.DataFrame.from_records(fold_rows)
    candidates.to_csv(output / "development_candidate_scores.csv", index=False)
    fold_metrics.to_csv(output / "development_fold_metrics.csv", index=False)
    (output / "selected_parameters.json").write_text(
        json.dumps(selected, indent=2) + "\n", encoding="utf-8"
    )
    (output / "source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8"
    )

    development_start, development_end = payload["development_period"]
    holdout_start, holdout_end = payload["holdout_period"]
    result_rows: list[dict[str, object]] = []
    selected_signals: list[pd.DataFrame] = []
    selected_portfolios: list[pd.DataFrame] = []
    for stage, specifications in (
        ("default_baseline", defaults),
        ("development_selected", selected),
    ):
        for family, parameters in specifications.items():
            portfolio = build_portfolio(family, parameters)
            for period, start, end in (
                ("development", development_start, development_end),
                ("holdout", holdout_start, holdout_end),
            ):
                result_rows.append(
                    {
                        "stage": stage,
                        "family": family,
                        "period": period,
                        "parameters": json.dumps(parameters, sort_keys=True),
                        **performance_metrics(portfolio, start=start, end=end),
                    }
                )
            if stage == "development_selected":
                labeled_signals = build_signals(family, parameters).copy()
                labeled_signals.insert(0, "family", family)
                selected_signals.append(labeled_signals)
                labeled_portfolio = portfolio.rename_axis("date").reset_index()
                labeled_portfolio.insert(0, "family", family)
                selected_portfolios.append(labeled_portfolio)

    results = pd.DataFrame.from_records(result_rows)
    results.to_csv(output / "baseline_and_selected_results.csv", index=False)
    pd.concat(selected_signals, ignore_index=True).to_csv(
        output / "selected_signals.csv.gz", index=False, compression="gzip"
    )
    pd.concat(selected_portfolios, ignore_index=True).to_csv(
        output / "selected_portfolios.csv.gz", index=False, compression="gzip"
    )

    stress_rows: list[dict[str, object]] = []
    for family, parameters in selected.items():
        signals = build_signals(family, parameters)
        for fee_bps in payload["cost_stress_bps"]:
            stressed_config = replace(base_config, fee_bps=float(fee_bps))
            portfolio = backtest_regime_strategy(close_frame, signals, stressed_config)
            for period, start, end in (
                ("development", development_start, development_end),
                ("holdout", holdout_start, holdout_end),
            ):
                stress_rows.append(
                    {
                        "family": family,
                        "fee_bps": fee_bps,
                        "period": period,
                        **performance_metrics(portfolio, start=start, end=end),
                    }
                )
    stress = pd.DataFrame.from_records(stress_rows)
    stress.to_csv(output / "cost_stress.csv", index=False)

    selected_holdout = results.loc[
        results["stage"].eq("development_selected") & results["period"].eq("holdout")
    ].sort_values("sharpe_ratio_zero_risk_free", ascending=False)
    winner = selected_holdout.iloc[0]
    report = f"""# BTC/ETH Development-Only Model Selection

All tests use the local hourly Binance USD-M futures files listed in `source_manifest.json`, aggregated to complete UTC days. Parameters were selected only from four rolling six-month folds inside 2022–2023. The 2024–2025 holdout was evaluated only after one configuration per family had been frozen.

The attached reference was implemented as MA crossover (including optional MACD and volume confirmation), Bollinger mean reversion, Bollinger breakout, and a dynamic-grid proxy. The grid result is a daily-close staged-exposure approximation, not a simulation of intraday limit-order fills.

## Default baselines and development-selected models

{markdown_table(format_results(results))}

## Outcome

The highest selected-model holdout Sharpe was **{float(winner['sharpe_ratio_zero_risk_free']):.3f}** for **{winner['family']}**, with return **{100 * float(winner['total_return']):.2f}%** and maximum drawdown **{100 * float(winner['maximum_drawdown']):.2f}%**. This is a comparison result, not sufficient evidence for deployment.

`selected_parameters.json` contains the frozen choices. `development_candidate_scores.csv` and `development_fold_metrics.csv` show why each choice won. `cost_stress.csv` applies 5, 10, 20, and 30 bps per unit of one-way turnover without reselecting parameters.

## Selection rule

The robust development score is median fold Sharpe minus penalties for Sharpe dispersion, worst fold drawdown, turnover, and near-zero exposure. Total return is reported but is not the selection objective. HMM state estimation and linear regression are both walk-forward; a close's signal is applied to the following day's return.

## Important limitations

- Perpetual funding, order-book spreads, liquidation, latency, and market impact are absent.
- The daily grid proxy cannot establish whether real intraday grid orders would fill in a favorable sequence. That requires an hourly event-driven fill model.
- Seeing the holdout means it must now remain locked. Any additional ideas should be selected on earlier data or a later forward period, not tuned to 2024–2025.
- A linear model can be useful as a control, but a positive in-sample coefficient or forecast is not proof of a stable market relationship.
"""
    (output / "research_report.md").write_text(report, encoding="utf-8")
    print("\nSelected holdout comparison")
    print(
        format_results(
            results.loc[
                results["stage"].eq("development_selected")
                & results["period"].eq("holdout")
            ]
        ).to_string(index=False)
    )
    print(f"Artifacts -> {output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
