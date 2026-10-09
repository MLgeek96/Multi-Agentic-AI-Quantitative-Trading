#!/usr/bin/env python3
"""Walk-forward backtest for the adaptive daily portfolio selected in the brief."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crypto_quant.daily_portfolio import (  # noqa: E402
    backtest_daily_portfolio,
    calculate_portfolio_kpis,
    load_daily_config,
)


PERIODS = {
    "development": ("2022-01-01", "2024-01-01"),
    "validation": ("2024-01-01", "2026-08-01"),
}
MODEL_VARIANTS = ("adaptive_trend", "trend_bb_rsi")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "daily_portfolio.json",
    )
    parser.add_argument(
        "--market-data",
        type=Path,
        default=PROJECT_ROOT / "live" / "market_data",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "reports" / "daily_portfolio",
    )
    return parser.parse_args()


def load_closes(directory: Path, symbols: tuple[str, ...]) -> pd.DataFrame:
    series = []
    for symbol in symbols:
        path = directory / f"{symbol}_1d.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}; run scripts/run_daily_portfolio.py first")
        frame = pd.read_csv(path, parse_dates=["open_time"])
        frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True)
        series.append(frame.set_index("open_time")["close"].astype(float).rename(symbol))
    return pd.concat(series, axis=1, join="inner").dropna().sort_index()


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
    config = load_daily_config(args.config)
    closes = load_closes(args.market_data, config.symbols)
    args.output.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, object]] = []
    collections: dict[str, list[pd.DataFrame]] = {
        "signals": [],
        "portfolio": [],
        "orders": [],
        "trades": [],
    }
    for model in MODEL_VARIANTS:
        model_config = replace(config, signal_model=model)
        for period, (start, end) in PERIODS.items():
            signals, portfolio, orders, trades = backtest_daily_portfolio(
                closes, model_config, start=start, end=end
            )
            if portfolio.empty:
                raise ValueError(
                    f"No observations produced for {model}/{period}; fetch more history"
                )
            metrics = calculate_portfolio_kpis(
                portfolio, trades, initial_equity=model_config.initial_equity
            )
            summaries.append(
                {
                    "model": model,
                    "period": period,
                    "requested_start": start,
                    "actual_start": portfolio["date"].iloc[0],
                    "end_exclusive": end,
                    **metrics,
                }
            )
            for name, frame in (
                ("signals", signals),
                ("portfolio", portfolio),
                ("orders", orders),
                ("trades", trades),
            ):
                if not frame.empty:
                    labeled = frame.copy()
                    labeled.insert(0, "period", period)
                    labeled.insert(0, "model", model)
                    collections[name].append(labeled)
            print(
                f"{model:16} {period:11} observations={metrics['observations']:4} "
                f"return={100 * float(metrics['total_return']):8.3f}% "
                f"maxDD={100 * float(metrics['maximum_drawdown']):8.3f}% "
                f"Sharpe={float(metrics['sharpe_ratio_zero_risk_free']):6.3f}"
            )

    summary = pd.DataFrame.from_records(summaries)
    summary.to_csv(args.output / "summary.csv", index=False)
    for name, frames in collections.items():
        if frames:
            pd.concat(frames, ignore_index=True).to_csv(args.output / f"{name}.csv", index=False)
    displayed = summary[
        [
            "period",
            "model",
            "observations",
            "total_return",
            "maximum_drawdown",
            "sharpe_ratio_zero_risk_free",
            "btc_benchmark_return",
            "equal_weight_benchmark_return",
            "closed_round_trips",
        ]
    ].copy()
    for column in (
        "total_return",
        "maximum_drawdown",
        "btc_benchmark_return",
        "equal_weight_benchmark_return",
    ):
        displayed[column] = (100 * displayed[column]).round(3).astype(str) + "%"
    validation = summary.loc[summary["period"].eq("validation")].set_index("model")
    baseline_return = 100 * float(validation.loc["adaptive_trend", "total_return"])
    enhanced_return = 100 * float(validation.loc["trend_bb_rsi", "total_return"])
    baseline_drawdown = 100 * float(validation.loc["adaptive_trend", "maximum_drawdown"])
    enhanced_drawdown = 100 * float(validation.loc["trend_bb_rsi", "maximum_drawdown"])
    interpretation = (
        f"The Bollinger/RSI filter changed validation return from {baseline_return:.2f}% "
        f"to {enhanced_return:.2f}% and maximum drawdown from {baseline_drawdown:.2f}% "
        f"to {enhanced_drawdown:.2f}%. "
    )
    if enhanced_return > baseline_return:
        interpretation += "It improved return in this comparison, but still requires a frozen-rule forward test."
    else:
        interpretation += (
            "It did not improve return, so it remains an experimental variant rather than the live default."
        )
    report = f"""# BTC/ETH Daily Portfolio — Walk-Forward Comparison

Both models re-select the SMA pair independently for BTC and ETH every day using only trailing observations. The baseline requires a positive trend and non-negative trailing training Sharpe. `trend_bb_rsi` adds fixed confirmation gates: RSI(14) must be 45–70 and price must remain inside its 20-day, two-standard-deviation Bollinger Bands. Active assets receive capped inverse-volatility weights, then the portfolio is scaled to its annualized volatility target.

{markdown_table(displayed)}

## Interpretation

{interpretation}

This walk-forward comparison includes the configured 10 bps turnover charge. Indicator thresholds are standard fixed values rather than parameters selected on validation performance. It does not include taxes, exchange outages, bid/ask spread history, or market impact. The October 2026 evaluation remains untouched and is logged separately by the daily runner.
"""
    (args.output / "research_report.md").write_text(report, encoding="utf-8")
    (args.output / "summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Research artifacts -> {args.output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
