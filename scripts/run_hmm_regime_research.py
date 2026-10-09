#!/usr/bin/env python3
"""Run the walk-forward two-state HMM regime baseline."""

from __future__ import annotations

import argparse
from dataclasses import fields
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
    build_strategy_signals,
    build_target_weights,
    load_daily_futures,
    performance_metrics,
    walk_forward_regime_probabilities,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "hmm_regime.json",
    )
    return parser.parse_args()


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_configuration(path: Path) -> tuple[HMMRegimeConfig, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = {field.name for field in fields(HMMRegimeConfig)}
    values = {name: payload[name] for name in names if name in payload}
    if "symbols" in values:
        values["symbols"] = tuple(str(value).upper() for value in values["symbols"])
    config = HMMRegimeConfig(**values)
    config.validate()
    return config, payload


def load_macro_features(
    payload: dict[str, object], daily_index: pd.DatetimeIndex
) -> pd.DataFrame | None:
    configured = payload.get("macro_features_csv")
    if not configured:
        return None
    path = resolve_path(str(configured))
    date_column = str(payload.get("macro_date_column", "date"))
    columns = [str(value) for value in payload.get("macro_columns", [])]
    if not columns:
        raise ValueError("macro_columns must be provided when macro_features_csv is set")
    frame = pd.read_csv(path, parse_dates=[date_column])
    missing = set(columns).difference(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing macro columns: {sorted(missing)}")
    frame[date_column] = pd.to_datetime(frame[date_column], utc=True).dt.normalize()
    frame = frame.set_index(date_column)[columns].sort_index()
    frame = frame[~frame.index.duplicated(keep="last")].apply(pd.to_numeric, errors="raise")
    lag = int(payload.get("macro_lag_days", 1))
    if lag < 0:
        raise ValueError("macro_lag_days cannot be negative")
    # A one-day default lag handles US-market-close/publication timing relative
    # to the crypto UTC close.  No-observation weekends represent no new macro
    # release and are encoded as zero changes/returns.
    return frame.shift(lag).reindex(daily_index).fillna(0.0)


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])


