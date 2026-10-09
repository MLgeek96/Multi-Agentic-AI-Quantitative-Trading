#!/usr/bin/env python3
"""Run the pattern/momentum strategy suite and write reproducible research artifacts."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crypto_quant import (  # noqa: E402
    DEFAULT_CONFIGS,
    backtest,
    build_candidates,
    build_structure_bars,
    load_ohlcv,
    performance_metrics,
    validate_audit_log,
)


PERIODS = {
    "development": ("2020-01-01", "2024-01-01"),
    "holdout": ("2024-01-01", "2026-01-01"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument(
        "--markets", nargs="+", choices=["spot", "usdt_futures"], default=["usdt_futures"]
    )
    parser.add_argument(
        "--strategies", nargs="+", choices=sorted(DEFAULT_CONFIGS), default=sorted(DEFAULT_CONFIGS)
    )
    parser.add_argument("--initial-equity", type=float, default=100_000.0)
    parser.add_argument("--risk-pct", type=float, default=1.0, help="Maximum equity risk per trade")
    parser.add_argument("--fee-bps", type=float, default=4.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "reports" / "pattern_momentum")
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


def write_report(output: Path, summary: pd.DataFrame, candidate_summary: pd.DataFrame) -> None:
    holdout = summary.loc[summary["period"].eq("holdout")].copy()
    robust = holdout.loc[
        holdout["trades"].ge(20)
        & holdout["total_return_pct"].gt(0)
        & holdout["sharpe"].gt(0)
        & holdout["profit_factor"].gt(1)
    ]
    positive = holdout.loc[holdout["total_return_pct"].gt(0), ["market", "symbol", "strategy", "trades"]]
    if robust.empty:
        robustness_note = (
            "None of the hypotheses passes a modest robustness screen of at least 20 holdout trades, "
            "positive return, positive Sharpe, and profit factor above 1."
        )
    else:
        robustness_note = (
            f"{len(robust)} hypothesis row(s) pass the stated robustness screen; they still require "
            "walk-forward and funding/liquidity validation."
        )
    if positive.empty:
        positive_note = "No holdout row was profitable after modeled fees and slippage."
    else:
        descriptions = [
            f"{row.market} {row.symbol} {row.strategy} ({int(row.trades)} trades)"
            for row in positive.itertuples(index=False)
        ]
        positive_note = "Positive holdout rows were: " + "; ".join(descriptions) + "."
    displayed = holdout[
        [
            "market",
            "symbol",
            "strategy",
            "trades",
            "total_return_pct",
            "max_drawdown_pct",
            "sharpe",
            "profit_factor",
            "expectancy_r",
        ]
    ]
    report = f"""# Pattern + Momentum Strategy Research

Generated from the checked Binance candles in this workspace. This is a research artifact, not financial advice or a live-trading system.

## Design

- Structural timeframe: completed 4-hour candles resampled from 1-hour data.
- Execution timeframe: 1-hour, with signals filled at the next available open.
- Strategies: double-top/bottom reversal, ascending/descending triangle breakout, bull/bear flag continuation.
- Confirmation: volume greater than 1.5x the prior 20-bar average, RSI exhaustion/divergence gate, and MACD direction plus slope.
- Risk: logical pattern invalidation stop, projected pattern target, minimum 3.0 reward/risk at the actual modeled fill, and at most 1% account risk.
- Management: breakeven at +1R; from +2R, a stop retaining 33% of maximum favorable excursion; one position per strategy; 25% drawdown kill-switch.
- Costs: configured fee and slippage on both entry and exit. Same-bar stop/target collisions resolve to the stop.

## Holdout results (2024-01-01 through 2025-12-31)

{markdown_table(displayed)}

Zero trades or weak results are retained rather than hidden. A strategy should not be selected from this table alone.

## Interpretation

{robustness_note} {positive_note} Sparse positive rows are hypotheses for further testing, not evidence of a deployable edge.

## Signal funnel

{markdown_table(candidate_summary)}

## Important limitations

- The available files are 1-hour candles. The specification's preferred 15-minute execution layer is not yet present.
- Perpetual funding, liquidation mechanics, variable fees, spread history, order-book depth, latency, and market impact are not in the source data and are therefore not modeled.
- OHLC bars do not reveal the path within a candle. The engine uses a deliberately conservative stop-first rule.
- The development/holdout split is a first defense against overfitting, not proof of future profitability. Parameters have not been optimized on the holdout set.
- BTC and ETH are tested independently; portfolio correlation and simultaneous account-level exposure are not modeled.

## Files

