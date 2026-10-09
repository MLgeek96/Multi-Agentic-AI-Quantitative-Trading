from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from build_sixcoin_validation_report import (
    BASE_SLIPPAGE_PER_SIDE,
    ENSEMBLE_MODELS,
    FEE_PER_SIDE,
    SYMBOLS,
    VALIDATION_END,
    VALIDATION_START,
    build_daily_market,
    build_regime_gate,
    build_signal_file,
    load_funding,
    make_allocations,
    portfolio_path,
    summarize_path,
    trade_positions,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LONG_SHORT_ROOT = PROJECT_ROOT / "freqtrade/validation_runs/2026_sixcoin"
SCENARIO_ROOT = PROJECT_ROOT / "freqtrade/validation_runs/2026_scenarios"
OUTPUT_ROOT = PROJECT_ROOT / "freqtrade/reports/2026_execution_scenarios"
BASELINE_OUTPUT_ROOT = OUTPUT_ROOT
NATIVE_RESULTS_ROOT = (
    PROJECT_ROOT / "freqtrade/validation_runs/2026_native_history_scenarios"
)
NATIVE_OUTPUT_ROOT = PROJECT_ROOT / "freqtrade/reports/2026_native_history_scenarios"
NATIVE_HISTORY = False

NATIVE_TRAIN_DAYS = {
    "futures_long_short": {
        "BTC": 2150,
        "ETH": 2150,
        "SOL": 1893,
        "XRP": 2145,
        "BNB": 2110,
        "DOGE": 1958,
    },
    "futures_long_only": {
        "BTC": 2150,
        "ETH": 2150,
        "SOL": 1893,
        "XRP": 2145,
        "BNB": 2110,
        "DOGE": 1958,
    },
    "spot_long_only": {
        "BTC": 2150,
        "ETH": 2150,
        "SOL": 1927,
        "XRP": 2150,
        "BNB": 2150,
        "DOGE": 2150,
    },
}

MODEL_SPECS = {
    "Bollinger 40d": ("bollinger", "bollinger/*.zip"),
    "RNN static": ("rnn", "rnn_static-*.zip"),
    "GRU static": ("gru", "gru_static-*.zip"),
    "LSTM static": ("lstm", "lstm_static-*.zip"),
    "Transformer static": ("transformer", "transformer_static-*.zip"),
    "HMM trend": ("hmm_trend", "hmm_trend-*.zip"),
    "HMM switching": ("hmm_switching", "hmm_regime-*.zip"),
    "HMM defensive": ("hmm_defensive", "hmm_defensive-*.zip"),
    "HMM trend defensive": (
        "hmm_trend_defensive",
        "hmm_trend_defensive-*.zip",
    ),
    "HMM + LSTM static": ("hmm_lstm", "hmm_lstm_static-*.zip"),
}

MODE_SPECS = {
    "futures_long_short": {
        "instrument": "Binance USD-M perpetual futures",
        "results_root": LONG_SHORT_ROOT,
        "data_root": PROJECT_ROOT / "freqtrade/user_data/data/binanceusdm/futures",
        "regime_root": PROJECT_ROOT / "freqtrade/user_data/regime_models",
        "funding": True,
    },
    "futures_long_only": {
        "instrument": "Binance USD-M perpetual futures",
        "results_root": SCENARIO_ROOT / "futures_long_only",
        "data_root": PROJECT_ROOT / "freqtrade/user_data/data/binanceusdm/futures",
        "regime_root": PROJECT_ROOT / "freqtrade/user_data/regime_models",
        "funding": True,
    },
    "spot_long_only": {
        "instrument": "Binance spot",
        "results_root": SCENARIO_ROOT / "spot_long_only",
        "data_root": PROJECT_ROOT / "freqtrade/user_data/data/binance",
        "regime_root": PROJECT_ROOT / "freqtrade/user_data/regime_models_spot",
        "funding": False,
    },
}


def latest(root: Path, pattern: str) -> Path:
    matches = sorted(root.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No backtest archive matching {root / pattern}")
    return matches[-1]


def result_archive(mode: str, label: str) -> Path:
    slug, legacy_pattern = MODEL_SPECS[label]
    root = MODE_SPECS[mode]["results_root"]
    if mode == "futures_long_short" and not NATIVE_HISTORY:
        return latest(root, legacy_pattern)
    return latest(root / slug, "*.zip")


def configure_experiment(experiment: str) -> None:
    global NATIVE_HISTORY, OUTPUT_ROOT
    if experiment != "native-history":
        return
    NATIVE_HISTORY = True
    OUTPUT_ROOT = NATIVE_OUTPUT_ROOT
    for mode, spec in MODE_SPECS.items():
        spec["results_root"] = NATIVE_RESULTS_ROOT / mode
    MODE_SPECS["futures_long_short"]["regime_root"] = (
        PROJECT_ROOT / "freqtrade/user_data/regime_models_full_history"
    )
    MODE_SPECS["futures_long_only"]["regime_root"] = (
        PROJECT_ROOT / "freqtrade/user_data/regime_models_full_history"
    )
    MODE_SPECS["spot_long_only"]["regime_root"] = (
        PROJECT_ROOT / "freqtrade/user_data/regime_models_spot_full_history"
    )


def read_archive(path: Path) -> tuple[str, dict]:
    with zipfile.ZipFile(path) as archive:
        members = [
            name
            for name in archive.namelist()
            if name.endswith(".json") and not name.endswith("_config.json")
        ]
        if len(members) != 1:
            raise ValueError(f"Expected one result JSON in {path}, got {members}")
        payload = json.loads(archive.read(members[0]))
    strategy, result = next(iter(payload["strategy"].items()))
    return strategy, result


def load_mode_results(mode: str) -> tuple[dict[str, dict], list[dict]]:
    results: dict[str, dict] = {}
    rows: list[dict] = []
    for label in MODEL_SPECS:
        archive = result_archive(mode, label)
        strategy, result = read_archive(archive)
        results[label] = result
        rows.append(
            {
                "execution_mode": mode,
                "instrument": MODE_SPECS[mode]["instrument"],
                "model": label,
                "strategy": strategy,
                "trades": int(result["total_trades"]),
                "long_trades": int(result["trade_count_long"]),
                "short_trades": int(result["trade_count_short"]),
                "win_rate_pct": float(result["winrate"]) * 100,
                "total_return_pct": float(result["profit_total"]) * 100,
                "maximum_drawdown_pct": float(result["max_relative_drawdown"]) * 100,
                "closed_trade_sharpe_zero_rf": float(result["sharpe"]),
                "profit_factor": float(result["profit_factor"]),
                "mean_profit_p_value": float(result["p_value"]),
                "validation_start": result["backtest_start"],
                "validation_end": result["backtest_end"],
                "fee_bps_per_side": FEE_PER_SIDE * 10_000,
                "slippage_included": False,
                "funding_included": False,
                "archive": str(archive.relative_to(PROJECT_ROOT)),
            }
        )
    return results, rows


def load_hourly(mode: str) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    data_root = MODE_SPECS[mode]["data_root"]
    suffix = "_USDT_USDT-1h-futures.feather" if mode != "spot_long_only" else "_USDT-1h.feather"
    for symbol in SYMBOLS:
        frame = pd.read_feather(data_root / f"{symbol}{suffix}")
        frame["date"] = pd.to_datetime(frame["date"], utc=True)
        frames[symbol] = frame.sort_values("date").reset_index(drop=True)
    return frames


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    view = frame[columns].copy()
    for column in view.select_dtypes(include=["float"]).columns:
        view[column] = view[column].map(
            lambda value: "N/A" if pd.isna(value) else f"{value:.2f}"
        )
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in view.to_numpy()]
    return "\n".join([header, divider, *rows])


def write_report(
    standalone: pd.DataFrame,
    best: pd.DataFrame,
    portfolios: pd.DataFrame,
) -> None:
    selected = standalone[
        standalone["model"].isin(
            [
                "Bollinger 40d",
                "LSTM static",
                "HMM trend",
                "HMM switching",
                "HMM + LSTM static",
            ]
        )
    ].sort_values(["execution_mode", "model"])
    training_design = (
        "Neural and HMM models use each coin's own available history through "
        "2025-12-31. After the 1,000-hour feature warm-up, the neural fitting "
        "windows span 1,893-2,150 days for futures and 1,927-2,150 days for "
        "spot. No 2026 retraining is allowed in the reported holdout."
        if NATIVE_HISTORY
        else "Neural models use a single 2025-01-01 through 2025-12-31 fit; "
        "no 2026 retraining is allowed in the reported holdout."
    )
    comparison_section = ""
    if NATIVE_HISTORY:
        model_comparison = pd.read_csv(OUTPUT_ROOT / "training_window_comparison.csv")
        model_comparison = model_comparison[
            model_comparison["model"].isin(
                [
                    "RNN static",
                    "GRU static",
                    "LSTM static",
                    "Transformer static",
                    "HMM + LSTM static",
                ]
            )
        ].sort_values(["execution_mode", "model"])
        variable_comparison = pd.read_csv(
            OUTPUT_ROOT / "portfolio_training_window_comparison.csv"
        )
        variable_comparison = variable_comparison[
            variable_comparison["portfolio"] == "Ensemble variable"
        ].sort_values("execution_mode")
        comparison_section = f"""## Native-history versus 2025-only training

Positive return and Sharpe deltas favor native-history training. Negative maximum-drawdown deltas mean a smaller drawdown.

{markdown_table(model_comparison, ['execution_mode', 'model', 'total_return_pct_2025_only', 'total_return_pct_native_history', 'total_return_pct_delta_native_minus_2025_only', 'closed_trade_sharpe_zero_rf_delta_native_minus_2025_only'])}

### Cost-aware variable-weight portfolio

{markdown_table(variable_comparison, ['execution_mode', 'return_pct_2025_only', 'return_pct_native_history', 'return_pct_delta_native_minus_2025_only', 'sharpe_2025_only', 'sharpe_native_history', 'max_drawdown_pct_native_history'])}

The complete comparisons are in `training_window_comparison.csv` and `portfolio_training_window_comparison.csv`.

"""
    report = f"""# Spot and futures execution-scenario validation

## Test design

- Frozen selection boundary: 2025-12-31. {training_design}
- Holdout: 2026-01-01 through 2026-09-17 23:00 UTC. September stops at the latest common verified Binance candle, so this is not a complete January-through-September calendar period.
- Coins: BTC, ETH, SOL, XRP, BNB, and DOGE, all at 1-hour strategy frequency.
- Execution cases: futures long/short, futures long-only, and spot long-only. Spot uses independently downloaded spot candles, spot-trained sequence models, and separately fitted spot HMMs.
- Standalone Freqtrade rows include 10 bps per-side fees. They do not include slippage or funding; those are handled in the daily portfolio layer.
- Portfolio rows include 10 bps fees and 5 bps modeled one-way slippage. Observed Binance funding is applied only to the two futures modes; spot has no funding and cannot short.

## Core model comparison

{markdown_table(selected, ['execution_mode', 'model', 'trades', 'long_trades', 'short_trades', 'total_return_pct', 'maximum_drawdown_pct', 'closed_trade_sharpe_zero_rf'])}

## Best standalone Sharpe in each execution mode

{markdown_table(best, ['execution_mode', 'model', 'trades', 'total_return_pct', 'maximum_drawdown_pct', 'closed_trade_sharpe_zero_rf'])}

## Allocation and cost scenarios

{markdown_table(portfolios, ['execution_mode', 'portfolio', 'return_pct', 'sharpe', 'max_drawdown_pct', 'avg_gross_exposure_pct', 'average_daily_turnover_pct'])}

{comparison_section}## Interpretation

- Futures long/short is the only valid short-selling case. Spot and the futures long-only control both clamp all short entries to zero.
- The raw Freqtrade comparison isolates strategy behavior after exchange fees. The portfolio comparison is the relevant cost-aware allocation validation because it adds modeled slippage and, for futures, observed funding.
- Spot and futures long-only can look close for slow Bollinger trades, but they are not duplicates: the candles, trained neural weights, HMM parameters, and funding treatment differ.
- Do not tune after reading this holdout. A rule change now needs a later untouched test period.
"""
    (OUTPUT_ROOT / "validation_report.md").write_text(report, encoding="utf-8")


def write_baseline_comparisons(
    standalone: pd.DataFrame, portfolios: pd.DataFrame
) -> None:
    if not NATIVE_HISTORY:
        return
    baseline_standalone = pd.read_csv(
        BASELINE_OUTPUT_ROOT / "standalone_execution_mode_results.csv"
    )
    metrics = [
        "trades",
        "total_return_pct",
        "maximum_drawdown_pct",
        "closed_trade_sharpe_zero_rf",
    ]
    comparison = baseline_standalone[
        ["execution_mode", "model", *metrics]
    ].merge(
        standalone[["execution_mode", "model", *metrics]],
        on=["execution_mode", "model"],
        suffixes=("_2025_only", "_native_history"),
        validate="one_to_one",
    )
    # Freqtrade emits -100 as a sentinel when a closed-trade Sharpe estimate is
    # not meaningful (for example, a single-trade result). Do not report a
    # fabricated 100-point improvement against that sentinel.
    for suffix in ("2025_only", "native_history"):
        sharpe_column = f"closed_trade_sharpe_zero_rf_{suffix}"
        comparison.loc[comparison[sharpe_column] <= -99, sharpe_column] = np.nan
    for metric in metrics:
        comparison[f"{metric}_delta_native_minus_2025_only"] = (
            comparison[f"{metric}_native_history"]
            - comparison[f"{metric}_2025_only"]
        )
    comparison.to_csv(OUTPUT_ROOT / "training_window_comparison.csv", index=False)

    baseline_portfolios = pd.read_csv(
        BASELINE_OUTPUT_ROOT / "portfolio_execution_mode_results.csv"
    )
    portfolio_metrics = ["return_pct", "sharpe", "max_drawdown_pct"]
    portfolio_comparison = baseline_portfolios[
        ["execution_mode", "portfolio", *portfolio_metrics]
    ].merge(
        portfolios[["execution_mode", "portfolio", *portfolio_metrics]],
        on=["execution_mode", "portfolio"],
        suffixes=("_2025_only", "_native_history"),
        validate="one_to_one",
    )
    for metric in portfolio_metrics:
        portfolio_comparison[f"{metric}_delta_native_minus_2025_only"] = (
            portfolio_comparison[f"{metric}_native_history"]
            - portfolio_comparison[f"{metric}_2025_only"]
        )
    portfolio_comparison.to_csv(
        OUTPUT_ROOT / "portfolio_training_window_comparison.csv", index=False
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build execution-scenario reports.")
    parser.add_argument(
        "--experiment",
        choices=("2025-only", "native-history"),
        default="2025-only",
    )
    args = parser.parse_args()
    configure_experiment(args.experiment)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range(VALIDATION_START, VALIDATION_END, freq="1D")
    all_standalone: list[dict] = []
    all_portfolios: list[dict] = []
    signal_panels: list[pd.DataFrame] = []
    path_panels: list[pd.DataFrame] = []
    weight_panels: list[pd.DataFrame] = []

    _, futures_funding = load_funding(
        PROJECT_ROOT / "freqtrade/reports/2026_sixcoin_validation", refresh=False
    )

    for mode in MODE_SPECS:
        results, rows = load_mode_results(mode)
        all_standalone.extend(rows)
        hourly = load_hourly(mode)
        _, daily_returns = build_daily_market(hourly)
        positions = trade_positions(results, dates)
        regimes = build_regime_gate(hourly, MODE_SPECS[mode]["regime_root"], dates)
        allocations, diagnostics = make_allocations(positions, regimes, daily_returns, dates)
        daily_funding = (
            futures_funding
            if MODE_SPECS[mode]["funding"]
            else pd.DataFrame(0.0, index=dates, columns=SYMBOLS)
        )

        for name, weights in allocations.items():
            path = portfolio_path(
                weights, daily_returns, daily_funding, BASE_SLIPPAGE_PER_SIDE
            )
            summary = summarize_path(name, path, BASE_SLIPPAGE_PER_SIDE)
            summary.update(
                {
                    "execution_mode": mode,
                    "funding_included": bool(MODE_SPECS[mode]["funding"]),
                    "average_daily_turnover_pct": path["turnover"].mean() * 100,
                }
            )
            all_portfolios.append(summary)

            path_panel = path.copy()
            path_panel.insert(0, "portfolio", name)
            path_panel.insert(0, "execution_mode", mode)
            path_panel.insert(0, "date", path_panel.index)
            path_panels.append(path_panel.reset_index(drop=True))

            weight_panel = weights.copy()
            weight_panel.insert(0, "portfolio", name)
            weight_panel.insert(0, "execution_mode", mode)
            weight_panel.insert(0, "date", weight_panel.index)
            weight_panels.append(weight_panel.reset_index(drop=True))

        signals = build_signal_file(positions, regimes, diagnostics, allocations)
        signals.insert(0, "execution_mode", mode)
        signal_panels.append(signals)

    standalone = pd.DataFrame(all_standalone).sort_values(
        ["execution_mode", "closed_trade_sharpe_zero_rf"], ascending=[True, False]
    )
    best = standalone.loc[
        standalone.groupby("execution_mode")["closed_trade_sharpe_zero_rf"].idxmax()
    ].sort_values("execution_mode")
    portfolios = pd.DataFrame(all_portfolios).sort_values(
        ["execution_mode", "sharpe"], ascending=[True, False]
    )

    standalone.to_csv(OUTPUT_ROOT / "standalone_execution_mode_results.csv", index=False)
    best.to_csv(OUTPUT_ROOT / "best_standalone_by_execution_mode.csv", index=False)
    portfolios.to_csv(OUTPUT_ROOT / "portfolio_execution_mode_results.csv", index=False)
    pd.concat(signal_panels, ignore_index=True).to_csv(
        OUTPUT_ROOT / "daily_signals_all_execution_modes.csv", index=False
    )
    pd.concat(path_panels, ignore_index=True).to_csv(
        OUTPUT_ROOT / "daily_portfolio_paths_all_execution_modes.csv", index=False
    )
    pd.concat(weight_panels, ignore_index=True).to_csv(
        OUTPUT_ROOT / "daily_target_weights_all_execution_modes.csv", index=False
    )
    write_baseline_comparisons(standalone, portfolios)

    manifest = {
        "selection_cutoff": "2025-12-31",
        "neural_train_start": (
            "pair-specific native usable history" if NATIVE_HISTORY else "2025-01-01"
        ),
        "neural_train_end_exclusive": "2026-01-01",
        "neural_train_days_by_execution_mode_and_symbol": (
            NATIVE_TRAIN_DAYS if NATIVE_HISTORY else None
        ),
        "validation_start": str(dates.min()),
        "validation_end": str(dates.max()),
        "symbols": SYMBOLS,
        "execution_modes": list(MODE_SPECS),
        "fee_per_side": FEE_PER_SIDE,
        "portfolio_slippage_per_side": BASE_SLIPPAGE_PER_SIDE,
        "funding": {
            "futures_long_short": "observed Binance USD-M funding events",
            "futures_long_only": "observed Binance USD-M funding events",
            "spot_long_only": "not applicable",
        },
        "result_archives": {
            mode: {label: str(result_archive(mode, label).relative_to(PROJECT_ROOT)) for label in MODEL_SPECS}
            for mode in MODE_SPECS
        },
    }
    (OUTPUT_ROOT / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    write_report(standalone, best, portfolios)

    print("Standalone best by execution mode")
    print(
        best[
            [
                "execution_mode",
                "model",
                "trades",
                "long_trades",
                "short_trades",
                "total_return_pct",
                "maximum_drawdown_pct",
                "closed_trade_sharpe_zero_rf",
            ]
        ].to_string(index=False)
    )
    print("\nPortfolio results")
    print(
        portfolios[
            [
                "execution_mode",
                "portfolio",
                "return_pct",
                "sharpe",
                "max_drawdown_pct",
                "average_daily_turnover_pct",
            ]
        ].to_string(index=False)
    )
    print(f"\nWrote {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
