#!/usr/bin/env python3
"""Apply frozen strategy choices to Spot and USD-M futures without retuning."""

from __future__ import annotations

import argparse
from dataclasses import replace
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
    build_linear_regression_signals,
    build_rule_signals,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "cross_market_validation.json",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    payload = read_json(args.config)
    symbols = tuple(str(value).upper() for value in payload["symbols"])
    validation_start, validation_end = payload["validation_period"]
    output = PROJECT_ROOT / str(payload["output_directory"])
    output.mkdir(parents=True, exist_ok=True)

    model_parameters = read_json(
        PROJECT_ROOT / "reports" / "model_selection" / "selected_parameters.json"
    )
    macro_parameters = read_json(
        PROJECT_ROOT / "reports" / "macro_regime" / "selected_parameters.json"
    )
    gatekeeper_parameters = read_json(
        PROJECT_ROOT / "reports" / "gatekeeper" / "selected_parameters.json"
    )

    result_rows: list[dict[str, object]] = []
    stress_rows: list[dict[str, object]] = []
    source_rows: list[dict[str, object]] = []
    signal_outputs: list[pd.DataFrame] = []
    portfolio_outputs: list[pd.DataFrame] = []

    for market_name in payload["markets"]:
        market_name = str(market_name)
        print(f"Loading {market_name} daily bars ...")
        markets = {
            symbol: load_complete_daily_market(
                PROJECT_ROOT / "processed" / market_name / f"{symbol}_1h.csv.gz"
            )
            for symbol in symbols
        }
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
                    "first_complete_day": common_index[0].date().isoformat(),
                    "last_complete_day": common_index[-1].date().isoformat(),
                    "complete_common_days": len(common_index),
                    "source": str(
                        (
                            PROJECT_ROOT
                            / "processed"
                            / market_name
                            / f"{symbol}_1h.csv.gz"
                        ).resolve()
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

        def regimes(feature_set: str, training_days: int, retrain_days: int) -> pd.DataFrame:
            key = (feature_set, training_days, retrain_days)
            if key not in regime_cache:
                print(
                    f"  Fitting {market_name} HMM: {feature_set}, "
                    f"training={training_days}, retrain={retrain_days} ..."
                )
                hmm_config = replace(
                    base_config,
                    hmm_training_days=training_days,
                    hmm_retrain_days=retrain_days,
                )
                regime_cache[key], _ = walk_forward_regime_probabilities(
                    hmm_features[feature_set], hmm_config
                )
            return regime_cache[key]

        frozen_signals: dict[str, pd.DataFrame] = {}
        for family, parameters in model_parameters.items():
            parameters = dict(parameters)
            if family in {
                "ma_crossover",
                "bollinger_mean_reversion",
                "bollinger_breakout",
                "dynamic_grid",
            }:
                label = (
                    "strong_bollinger_breakout"
                    if family == "bollinger_breakout"
                    else family
                )
                frozen_signals[label] = build_rule_signals(
                    closes,
                    family=family,
                    parameters=parameters,
                    volumes=volumes,
                )
            elif family == "momentum_only":
                frozen_signals[family] = build_rule_signals(
                    closes, family="momentum_vote", parameters=parameters
                )
            elif family == "linear_regression":
                frozen_signals[family], _ = build_linear_regression_signals(
                    closes, **parameters
                )
            elif family == "hmm_switch":
                hmm_config = replace(
                    base_config,
                    hmm_training_days=int(parameters["hmm_training_days"]),
                    hmm_retrain_days=int(parameters["hmm_retrain_days"]),
                    sma_fast=int(parameters["sma_fast"]),
                    sma_slow=int(parameters["sma_slow"]),
                    bollinger_standard_deviations=float(
                        parameters["bollinger_width"]
                    ),
                )
                frozen_signals[family] = build_strategy_signals(
                    closes,
                    regimes(
                        "crypto_only",
                        hmm_config.hmm_training_days,
                        hmm_config.hmm_retrain_days,
                    ),
                    hmm_config,
                )

        breakout = frozen_signals["strong_bollinger_breakout"]
        macro_feature_set = str(macro_parameters["feature_set"])
        macro_regimes = regimes(
            macro_feature_set,
            int(macro_parameters["hmm_training_days"]),
            60,
        )
        macro_rule_pair = str(macro_parameters["rule_pair"])
        macro_confirmation = str(macro_parameters["confirmation"])
        if macro_rule_pair == "momentum_mean_reversion":
            macro_high = build_rule_signals(
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
            macro_low: pd.DataFrame | None = build_rule_signals(
                closes,
                family="bollinger_mean_reversion",
                parameters={"window": 20, "width": 2.0, "exit_z": 0.25},
            )
        else:
            macro_high = breakout
            macro_low = None
        forecasts: pd.DataFrame | None = None
        if macro_confirmation != "none":
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
        frozen_signals["macro_regime"] = combine_regime_signals(
            macro_regimes,
            macro_high,
            macro_low,
            forecasts,
            confirmation=macro_confirmation,
        )

        gatekeeper_feature_set = str(gatekeeper_parameters["feature_set"])
        gatekeeper_regimes = regimes(
            gatekeeper_feature_set,
            int(gatekeeper_parameters["hmm_training_days"]),
            60,
        )
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
        selected_confirmation = confirm_breakout_entries(
            breakout,
            gatekeeper_ma,
            gatekeeper_momentum,
            confirmation=str(gatekeeper_parameters["confirmation"]),
        )
        low_scale = float(gatekeeper_parameters["low_volatility_scale"])
        frozen_signals["gatekeeper_confirmation_only"] = selected_confirmation
        frozen_signals["gatekeeper_hmm_throttle_only"] = apply_hmm_throttle(
            breakout, gatekeeper_regimes, low_volatility_scale=low_scale
        )
        frozen_signals["full_gatekeeper"] = apply_hmm_throttle(
            selected_confirmation,
            gatekeeper_regimes,
            low_volatility_scale=low_scale,
        )

        execution_modes = (
            [("spot_long_only", False)]
            if market_name == "spot"
            else [("futures_long_only", False), ("futures_long_short", True)]
        )
        for execution_mode, allow_short in execution_modes:
            print(f"  Backtesting {execution_mode} ...")
            for model, raw_signals in frozen_signals.items():
                signals = enforce_execution_mode(
                    raw_signals, allow_short=allow_short
                )
                portfolio = backtest_regime_strategy(closes, signals, base_config)
                result_rows.append(
                    {
                        "market": market_name,
                        "execution_mode": execution_mode,
                        "model": model,
                        "parameters_frozen_from": "futures_development_selection",
                        **performance_metrics(
                            portfolio, start=validation_start, end=validation_end
                        ),
                    }
                )
                signal_sample = signals.loc[
                    pd.to_datetime(signals["date"], utc=True).ge(
                        pd.Timestamp(validation_start, tz="UTC")
                    )
                    & pd.to_datetime(signals["date"], utc=True).lt(
                        pd.Timestamp(validation_end, tz="UTC")
                    )
                ].copy()
                signal_sample.insert(0, "model", model)
                signal_sample.insert(0, "execution_mode", execution_mode)
                signal_outputs.append(signal_sample)
                portfolio_sample = portfolio.loc[
                    (portfolio.index >= pd.Timestamp(validation_start, tz="UTC"))
                    & (portfolio.index < pd.Timestamp(validation_end, tz="UTC"))
                ].rename_axis("date").reset_index()
                portfolio_sample.insert(0, "model", model)
                portfolio_sample.insert(0, "execution_mode", execution_mode)
                portfolio_outputs.append(portfolio_sample)

                if model in {
                    "strong_bollinger_breakout",
                    "hmm_switch",
                    "macro_regime",
                    "full_gatekeeper",
                }:
                    for fee_bps in payload["cost_stress_bps"]:
                        stressed = backtest_regime_strategy(
                            closes,
                            signals,
                            replace(base_config, fee_bps=float(fee_bps)),
                        )
                        stress_rows.append(
                            {
                                "market": market_name,
                                "execution_mode": execution_mode,
                                "model": model,
                                "fee_bps": fee_bps,
                                **performance_metrics(
                                    stressed,
                                    start=validation_start,
                                    end=validation_end,
                                ),
                            }
                        )

    results = pd.DataFrame.from_records(result_rows).sort_values(
        ["execution_mode", "sharpe_ratio_zero_risk_free"],
        ascending=[True, False],
        kind="stable",
    )
    results.to_csv(output / "results.csv", index=False)
    pd.DataFrame.from_records(stress_rows).to_csv(
        output / "cost_stress.csv", index=False
    )
    pd.DataFrame.from_records(source_rows).to_csv(
        output / "source_manifest.csv", index=False
    )
    pd.concat(signal_outputs, ignore_index=True, sort=False).to_csv(
        output / "signals.csv.gz", index=False, compression="gzip"
    )
    pd.concat(portfolio_outputs, ignore_index=True, sort=False).to_csv(
        output / "portfolios.csv.gz", index=False, compression="gzip"
    )

    winners = (
        results.sort_values(
            ["execution_mode", "sharpe_ratio_zero_risk_free"],
            ascending=[True, False],
            kind="stable",
        )
        .groupby("execution_mode", sort=False)
        .head(1)
    )
    selected_models = results.loc[
        results["model"].isin(
            [
                "strong_bollinger_breakout",
                "hmm_switch",
                "macro_regime",
                "full_gatekeeper",
            ]
        )
    ]
    report = f"""# Frozen Cross-Market Validation

The parameters in this comparison were copied from the existing futures
development selections and were **not reselected on Spot or on the 2025
comparison period**. The common half-open validation window is
`{validation_start}` through `{validation_end}`. Every model uses next-day
execution, inverse-volatility sizing, a 50% per-asset cap, a 100% gross cap, a
20% annualized volatility target, and {float(payload['fee_bps']):g} bps per
unit of one-way turnover.

Three modes separate the source of performance:

- `spot_long_only`: ordinary Spot constraints; negative signals become cash.
- `futures_long_only`: futures prices with negative signals disabled.
- `futures_long_short`: the original signed perpetual-futures strategy.

## Core requested models

{markdown_table(display_results(selected_models))}

## Best Sharpe in each execution mode

{markdown_table(display_results(winners))}

## Interpretation rules

This is a useful frozen-parameter transfer test, but not a new pristine
temporal holdout: 2025 has already appeared in earlier reports. Spot and
futures also have different microstructure and price formation. A result that
works only in `futures_long_short` may depend on short exposure; a result that
works in both long-only modes is stronger evidence that the directional rule
transfers across markets.

Funding, borrow availability, liquidation, bid/ask spread history, market
impact, and intraday fill sequencing remain unmodeled. `cost_stress.csv`
repeats the four core models at 5, 10, 20, and 30 bps without changing their
parameters.
"""
    (output / "research_report.md").write_text(report, encoding="utf-8")
    print("\nCore cross-market results")
    print(display_results(selected_models).to_string(index=False))
    print(f"Artifacts -> {output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