- `summary.csv`: development and holdout metrics.
- `candidate_summary.csv`: pattern detections and confirmation outcomes.
- `candidates.csv`: every structural signal, including rejected momentum gates.
- `trades.csv`: completed simulated trades.
- `audit_log.csv`: reconciled entry and exit fill references.
- `rejections.csv`: execution-stage rejections, primarily the 1:3 gate.
- `equity.csv.gz`: timestamped mark-to-market curves.
"""
    (output / "research_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    if not 0 < args.risk_pct <= 1.0:
        raise ValueError("--risk-pct must be greater than 0 and no more than 1")
    args.output.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, object]] = []
    all_candidates: list[pd.DataFrame] = []
    all_trades: list[pd.DataFrame] = []
    all_audit: list[pd.DataFrame] = []
    all_rejections: list[pd.DataFrame] = []
    all_equity: list[pd.DataFrame] = []
    candidate_summaries: list[dict[str, object]] = []

    for market in args.markets:
        for symbol in (value.upper() for value in args.symbols):
            source = PROJECT_ROOT / "processed" / market / f"{symbol}_1h.csv.gz"
            execution = load_ohlcv(source)
            for strategy_name in args.strategies:
                config = replace(
                    DEFAULT_CONFIGS[strategy_name],
                    risk_fraction=args.risk_pct / 100.0,
                    fee_bps=args.fee_bps,
                    slippage_bps=args.slippage_bps,
                )
                structure = build_structure_bars(
                    execution,
                    structure_rule=config.structure_rule,
                    execution_rule=config.execution_rule,
                    rsi_period=config.rsi_period,
                    divergence_lookback=config.divergence_lookback,
                )
                candidates = build_candidates(structure, config)
                candidates.insert(0, "strategy", strategy_name)
                candidates.insert(0, "symbol", symbol)
                candidates.insert(0, "market", market)
                all_candidates.append(candidates)
                counts = candidates["confirmation"].value_counts().to_dict()
                candidate_summaries.append(
                    {
                        "market": market,
                        "symbol": symbol,
                        "strategy": strategy_name,
                        "patterns": len(candidates),
                        "confirmed": counts.get("passed", 0),
                        "volume_reject": counts.get("volume", 0),
                        "rsi_reject": counts.get("rsi", 0) + counts.get("rsi_divergence", 0),
                        "macd_reject": counts.get("macd", 0),
                    }
                )

                engine_candidates = candidates.drop(columns=["market", "symbol", "strategy"])
                for period_name, (start, end) in PERIODS.items():
                    result = backtest(
                        execution,
                        engine_candidates,
                        config,
                        symbol=symbol,
                        market=market,
                        start=start,
                        end=end,
                        initial_equity=args.initial_equity,
                    )
                    validate_audit_log(result)
                    metrics = performance_metrics(result, initial_equity=args.initial_equity)
                    summaries.append(
                        {
                            "market": market,
                            "symbol": symbol,
                            "strategy": strategy_name,
                            "period": period_name,
                            "start": start,
                            "end_exclusive": end,
                            **metrics,
                        }
                    )
                    for collection, frame in (
                        (all_trades, result.trades),
                        (all_audit, result.audit),
                        (all_rejections, result.rejections),
                        (all_equity, result.equity),
                    ):
                        if frame.empty:
                            continue
                        labeled = frame.copy()
                        labeled.insert(0, "period", period_name)
                        if "strategy" not in labeled:
                            labeled.insert(0, "strategy", strategy_name)
                        if "symbol" not in labeled:
                            labeled.insert(0, "symbol", symbol)
                        if "market" not in labeled:
                            labeled.insert(0, "market", market)
                        collection.append(labeled)
                    print(
                        f"{market:13} {symbol:7} {strategy_name:19} {period_name:11} "
                        f"trades={metrics['trades']:3} return={metrics['total_return_pct']:8.3f}% "
                        f"maxDD={metrics['max_drawdown_pct']:8.3f}%"
                    )

    summary = pd.DataFrame.from_records(summaries)
    candidate_summary = pd.DataFrame.from_records(candidate_summaries)
    summary.to_csv(args.output / "summary.csv", index=False)
    candidate_summary.to_csv(args.output / "candidate_summary.csv", index=False)
    pd.concat(all_candidates, ignore_index=True).to_csv(args.output / "candidates.csv", index=False)
    if all_trades:
        pd.concat(all_trades, ignore_index=True).to_csv(args.output / "trades.csv", index=False)
    if all_audit:
        pd.concat(all_audit, ignore_index=True).to_csv(args.output / "audit_log.csv", index=False)
    if all_rejections:
        pd.concat(all_rejections, ignore_index=True).to_csv(args.output / "rejections.csv", index=False)
    if all_equity:
        pd.concat(all_equity, ignore_index=True).to_csv(
            args.output / "equity.csv.gz", index=False, compression="gzip"
        )
    write_report(args.output, summary, candidate_summary)
    print(f"Research artifacts -> {args.output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
