#!/usr/bin/env python3
"""Test HMM + dynamic macro relationships + volume on 2025-2026 data."""

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

from crypto_quant.hmm_regime import (  # noqa: E402
    HMMRegimeConfig,
    backtest_regime_strategy,
    build_regime_features,
    performance_metrics,
    walk_forward_regime_probabilities,
)
from crypto_quant.macro_regime import (  # noqa: E402
    build_macro_volume_features,
    combine_regime_signals,
    load_extended_daily_futures,
    load_fred_levels,
    walk_forward_macro_forecasts,
)
from crypto_quant.strategy_selection import (  # noqa: E402
    DevelopmentFold,
    build_rule_signals,
    score_development_folds,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "macro_regime.json",
    )
    return parser.parse_args()


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])


def main() -> None:
    args = parse_args()
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    symbols = tuple(payload["symbols"])
    output = PROJECT_ROOT / payload["output_directory"]
    output.mkdir(parents=True, exist_ok=True)
    base_config = HMMRegimeConfig(
        symbols=symbols,
        fee_bps=float(payload["selection_fee_bps"]),
    )

    markets: dict[str, pd.DataFrame] = {}
    source_rows: list[dict[str, object]] = []
    for symbol in symbols:
        market = load_extended_daily_futures(
            PROJECT_ROOT / "processed" / "usdt_futures" / f"{symbol}_1h.csv.gz",
            monthly_daily_directory=(
                PROJECT_ROOT
                / "datasets"
                / "usdt_futures"
                / "data"
                / "futures"
                / "um"
                / "monthly"
                / "klines"
                / symbol
                / "1d"
            ),
            daily_directory=(
                PROJECT_ROOT
                / "datasets"
                / "usdt_futures"
                / "data"
                / "futures"
                / "um"
                / "daily"
                / "klines"
                / symbol
                / "1d"
            ),
        )
        markets[symbol] = market
        source_rows.append(
            {
                "symbol": symbol,
                "observations": len(market),
                "first_date": market.index[0].date().isoformat(),
                "last_date": market.index[-1].date().isoformat(),
                "last_close": float(market["close"].iloc[-1]),
            }
        )
    common_index = markets[symbols[0]].index
    for symbol in symbols[1:]:
        common_index = common_index.intersection(markets[symbol].index)
    markets = {symbol: frame.reindex(common_index) for symbol, frame in markets.items()}
    closes = pd.DataFrame({symbol: markets[symbol]["close"] for symbol in symbols})
    volumes = pd.DataFrame({symbol: markets[symbol]["volume"] for symbol in symbols})
    macro_levels = load_fred_levels(
        PROJECT_ROOT / "datasets" / "external" / "fred", common_index
    )
    extra = build_macro_volume_features(markets, macro_levels)

    volume_columns = [
        column
        for column in extra.columns
        if "volume_" in column or "taker_" in column or "flow_" in column
    ]
    macro_columns = [column for column in extra.columns if column not in volume_columns]
    feature_extras = {
        "crypto_only": None,
        "crypto_volume": extra[volume_columns],
        "crypto_macro": extra[macro_columns],
        "macro_volume": extra,
    }
    hmm_feature_cache: dict[str, pd.DataFrame] = {
        name: build_regime_features(
            closes,
            volatility_window=base_config.feature_volatility_window,
            macro_features=additional,
        )
        for name, additional in feature_extras.items()
    }
    forecast_features = pd.concat(
        [hmm_feature_cache["crypto_only"], extra], axis=1, join="inner"
    ).dropna()
    forecasts, coefficients = walk_forward_macro_forecasts(
        closes,
        forecast_features,
        training_days=730,
        retrain_days=60,
        ridge_penalty=10.0,
        volatility_threshold=0.05,
    )

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
    breakout = build_rule_signals(
        closes,
        family="bollinger_breakout",
        parameters={"window": 40, "width": 1.5, "exit_z": 0.0},
    )

    folds = [
        DevelopmentFold(name, values[0], values[1])
        for name, values in payload["development_folds"].items()
    ]
    regime_cache: dict[tuple[str, int], pd.DataFrame] = {}

    def regimes(feature_set: str, training_days: int) -> pd.DataFrame:
        key = (feature_set, training_days)
        if key not in regime_cache:
            print(f"Fitting {feature_set} HMM with {training_days} training days ...")
            config = replace(
                base_config,
                hmm_training_days=training_days,
                hmm_retrain_days=60,
            )
            regime_cache[key], _ = walk_forward_regime_probabilities(
                hmm_feature_cache[feature_set], config
            )
        return regime_cache[key]

    candidates: list[dict[str, object]] = []
    # Fixed-rule ablations isolate what the added HMM observations change.
    for feature_set in feature_extras:
        candidates.append(
            {
                "feature_set": feature_set,
                "hmm_training_days": 730,
                "rule_pair": "momentum_mean_reversion",
                "confirmation": "none",
                "candidate_type": "ablation",
            }
        )
    # Small combined grid: no tuning on 2025-2026.
    for training_days in (365, 730):
        for rule_pair in ("momentum_mean_reversion", "breakout_flat"):
            for confirmation in ("none", "soft", "agreement"):
                candidates.append(
                    {
                        "feature_set": "macro_volume",
                        "hmm_training_days": training_days,
                        "rule_pair": rule_pair,
                        "confirmation": confirmation,
                        "candidate_type": "combined_grid",
                    }
                )

    candidate_rows: list[dict[str, object]] = []
    fold_rows: list[dict[str, object]] = []
    signal_cache: dict[str, pd.DataFrame] = {}
    portfolio_cache: dict[str, pd.DataFrame] = {}
    best_id = ""
    best_score = float("-inf")
    for number, parameters in enumerate(candidates, start=1):
        candidate_id = f"macro_regime_{number:02d}"
        high = momentum if parameters["rule_pair"] == "momentum_mean_reversion" else breakout
        low = mean_reversion if parameters["rule_pair"] == "momentum_mean_reversion" else None
        confirmation = str(parameters["confirmation"])
        signal = combine_regime_signals(
            regimes(str(parameters["feature_set"]), int(parameters["hmm_training_days"])),
            high,
            low,
            forecasts if confirmation != "none" else None,
            confirmation=confirmation,
        )
        portfolio = backtest_regime_strategy(closes, signal, base_config)
        signal_cache[candidate_id] = signal
        portfolio_cache[candidate_id] = portfolio
        score, fold_frame = score_development_folds(portfolio, folds)
        candidate_rows.append(
            {
                "candidate_id": candidate_id,
                "parameters": json.dumps(parameters, sort_keys=True),
                **parameters,
                **score,
            }
        )
        for record in fold_frame.to_dict(orient="records"):
            fold_rows.append({"candidate_id": candidate_id, **record})
        if parameters["candidate_type"] == "combined_grid" and float(score["robust_score"]) > best_score:
            best_score = float(score["robust_score"])
            best_id = candidate_id

    candidate_frame = pd.DataFrame.from_records(candidate_rows).sort_values(
        "robust_score", ascending=False, kind="stable"
    )
    fold_frame = pd.DataFrame.from_records(fold_rows)
    selected_parameters = next(
        row for row in candidate_rows if row["candidate_id"] == best_id
    )
    (output / "selected_parameters.json").write_text(
        json.dumps(
            {
                key: selected_parameters[key]
                for key in (
                    "candidate_id",
                    "feature_set",
                    "hmm_training_days",
                    "rule_pair",
                    "confirmation",
                    "robust_score",
                )
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    candidate_frame.to_csv(output / "development_candidate_scores.csv", index=False)
    fold_frame.to_csv(output / "development_fold_metrics.csv", index=False)
    pd.DataFrame.from_records(source_rows).to_csv(output / "source_manifest.csv", index=False)
    extra.rename_axis("date").reset_index().to_csv(
        output / "macro_volume_features.csv.gz", index=False, compression="gzip"
    )
    coefficients.to_csv(output / "ridge_coefficients.csv.gz", index=False, compression="gzip")

    final_start, final_end = payload["final_test"]
    final_rows: list[dict[str, object]] = []
    # Report every feature ablation plus the selected combined configuration.
    report_ids = [
        row["candidate_id"]
        for row in candidate_rows
        if row["candidate_type"] == "ablation"
    ] + [best_id]
    for candidate_id in report_ids:
        parameters = next(row for row in candidate_rows if row["candidate_id"] == candidate_id)
        final_rows.append(
            {
                "candidate_id": candidate_id,
                "label": "selected_combined" if candidate_id == best_id else parameters["feature_set"],
                "feature_set": parameters["feature_set"],
                "rule_pair": parameters["rule_pair"],
                "confirmation": parameters["confirmation"],
                **performance_metrics(
                    portfolio_cache[candidate_id], start=final_start, end=final_end
                ),
            }
        )
    # The previously selected breakout remains the non-HMM control.
    breakout_portfolio = backtest_regime_strategy(closes, breakout, base_config)
    final_rows.append(
        {
            "candidate_id": "control",
            "label": "bollinger_breakout_control",
            "feature_set": "none",
            "rule_pair": "breakout_all_regimes",
            "confirmation": "none",
            **performance_metrics(breakout_portfolio, start=final_start, end=final_end),
        }
    )
    final_results = pd.DataFrame.from_records(final_rows)
    final_results.to_csv(output / "final_2025_2026_results.csv", index=False)

    stress_rows: list[dict[str, object]] = []
    for fee in payload["cost_stress_bps"]:
        portfolio = backtest_regime_strategy(
            closes, signal_cache[best_id], replace(base_config, fee_bps=float(fee))
        )
        stress_rows.append(
            {
                "fee_bps": fee,
                **performance_metrics(portfolio, start=final_start, end=final_end),
            }
        )
    pd.DataFrame.from_records(stress_rows).to_csv(output / "cost_stress.csv", index=False)

    selected_signals = signal_cache[best_id]
    selected_signals.to_csv(output / "selected_signals.csv.gz", index=False, compression="gzip")
    portfolio_cache[best_id].rename_axis("date").reset_index().to_csv(
        output / "selected_portfolio.csv.gz", index=False, compression="gzip"
    )

    relationship_columns = [column for column in extra if "_corr_" in column]
    relationship = extra.loc[final_start:final_end, relationship_columns].agg(
        ["median", lambda values: values.lt(0).mean()]
    ).T.reset_index()
    relationship.columns = ["relationship", "median_correlation", "fraction_negative"]
    relationship.to_csv(output / "relationship_summary.csv", index=False)
    coefficient_sample = coefficients.loc[
        pd.to_datetime(coefficients["refit_date"], utc=True) >= pd.Timestamp(final_start, tz="UTC")
    ]
    coefficient_summary = (
        coefficient_sample.groupby(["symbol", "feature"])["standardized_coefficient"]
        .agg(median_coefficient="median", fraction_negative=lambda values: values.lt(0).mean())
        .reset_index()
    )
    coefficient_summary.to_csv(output / "coefficient_summary.csv", index=False)

    annual_rows: list[dict[str, object]] = []
    for label, portfolio in (
        ("selected_combined", portfolio_cache[best_id]),
        ("bollinger_breakout_control", breakout_portfolio),
    ):
        for period, start, end in (
            ("2025", "2025-01-01", "2026-01-01"),
            ("2026_ytd", "2026-01-01", final_end),
        ):
            annual_rows.append(
                {
                    "label": label,
                    "period": period,
                    **performance_metrics(portfolio, start=start, end=end),
                }
            )
    annual = pd.DataFrame.from_records(annual_rows)
    annual.to_csv(output / "calendar_results.csv", index=False)

    displayed = final_results[
        [
            "label",
            "rule_pair",
            "confirmation",
            "total_return",
            "maximum_drawdown",
            "sharpe_ratio_zero_risk_free",
            "average_daily_turnover",
        ]
    ].copy()
    for column in ("total_return", "maximum_drawdown", "average_daily_turnover"):
        displayed[column] = (100.0 * displayed[column]).round(2).astype(str) + "%"
    displayed["sharpe_ratio_zero_risk_free"] = displayed[
        "sharpe_ratio_zero_risk_free"
    ].round(3)
    winner = final_results.loc[final_results["candidate_id"].eq(best_id)].iloc[0]
    annual_display = annual[
        ["label", "period", "total_return", "maximum_drawdown", "sharpe_ratio_zero_risk_free"]
    ].copy()
    for column in ("total_return", "maximum_drawdown"):
        annual_display[column] = (100.0 * annual_display[column]).round(2).astype(str) + "%"
    annual_display["sharpe_ratio_zero_risk_free"] = annual_display[
        "sharpe_ratio_zero_risk_free"
    ].round(3)
    report = f"""# Combined HMM + Macro Relationships + Volume

The current model now combines: (1) a two-state HMM; (2) BTC/ETH return and volatility; (3) lagged S&P 500, Nasdaq, VIX, 10-year-yield, and effective-fed-funds changes; (4) 60-day rolling crypto/macro correlations; and (5) volume surprise plus taker-buy imbalance. It does **not** assume a permanent inverse relationship. Rolling correlations and ridge coefficients are allowed to change sign.

The small grid was selected on six half-year folds from 2022 through 2024. The final period is 2025-01-01 through 2026-09-16. Because 2025 was already viewed in earlier research, this is an extended backtest rather than a pristine unseen holdout.

## 2025–2026 results

{markdown_table(displayed)}

### Calendar split

{markdown_table(annual_display)}

The development-selected combined candidate used `{selected_parameters['feature_set']}`, a {selected_parameters['hmm_training_days']}-day HMM window, `{selected_parameters['rule_pair']}`, and `{selected_parameters['confirmation']}` macro/volume confirmation. It returned **{100 * float(winner['total_return']):.2f}%**, with Sharpe **{float(winner['sharpe_ratio_zero_risk_free']):.3f}** and maximum drawdown **{100 * float(winner['maximum_drawdown']):.2f}%**.

During the final period, median BTC correlations were {float(relationship.loc[relationship['relationship'].eq('BTCUSDT_corr_sp500'), 'median_correlation'].iloc[0]):.3f} with the S&P 500 and {float(relationship.loc[relationship['relationship'].eq('BTCUSDT_corr_dgs10'), 'median_correlation'].iloc[0]):.3f} with 10-year-yield changes. ETH correlations were {float(relationship.loc[relationship['relationship'].eq('ETHUSDT_corr_sp500'), 'median_correlation'].iloc[0]):.3f} and {float(relationship.loc[relationship['relationship'].eq('ETHUSDT_corr_dgs10'), 'median_correlation'].iloc[0]):.3f}, respectively. The equity relationship was positive, while the rate relationship was weakly negative—not a stable blanket inverse relationship.

## How to fine-tune responsibly

1. Tune feature sets and HMM state quality separately from trade-rule thresholds. Reject HMM fits with unstable state labels, tiny state occupancy, or implausibly short persistence.
2. Keep grids small: HMM windows 365/730/1095 days, refits 30/60/90 days, breakout windows 20/40/60, band widths 1.5/2.0/2.5, and confirmation thresholds 0/0.05/0.10 daily volatility.
3. Select by median walk-forward Sharpe with penalties for dispersion, drawdown, turnover, and near-zero exposure. Do not select on the final-period return.
4. Check coefficient-sign stability. A supposed inverse rate relationship that changes sign in most refits is not a dependable trading rule.
5. Require ablations: crypto-only HMM, +volume, +macro relationships, +both, and a no-HMM technical control. The combined model is useful only if it improves consistently after costs.
6. Before deployment, add perpetual funding and an hourly event-driven execution test. Daily closes cannot represent intraday band or grid fills.
"""
    (output / "research_report.md").write_text(report, encoding="utf-8")
    print("\n2025-2026 comparison")
    print(displayed.to_string(index=False))
    print(f"Artifacts -> {output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