def write_report(
    output: Path,
    summary: pd.DataFrame,
    signals: pd.DataFrame,
    diagnostics: pd.DataFrame,
    attribution: pd.DataFrame,
    macro_enabled: bool,
) -> None:
    displayed = summary[
        [
            "period",
            "observations",
            "total_return",
            "maximum_drawdown",
            "sharpe_ratio_zero_risk_free",
            "average_gross_exposure",
            "btc_benchmark_return",
            "equal_weight_benchmark_return",
        ]
    ].copy()
    for column in (
        "total_return",
        "maximum_drawdown",
        "average_gross_exposure",
        "btc_benchmark_return",
        "equal_weight_benchmark_return",
    ):
        displayed[column] = (100.0 * displayed[column].astype(float)).round(2).astype(str) + "%"
    displayed["sharpe_ratio_zero_risk_free"] = displayed[
        "sharpe_ratio_zero_risk_free"
    ].astype(float).round(3)

    daily_regime = signals.drop_duplicates("date").set_index("date")["regime"]
    regime_share = daily_regime.value_counts(normalize=True)
    high_share = 100.0 * float(regime_share.get("high_volatility", 0.0))
    low_share = 100.0 * float(regime_share.get("low_volatility", 0.0))
    high_persistence = float(diagnostics["high_state_persistence"].mean())
    low_persistence = float(diagnostics["low_state_persistence"].mean())
    macro_note = (
        "Configured lagged macro features were included."
        if macro_enabled
        else "This first baseline uses only BTC and ETH return/volatility features; no macro data was supplied."
    )
    attribution_display = attribution.copy()
    for column in ("compounded_return", "cost_return"):
        attribution_display[column] = (
            100.0 * attribution_display[column].astype(float)
        ).round(2).astype(str) + "%"
    report = f"""# Two-State HMM Regime Baseline

This is a research backtest, not a live-trading recommendation. {macro_note}

## Baseline design

- One shared two-state diagonal-Gaussian HMM is refit every 30 days on at most two years of trailing observations.
- States are relabeled after every fit: the state with greater BTC/ETH return variance is **high volatility**. Filtered probabilities use only data known by that close.
- High volatility: trade the majority direction of MACD(12,26,9), SMA(20/100), and RSI(14) above 55 or below 45. Two of three votes are required.
- Low volatility: enter long below the 20-day lower Bollinger Band or short above the upper band (2 standard deviations), then exit near the rolling mean.
- BTC and ETH signals are independent. The portfolio can be long one and short the other simultaneously, but each instrument has one net position.
- Signals formed at a daily close earn returns starting the next day. Sizing is inverse-volatility, capped at 50% per asset and 100% gross, then scaled down to a 20% annual volatility target.
- Trading cost is 10 bps per unit of one-way turnover. Funding, borrow constraints, spread history, liquidation, and market impact are not modeled.

The fitted regime was high-volatility on {high_share:.1f}% of classified days and low-volatility on {low_share:.1f}%. Mean estimated one-day persistence was {high_persistence:.3f} for high vol and {low_persistence:.3f} for low vol.

## Results

{markdown_table(displayed)}

Returns attributed to the regime that generated the prior close's applied position:

{markdown_table(attribution_display)}

## How to select parameters without fooling yourself

1. Freeze the HMM structure first: compare 2 versus 3 states with walk-forward log likelihood, state stability, and minimum state occupancy—not strategy P&L. Keep two states unless a third state is persistent and interpretable across folds.
2. Tune only a small, economically sensible grid on the development period. Suggested tests: HMM training 365/730/1095 days; refit 14/30/60 days; SMA 10/50, 20/100, 50/200; Bollinger window 20/40 and width 1.5/2.0/2.5; momentum votes 2/3 or 3/3.
3. Use anchored or rolling walk-forward folds and rank configurations by median out-of-sample Sharpe, drawdown, turnover, and consistency across BTC and ETH. Do not choose on total return alone.
4. Leave 2024–2025 as untouched holdout while selecting on earlier folds. Apply a deflated-Sharpe or multiple-testing haircut when many configurations are tried.
5. Add macro variables as an ablation, not all at once. Start with stationary, lagged features such as S&P 500 return, VIX change, and 10-year-yield change. Retain a feature only if it improves several walk-forward folds after costs and does not make state labels unstable.
6. Stress costs to 15–30 bps and add perpetual funding before considering deployment. Re-run with one-bar and one-day extra execution delays to expose timing sensitivity.

## Reading this baseline

A weak or negative holdout result is useful evidence against these exact default rules; it is not a prompt to tune on the holdout. The next defensible experiment is a small development-only grid plus a no-HMM control (momentum-only and Bollinger-only) so the incremental value of regime switching is measurable.
"""
    (output / "research_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    config, payload = load_configuration(args.config)
    data_directory = resolve_path(str(payload["market_data_directory"]))
    output = resolve_path(str(payload["output_directory"]))
    output.mkdir(parents=True, exist_ok=True)

    closes = []
    for symbol in config.symbols:
        path = data_directory / f"{symbol}_1h.csv.gz"
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}; prepare the futures candles first")
        daily = load_daily_futures(path)
        closes.append(daily["close"].rename(symbol))
    close_frame = pd.concat(closes, axis=1, join="inner").dropna().sort_index()
    macro = load_macro_features(payload, close_frame.index)
    features = build_regime_features(
        close_frame,
        volatility_window=config.feature_volatility_window,
        macro_features=macro,
    )
    regimes, diagnostics = walk_forward_regime_probabilities(features, config)
    signals = build_strategy_signals(close_frame, regimes, config)
    target_weights = build_target_weights(close_frame, signals, config)
    portfolio = backtest_regime_strategy(close_frame, signals, config)

    summaries: list[dict[str, object]] = []
    periods = payload.get("periods", {})
    for name, boundaries in periods.items():
        start, end = boundaries
        metrics = performance_metrics(portfolio, start=str(start), end=str(end))
        summaries.append(
            {
                "period": name,
                "requested_start": start,
                "end_exclusive": end,
                **metrics,
            }
        )
        print(
            f"{name:11} observations={metrics['observations']:4} "
            f"return={100 * float(metrics['total_return']):8.3f}% "
            f"maxDD={100 * float(metrics['maximum_drawdown']):8.3f}% "
            f"Sharpe={float(metrics['sharpe_ratio_zero_risk_free']):6.3f}"
        )

    summary = pd.DataFrame.from_records(summaries)
    daily_strategy = signals.drop_duplicates("date").set_index("date")[
        ["regime", "strategy"]
    ].shift(1)
    attributed = portfolio.join(daily_strategy)
    attribution_records: list[dict[str, object]] = []
    for period, boundaries in periods.items():
        start, end = (pd.Timestamp(value, tz="UTC") for value in boundaries)
        sample = attributed.loc[
            (attributed.index >= start) & (attributed.index < end)
        ]
        for (regime, strategy), group in sample.groupby(["regime", "strategy"]):
            attribution_records.append(
                {
                    "period": period,
                    "regime": regime,
                    "strategy": strategy,
                    "days": len(group),
                    "compounded_return": float((1.0 + group["net_return"]).prod() - 1.0),
                    "cost_return": float(group["transaction_cost_return"].sum()),
                }
            )
    attribution = pd.DataFrame.from_records(attribution_records)
    signal_output = signals.merge(
        target_weights.rename(columns=lambda value: f"target_weight_{value}")
        .rename_axis("date")
        .reset_index(),
        on="date",
        how="left",
    )
    signal_output["target_weight"] = signal_output.apply(
        lambda row: row[f"target_weight_{row['symbol']}"], axis=1
    )
    signal_output = signal_output.drop(
        columns=[f"target_weight_{symbol}" for symbol in config.symbols]
    )
    regimes.rename_axis("date").reset_index().to_csv(output / "regimes.csv", index=False)
    diagnostics.to_csv(output / "hmm_refits.csv", index=False)
    signal_output.to_csv(output / "signals.csv", index=False)
    portfolio.rename_axis("date").reset_index().to_csv(
        output / "portfolio.csv.gz", index=False, compression="gzip"
    )
    summary.to_csv(output / "summary.csv", index=False)
    attribution.to_csv(output / "regime_attribution.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n", encoding="utf-8"
    )
    write_report(
        output, summary, signal_output, diagnostics, attribution, macro is not None
    )
    print(f"Research artifacts -> {output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
