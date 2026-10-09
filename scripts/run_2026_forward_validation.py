#!/usr/bin/env python3
"""Reselect through 2025, then evaluate Spot and futures once in 2026."""

from __future__ import annotations

import argparse
from dataclasses import replace
from itertools import product
import json
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crypto_quant.cross_market import (  # noqa: E402
    enforce_execution_mode,
    load_complete_daily_market,
    load_daily_market,
)
from crypto_quant.gatekeeper import (  # noqa: E402
    apply_hmm_throttle,
    confirm_breakout_entries,
)
from crypto_quant.hmm_regime import (  # noqa: E402
    HMMRegimeConfig,
    backtest_regime_strategy,
    build_regime_features,
    build_strategy_signals,
    performance_metrics,
    walk_forward_regime_probabilities,
)
from crypto_quant.macro_regime import (  # noqa: E402
    build_macro_volume_features,
    combine_regime_signals,
    load_fred_levels,
    walk_forward_macro_forecasts,
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
        default=PROJECT_ROOT / "config" / "forward_2026_validation.json",
    )
    return parser.parse_args()


def parameter_grids() -> dict[str, list[dict[str, object]]]:
    """Use the same economically bounded grids as the earlier research."""

    return {
        "ma_crossover": [
            {"fast": fast, "slow": slow, "filter": filter_name}
            for (fast, slow), filter_name in product(
                [(5, 20), (10, 50), (20, 100)],
                ["none", "macd", "macd_volume"],
            )
        ],
        "bollinger_mean_reversion": [
            {"window": window, "width": width, "exit_z": 0.25}
            for window, width in product([20, 40], [1.5, 2.0, 2.5])
        ],
        "bollinger_breakout": [
            {"window": window, "width": width, "exit_z": 0.0}
            for window, width in product([20, 40], [1.5, 2.0, 2.5])
        ],
        "dynamic_grid": [
            {
                "center_window": center,
                "grid_step": step,
                "levels": 4,
                "trend_threshold": threshold,
                "trend_fast": 20,
                "trend_slow": 100,
            }
            for center, step, threshold in product(
                [20, 40], [0.01, 0.02], [0.03, 0.06]
            )
        ],
        "momentum_only": [
            {
                "sma_fast": fast,
                "sma_slow": slow,
                "rsi_long": rsi_long,
                "rsi_short": 100.0 - rsi_long,
                "minimum_votes": votes,
            }
            for (fast, slow), rsi_long, votes in product(
                [(10, 50), (20, 100), (50, 200)],
                [55.0, 60.0],
                [2, 3],
            )
        ],
        "hmm_switch": [
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
        ],
        "linear_regression": [
            {
                "training_days": training,
                "retrain_days": 30,
                "ridge_penalty": ridge,
                "volatility_threshold": threshold,
            }
            for training, ridge, threshold in product(
                [365, 730], [1.0, 10.0], [0.05, 0.10]
            )
        ],
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


def display_results(frame: pd.DataFrame) -> pd.DataFrame:
    displayed = frame[
        [
            "execution_mode",
            "model",
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
        displayed[column] = (
            (100.0 * displayed[column].astype(float)).round(2).astype(str) + "%"
        )
    displayed["sharpe_ratio_zero_risk_free"] = displayed[
        "sharpe_ratio_zero_risk_free"
    ].astype(float).round(3)
    return displayed


def main() -> None:
    args = parse_args()
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    symbols = tuple(str(value).upper() for value in payload["symbols"])
    test_start, test_end = payload["test_period"]
    folds = [
        DevelopmentFold(name, dates[0], dates[1])
        for name, dates in payload["development_folds"].items()
    ]
    output = PROJECT_ROOT / str(payload["output_directory"])
    output.mkdir(parents=True, exist_ok=True)

    result_rows: list[dict[str, object]] = []
    selection_rows: list[dict[str, object]] = []
    fold_rows: list[dict[str, object]] = []
    stress_rows: list[dict[str, object]] = []
    source_rows: list[dict[str, object]] = []
    test_portfolios: list[pd.DataFrame] = []
    selected_parameters: dict[str, dict[str, dict[str, object]]] = {}

    for market_name in ("spot", "usdt_futures"):
        print(f"\nLoading {market_name} source data ...", flush=True)
        if market_name == "spot":
            markets = {
                symbol: load_daily_market(
                    PROJECT_ROOT / "live" / "market_data" / f"{symbol}_1d.csv"
                )
                for symbol in symbols
            }
            execution_modes = [("spot_long_only", False)]
            source_kind = "Binance public Spot daily API candles"
        else:
            markets = {
                symbol: load_complete_daily_market(
                    PROJECT_ROOT
                    / "processed"
                    / "usdt_futures"
                    / f"{symbol}_1h.csv.gz"
                )
                for symbol in symbols
            }
            execution_modes = [
                ("futures_long_only", False),
                ("futures_long_short", True),
            ]
            source_kind = "Binance USD-M hourly candles aggregated to complete UTC days"

        common_index = markets[symbols[0]].index
        for symbol in symbols[1:]:
            common_index = common_index.intersection(markets[symbol].index)
        markets = {symbol: frame.reindex(common_index) for symbol, frame in markets.items()}
        closes = pd.DataFrame({symbol: markets[symbol]["close"] for symbol in symbols})
        volumes = pd.DataFrame({symbol: markets[symbol]["volume"] for symbol in symbols})
        for symbol in symbols:
            source_rows.append(
                {
                    "market": market_name,
                    "symbol": symbol,
                    "source_kind": source_kind,
                    "first_common_day": common_index[0].date().isoformat(),
                    "last_common_day": common_index[-1].date().isoformat(),
                    "common_days": len(common_index),
                    "test_observations": int(
                        (
                            (common_index >= pd.Timestamp(test_start, tz="UTC"))
                            & (common_index < pd.Timestamp(test_end, tz="UTC"))
                        ).sum()
                    ),
                }
            )

        base_config = HMMRegimeConfig(
            symbols=symbols,
            fee_bps=float(payload["fee_bps"]),
        )
        macro_levels = load_fred_levels(
            PROJECT_ROOT / "datasets" / "external" / "fred", common_index
        )
        macro_volume = build_macro_volume_features(markets, macro_levels)
        volume_columns = [
            column
            for column in macro_volume.columns
            if "volume_" in column or "taker_" in column or "flow_" in column
        ]
        macro_columns = [
            column for column in macro_volume.columns if column not in volume_columns
        ]
        feature_extras: dict[str, pd.DataFrame | None] = {
            "crypto_only": None,
            "crypto_volume": macro_volume[volume_columns],
            "crypto_macro": macro_volume[macro_columns],
            "macro_volume": macro_volume,
        }
        hmm_features = {
            name: build_regime_features(
                closes,
                volatility_window=base_config.feature_volatility_window,
                macro_features=extra,
            )
            for name, extra in feature_extras.items()
        }
        regime_cache: dict[tuple[str, int, int], pd.DataFrame] = {}

        def regimes(feature_set: str, training: int, retrain: int) -> pd.DataFrame:
            key = (feature_set, training, retrain)
            if key not in regime_cache:
                print(
                    f"  Fitting HMM {feature_set}, trailing={training}, "
                    f"refit={retrain} ...",
                    flush=True,
                )
                config = replace(
                    base_config,
                    hmm_training_days=training,
                    hmm_retrain_days=retrain,
                )
                regime_cache[key], _ = walk_forward_regime_probabilities(
                    hmm_features[feature_set], config
                )
            return regime_cache[key]

        model_signal_cache: dict[str, pd.DataFrame] = {}

        def model_signal(family: str, parameters: dict[str, object]) -> pd.DataFrame:
            key = family + ":" + json.dumps(parameters, sort_keys=True)
            if key in model_signal_cache:
                return model_signal_cache[key]
            if family in {
                "ma_crossover",
                "bollinger_mean_reversion",
                "bollinger_breakout",
                "dynamic_grid",
            }:
                signal = build_rule_signals(
                    closes,
                    family=family,
                    parameters=parameters,
                    volumes=volumes,
                )
            elif family == "momentum_only":
                signal = build_rule_signals(
                    closes, family="momentum_vote", parameters=parameters
                )
            elif family == "linear_regression":
                signal, _ = build_linear_regression_signals(closes, **parameters)
            elif family == "hmm_switch":
                config = replace(
                    base_config,
                    hmm_training_days=int(parameters["hmm_training_days"]),
                    hmm_retrain_days=int(parameters["hmm_retrain_days"]),
                    sma_fast=int(parameters["sma_fast"]),
                    sma_slow=int(parameters["sma_slow"]),
                    bollinger_standard_deviations=float(
                        parameters["bollinger_width"]
                    ),
                )
                signal = build_strategy_signals(
                    closes,
                    regimes(
                        "crypto_only",
                        config.hmm_training_days,
                        config.hmm_retrain_days,
                    ),
                    config,
                )
            else:
                raise ValueError(f"Unknown model family {family!r}")
            model_signal_cache[key] = signal
            return signal

        mode_lookup = dict(execution_modes)
        best_model_scores = {
            mode: {family: float("-inf") for family in parameter_grids()}
            for mode, _ in execution_modes
        }
        best_model_parameters: dict[str, dict[str, dict[str, object]]] = {
            mode: {} for mode, _ in execution_modes
        }
        for family, candidates in parameter_grids().items():
            print(
                f"  Selecting {family} from {len(candidates)} candidates ...",
                flush=True,
            )
            for number, parameters in enumerate(candidates, start=1):
                raw_signal = model_signal(family, parameters)
                for mode, allow_short in execution_modes:
                    signal = enforce_execution_mode(
                        raw_signal, allow_short=allow_short
                    )
                    portfolio = backtest_regime_strategy(
                        closes, signal, base_config
                    )
                    score, fold_metrics = score_development_folds(portfolio, folds)
                    candidate_id = f"{family}_{number:02d}"
                    selection_rows.append(
                        {
                            "market": market_name,
                            "execution_mode": mode,
                            "research_layer": "model_selection",
                            "candidate_id": candidate_id,
                            "family": family,
                            "parameters": json.dumps(parameters, sort_keys=True),
                            **score,
                        }
                    )
                    for record in fold_metrics.to_dict(orient="records"):
                        fold_rows.append(
                            {
                                "market": market_name,
                                "execution_mode": mode,
                                "research_layer": "model_selection",
                                "candidate_id": candidate_id,
                                "family": family,
                                **record,
                            }
                        )
                    if float(score["robust_score"]) > best_model_scores[mode][family]:
                        best_model_scores[mode][family] = float(score["robust_score"])
                        best_model_parameters[mode][family] = parameters

        momentum = build_rule_signals(
            closes,
            family="momentum_vote",
            parameters={
                "sma_fast": 20,
                "sma_slow": 100,
                "rsi_long": 55.0,
                "rsi_short": 45.0,
                "minimum_votes": 2,
            },
        )
        mean_reversion = build_rule_signals(
            closes,
            family="bollinger_mean_reversion",
            parameters={"window": 20, "width": 2.0, "exit_z": 0.25},
        )
        strong_breakout_parameters = {"window": 40, "width": 1.5, "exit_z": 0.0}
        strong_breakout = build_rule_signals(
            closes,
            family="bollinger_breakout",
            parameters=strong_breakout_parameters,
        )
        forecast_features = pd.concat(
            [hmm_features["crypto_only"], macro_volume], axis=1, join="inner"
        ).dropna()
        forecasts, _ = walk_forward_macro_forecasts(
            closes,
            forecast_features,
            training_days=730,
            retrain_days=60,
            ridge_penalty=10.0,
            volatility_threshold=0.05,
        )
        macro_candidates: list[dict[str, object]] = []
        for feature_set in feature_extras:
            macro_candidates.append(
                {
                    "feature_set": feature_set,
                    "hmm_training_days": 730,
                    "rule_pair": "momentum_mean_reversion",
                    "confirmation": "none",
                    "candidate_type": "ablation",
                }
            )
        for training, rule_pair, confirmation in product(
            [365, 730],
            ["momentum_mean_reversion", "breakout_flat"],
            ["none", "soft", "agreement"],
        ):
            macro_candidates.append(
                {
                    "feature_set": "macro_volume",
                    "hmm_training_days": training,
                    "rule_pair": rule_pair,
                    "confirmation": confirmation,
                    "candidate_type": "combined_grid",
                }
            )
        macro_signal_cache: dict[str, pd.DataFrame] = {}
        best_macro_score = {mode: float("-inf") for mode, _ in execution_modes}
        best_macro_parameters: dict[str, dict[str, object]] = {}
        print("  Selecting macro-regime candidates ...", flush=True)
        for number, parameters in enumerate(macro_candidates, start=1):
            candidate_id = f"macro_regime_{number:02d}"
            high = (
                momentum
                if parameters["rule_pair"] == "momentum_mean_reversion"
                else strong_breakout
            )
            low = (
                mean_reversion
                if parameters["rule_pair"] == "momentum_mean_reversion"
                else None
            )
            confirmation = str(parameters["confirmation"])
            raw_signal = combine_regime_signals(
                regimes(
                    str(parameters["feature_set"]),
                    int(parameters["hmm_training_days"]),
                    60,
                ),
                high,
                low,
                forecasts if confirmation != "none" else None,
                confirmation=confirmation,
            )
            macro_signal_cache[candidate_id] = raw_signal
            for mode, allow_short in execution_modes:
                portfolio = backtest_regime_strategy(
                    closes,
                    enforce_execution_mode(raw_signal, allow_short=allow_short),
                    base_config,
                )
                score, fold_metrics = score_development_folds(portfolio, folds)
                selection_rows.append(
                    {
                        "market": market_name,
                        "execution_mode": mode,
                        "research_layer": "macro_regime",
                        "candidate_id": candidate_id,
                        "family": "macro_regime",
                        "parameters": json.dumps(parameters, sort_keys=True),
                        **score,
                    }
                )
                for record in fold_metrics.to_dict(orient="records"):
                    fold_rows.append(
                        {
                            "market": market_name,
                            "execution_mode": mode,
                            "research_layer": "macro_regime",
                            "candidate_id": candidate_id,
                            "family": "macro_regime",
                            **record,
                        }
                    )
                if (
                    parameters["candidate_type"] == "combined_grid"
                    and float(score["robust_score"]) > best_macro_score[mode]
                ):
                    best_macro_score[mode] = float(score["robust_score"])
                    best_macro_parameters[mode] = {
                        "candidate_id": candidate_id,
                        **parameters,
                    }

        gatekeeper_ma = build_rule_signals(
            closes,
            family="ma_crossover",
            parameters={"fast": 10, "slow": 50, "filter": "none"},
        )
        gatekeeper_momentum = build_rule_signals(
            closes,
            family="momentum_vote",
            parameters={
                "sma_fast": 10,
                "sma_slow": 50,
                "rsi_long": 60.0,
                "rsi_short": 40.0,
                "minimum_votes": 3,
            },
        )
        confirmations = {
            name: confirm_breakout_entries(
                strong_breakout,
                gatekeeper_ma,
                gatekeeper_momentum,
                confirmation=name,
            )
            for name in ("none", "ma", "momentum", "either", "both")
        }
        gatekeeper_candidates = [
            {
                "feature_set": feature_set,
                "hmm_training_days": training,
                "low_volatility_scale": low_scale,
                "confirmation": confirmation,
            }
            for feature_set, training, low_scale, confirmation in product(
                ["crypto_only", "macro_volume"],
                [365, 730],
                [0.0, 0.25, 0.50],
                ["ma", "momentum", "either", "both"],
            )
        ]
        gatekeeper_signal_cache: dict[str, pd.DataFrame] = {}
        best_gatekeeper_score = {mode: float("-inf") for mode, _ in execution_modes}
        best_gatekeeper_parameters: dict[str, dict[str, object]] = {}
        print("  Selecting gatekeeper candidates ...", flush=True)
        for number, parameters in enumerate(gatekeeper_candidates, start=1):
            candidate_id = f"gatekeeper_{number:02d}"
            raw_signal = apply_hmm_throttle(
                confirmations[str(parameters["confirmation"])],
                regimes(
                    str(parameters["feature_set"]),
                    int(parameters["hmm_training_days"]),
                    60,
                ),
                low_volatility_scale=float(parameters["low_volatility_scale"]),
            )
            gatekeeper_signal_cache[candidate_id] = raw_signal
            for mode, allow_short in execution_modes:
                portfolio = backtest_regime_strategy(
                    closes,
                    enforce_execution_mode(raw_signal, allow_short=allow_short),
                    base_config,
                )
                score, fold_metrics = score_development_folds(portfolio, folds)
                selection_rows.append(
                    {
                        "market": market_name,
                        "execution_mode": mode,
                        "research_layer": "gatekeeper",
                        "candidate_id": candidate_id,
                        "family": "gatekeeper",
                        "parameters": json.dumps(parameters, sort_keys=True),
                        **score,
                    }
                )
                for record in fold_metrics.to_dict(orient="records"):
                    fold_rows.append(
                        {
                            "market": market_name,
                            "execution_mode": mode,
                            "research_layer": "gatekeeper",
                            "candidate_id": candidate_id,
                            "family": "gatekeeper",
                            **record,
                        }
                    )
                if float(score["robust_score"]) > best_gatekeeper_score[mode]:
                    best_gatekeeper_score[mode] = float(score["robust_score"])
                    best_gatekeeper_parameters[mode] = {
                        "candidate_id": candidate_id,
                        **parameters,
                    }

        for mode, allow_short in execution_modes:
            print(f"  Evaluating frozen 2026 test for {mode} ...", flush=True)
            selected_parameters[mode] = {
                "model_selection": best_model_parameters[mode],
                "macro_regime": best_macro_parameters[mode],
                "gatekeeper": best_gatekeeper_parameters[mode],
            }
            selected_signals: dict[str, tuple[pd.DataFrame, dict[str, object]]] = {
                "strong_bollinger_40_1.5": (
                    strong_breakout,
                    strong_breakout_parameters,
                )
            }
            for family, parameters in best_model_parameters[mode].items():
                label = (
                    "bollinger_breakout_reselected"
                    if family == "bollinger_breakout"
                    else f"{family}_reselected"
                )
                selected_signals[label] = (
                    model_signal(family, parameters),
                    parameters,
                )
            macro_selected = best_macro_parameters[mode]
            selected_signals["macro_regime_reselected"] = (
                macro_signal_cache[str(macro_selected["candidate_id"])],
                macro_selected,
            )
            gatekeeper_selected = best_gatekeeper_parameters[mode]
            gatekeeper_raw = gatekeeper_signal_cache[
                str(gatekeeper_selected["candidate_id"])
            ]
            selected_confirmation = confirmations[
                str(gatekeeper_selected["confirmation"])
            ]
            selected_regime = regimes(
                str(gatekeeper_selected["feature_set"]),
                int(gatekeeper_selected["hmm_training_days"]),
                60,
            )
            selected_scale = float(gatekeeper_selected["low_volatility_scale"])
            selected_signals.update(
                {
                    "gatekeeper_confirmation_only": (
                        selected_confirmation,
                        {"confirmation": gatekeeper_selected["confirmation"]},
                    ),
                    "gatekeeper_hmm_throttle_only": (
                        apply_hmm_throttle(
                            strong_breakout,
                            selected_regime,
                            low_volatility_scale=selected_scale,
                        ),
                        {
                            "feature_set": gatekeeper_selected["feature_set"],
                            "hmm_training_days": gatekeeper_selected[
                                "hmm_training_days"
                            ],
                            "low_volatility_scale": selected_scale,
                        },
                    ),
                    "full_gatekeeper_reselected": (
                        gatekeeper_raw,
                        gatekeeper_selected,
                    ),
                }
            )

            for model, (raw_signal, parameters) in selected_signals.items():
                signal = enforce_execution_mode(
                    raw_signal, allow_short=allow_short
                )
                portfolio = backtest_regime_strategy(closes, signal, base_config)
                result_rows.append(
                    {
                        "market": market_name,
                        "execution_mode": mode,
                        "model": model,
                        "parameters": json.dumps(parameters, sort_keys=True),
                        **performance_metrics(
                            portfolio, start=test_start, end=test_end
                        ),
                    }
                )
                test_sample = portfolio.loc[
                    (portfolio.index >= pd.Timestamp(test_start, tz="UTC"))
                    & (portfolio.index < pd.Timestamp(test_end, tz="UTC"))
                ].rename_axis("date").reset_index()
                test_sample.insert(0, "model", model)
                test_sample.insert(0, "execution_mode", mode)
                test_portfolios.append(test_sample)

                if model in {
                    "strong_bollinger_40_1.5",
                    "bollinger_breakout_reselected",
                    "hmm_switch_reselected",
                    "macro_regime_reselected",
                    "full_gatekeeper_reselected",
                }:
                    for fee_bps in payload["cost_stress_bps"]:
                        stressed = backtest_regime_strategy(
                            closes,
                            signal,
                            replace(base_config, fee_bps=float(fee_bps)),
                        )
                        stress_rows.append(
                            {
                                "market": market_name,
                                "execution_mode": mode,
                                "model": model,
                                "fee_bps": fee_bps,
                                **performance_metrics(
                                    stressed, start=test_start, end=test_end
                                ),
                            }
                        )

    results = pd.DataFrame.from_records(result_rows).sort_values(
        ["execution_mode", "sharpe_ratio_zero_risk_free"],
        ascending=[True, False],
        kind="stable",
    )
    results.to_csv(output / "test_results.csv", index=False)
    pd.DataFrame.from_records(selection_rows).to_csv(
        output / "development_candidate_scores.csv", index=False
    )
    pd.DataFrame.from_records(fold_rows).to_csv(
        output / "development_fold_metrics.csv", index=False
    )
    pd.DataFrame.from_records(stress_rows).to_csv(
        output / "cost_stress.csv", index=False
    )
    pd.DataFrame.from_records(source_rows).to_csv(
        output / "source_manifest.csv", index=False
    )
    pd.concat(test_portfolios, ignore_index=True, sort=False).to_csv(
        output / "test_portfolios.csv.gz", index=False, compression="gzip"
    )
    (output / "selected_parameters.json").write_text(
        json.dumps(selected_parameters, indent=2) + "\n", encoding="utf-8"
    )

    core_models = [
        "strong_bollinger_40_1.5",
        "bollinger_breakout_reselected",
        "hmm_switch_reselected",
        "macro_regime_reselected",
        "full_gatekeeper_reselected",
    ]
    core = results.loc[results["model"].isin(core_models)]
    winners = (
        results.sort_values(
            ["execution_mode", "sharpe_ratio_zero_risk_free"],
            ascending=[True, False],
            kind="stable",
        )
        .groupby("execution_mode", sort=False)
        .head(1)
    )
    source_frame = pd.DataFrame.from_records(source_rows)
    test_observations = int(source_frame["test_observations"].min())
    report = f"""# 2026 Forward Validation After Selection Through 2025

All parameter choices were ranked on eight half-year folds from 1 January 2022
through 31 December 2025. The choices were then frozen and evaluated from
`{test_start}` through `{test_end}` (end exclusive), giving
**{test_observations} daily observations** through 16 September 2026.

Spot is evaluated long/cash. Futures is evaluated both long/cash and
long/short. Every portfolio applies a close-known signal to the following
day's return, charges {float(payload['fee_bps']):g} bps per unit of one-way
turnover, targets 20% annualized volatility, caps each asset at 50%, and caps
gross exposure at 100%.

## Core requested models

{markdown_table(display_results(core))}

## Best test Sharpe in each execution mode

{markdown_table(display_results(winners))}

## Validation status

This run does not use 2026 observations for parameter ranking. It is therefore
a correctly separated forward test for the re-selection procedure. However,
2026 had already been inspected in earlier futures reports, so it is not a
globally pristine holdout for the overall research project. No parameters
should now be changed in response to this table; the next clean confirmation
must use later data.

The Spot source is complete daily public-API data through 16 September 2026.
The futures source is complete hourly USD-M data through 17 September 2026;
the comparison deliberately stops one day earlier so every mode uses the same
dates. Macro series are available through 15–16 September and are lagged by
one day.

Funding, borrow availability, liquidation, historical bid/ask spreads, market
impact, and intraday fill sequencing are not modeled. Cost stress at 5, 10,
20, and 30 bps is reported separately without reselecting parameters.
"""
    (output / "research_report.md").write_text(report, encoding="utf-8")
    print("\n2026 forward-validation core results", flush=True)
    print(display_results(core).to_string(index=False), flush=True)
    print(f"Artifacts -> {output.relative_to(PROJECT_ROOT)}", flush=True)


if __name__ == "__main__":
    main()
