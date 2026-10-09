from __future__ import annotations

import io
import json
import math
import sys
import zipfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parent
RESULTS_DIRECTORY = ROOT / "user_data" / "backtest_results"
OUTPUT_DIRECTORY = ROOT / "reports" / "2025_2026_regime_lessons"
STRATEGY_DIRECTORY = ROOT / "user_data" / "strategies"
sys.path.insert(0, str(STRATEGY_DIRECTORY))

from regime_hmm import (  # noqa: E402
    apply_defensive_router,
    build_regime_features,
    causal_filter,
    load_hmm_parameters,
)


RUNS = {
    "hmm-regime-oos-2025-2026": "HMM three sleeve",
    "hmm-defensive-oos-2025-2026": "HMM defensive three sleeve",
    "hmm-trend-only-oos-2025-2026": "HMM trend only",
    "hmm-trend-defensive-oos-2025-2026": "HMM defensive trend only",
    "bollinger-control-oos-2025-2026": "Bollinger breakout control",
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


def find_archives() -> dict[str, tuple[Path, str, str]]:
    selected: dict[str, tuple[Path, str, str]] = {}
    for metadata_path in sorted(RESULTS_DIRECTORY.glob("*.meta.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        for strategy_name, run_metadata in metadata.items():
            note = run_metadata.get("notes")
            if note in RUNS:
                archive_path = metadata_path.with_name(
                    metadata_path.name.replace(".meta.json", ".zip")
                )
                selected[str(note)] = (
                    archive_path,
                    strategy_name,
                    str(run_metadata["run_id"]),
                )
    missing = set(RUNS).difference(selected)
    if missing:
        raise FileNotFoundError(f"Missing backtests for notes: {sorted(missing)}")
    return selected


def result_member(names: list[str]) -> str:
    candidates = [
        name
        for name in names
        if name.endswith(".json") and not name.endswith("_config.json")
    ]
    if len(candidates) != 1:
        raise ValueError(f"Expected one result JSON, found {candidates}")
    return candidates[0]


def pair_profit(strategy: dict, pair: str) -> float:
    row = next(item for item in strategy["results_per_pair"] if item["key"] == pair)
    return float(row["profit_total"])


def load_result(
    archive_path: Path, strategy_name: str, run_id: str, label: str
) -> tuple[dict[str, object], list[dict[str, object]], pd.DataFrame]:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        raw = json.loads(archive.read(result_member(names)))
        strategy = raw["strategy"][strategy_name]
        wallet_name = next(name for name in names if name.endswith("_wallet.feather"))
        wallet = pd.read_feather(io.BytesIO(archive.read(wallet_name)))

    wallet["date"] = pd.to_datetime(wallet["date"], utc=True)
    daily_wallet = (
        wallet.set_index("date")[["total_quote"]]
        .resample("1D")
        .last()
        .ffill()
        .reset_index()
    )
    wallet_stats = strategy["wallet_stats"]
    summary = {
        "model": label,
        "run_id": run_id,
        "strategy": strategy_name,
        "start": strategy["backtest_start"],
        "end": strategy["backtest_end"],
        "starting_balance_usdt": float(strategy["starting_balance"]),
        "final_balance_usdt": float(strategy["final_balance"]),
        "profit_usdt": float(strategy["profit_total_abs"]),
        "return": float(strategy["profit_total"]),
        "max_drawdown": float(wallet_stats["max_drawdown_account"]),
        "wallet_sharpe": float(wallet_stats["sharpe"]),
        "wallet_sortino": float(wallet_stats["sortino"]),
        "profit_factor": float(strategy["profit_factor"]),
        "trades": int(strategy["total_trades"]),
        "wins": int(strategy["wins"]),
        "losses": int(strategy["losses"]),
        "win_rate": float(strategy["winrate"]),
        "long_return": float(strategy["profit_total_long"]),
        "short_return": float(strategy["profit_total_short"]),
        "btc_return": pair_profit(strategy, "BTC/USDT:USDT"),
        "eth_return": pair_profit(strategy, "ETH/USDT:USDT"),
        "market_change": float(strategy["market_change"]),
    }

    trades: list[dict[str, object]] = []
    cumulative_profit = 0.0
    ordered = sorted(
        strategy["trades"],
        key=lambda trade: (trade["close_timestamp"], trade["open_timestamp"]),
    )
    for trade_number, trade in enumerate(ordered, 1):
        cumulative_profit += float(trade["profit_abs"])
        tag = str(trade["enter_tag"])
        sleeve = "Trend" if "trend" in tag or "bb40d" in tag else "Sideways"
        trades.append(
            {
                "model": label,
                "trade_number": trade_number,
                "sleeve": sleeve,
                "pair": trade["pair"],
                "side": "Short" if trade["is_short"] else "Long",
                "open_date": trade["open_date"],
                "close_date": trade["close_date"],
                "duration_hours": float(trade["trade_duration"]) / 60.0,
                "stake_usdt": float(trade["stake_amount"]),
                "entry_fee_rate": float(trade["fee_open"]),
                "exit_fee_rate": float(trade["fee_close"]),
                "funding_fees_usdt": float(trade["funding_fees"]),
                "net_profit_usdt": float(trade["profit_abs"]),
                "net_return": float(trade["profit_ratio"]),
                "cumulative_profit_usdt": cumulative_profit,
                "entry_signal": tag,
                "exit_reason": trade["exit_reason"],
            }
        )
    return summary, trades, daily_wallet


def calendar_metrics(
    label: str,
    wallet: pd.DataFrame,
    *,
    period: str,
    start: str,
    end: str,
) -> dict[str, object]:
    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    indexed = wallet.set_index("date")["total_quote"].sort_index()
    sample = indexed.loc[(indexed.index >= start_timestamp) & (indexed.index < end_timestamp)]
    if sample.empty:
        raise ValueError(f"No wallet observations for {label} in {period}")
    before = indexed.loc[indexed.index < start_timestamp]
    opening = float(before.iloc[-1]) if len(before) else float(sample.iloc[0])
    curve = pd.concat(
        [pd.Series([opening], index=[start_timestamp - pd.Timedelta(seconds=1)]), sample]
    )
    daily_return = curve.pct_change().dropna()
    standard_deviation = float(daily_return.std(ddof=1))
    downside = float(daily_return.clip(upper=0).std(ddof=1))
    drawdown = curve / curve.cummax() - 1.0
    return {
        "model": label,
        "period": period,
        "observations": len(sample),
        "actual_start": sample.index[0].date().isoformat(),
        "actual_end": sample.index[-1].date().isoformat(),
        "return": float(sample.iloc[-1] / opening - 1.0),
        "max_drawdown": abs(float(drawdown.min())),
        "wallet_sharpe": (
            float(daily_return.mean() / standard_deviation * math.sqrt(365))
            if standard_deviation > 0
            else 0.0
        ),
        "wallet_sortino": (
            float(daily_return.mean() / downside * math.sqrt(365))
            if downside > 0
            else 0.0
        ),
    }


def committed_switches(regimes: pd.Series) -> int:
    committed = regimes.loc[regimes.isin(["trend", "sideways", "crisis"])]
    return int(committed.ne(committed.shift()).sum() - (1 if len(committed) else 0))


def regime_diagnostics(symbol: str) -> tuple[dict[str, object], pd.DataFrame]:
    source_path = REPOSITORY_ROOT / "processed" / "usdt_futures" / f"{symbol}_1h.csv.gz"
    raw = pd.read_csv(source_path, compression="gzip")
    raw["date"] = pd.to_datetime(raw["open_time"], utc=True)
    raw = raw.sort_values("date").set_index("date")
    parameters = load_hmm_parameters(
        ROOT / "user_data" / "regime_models" / f"{symbol}_3state_hmm.json"
    )
    filtered = causal_filter(build_regime_features(raw), parameters)
    routed = apply_defensive_router(filtered)
    sample = routed.loc["2025-01-01":"2026-09-17 23:00:00"].copy()
    history = raw[["close"]].join(sample, how="right")
    raw_regimes = sample["raw_regime"]
    routed_regimes = sample["regime"]
    record = {
        "symbol": symbol,
        "observations": len(sample),
        "actual_start": sample.index[0].isoformat(),
        "actual_end": sample.index[-1].isoformat(),
        "mean_confidence": float(sample["regime_confidence"].mean()),
        "raw_switches": int(raw_regimes.ne(raw_regimes.shift()).sum() - 1),
        "defensive_committed_switches": committed_switches(routed_regimes),
        "uncertain_share": float(routed_regimes.eq("uncertain").mean()),
        "transition_pending_share": float(sample["regime_transition_pending"].mean()),
        "crisis_share": float(routed_regimes.eq("crisis").mean()),
    }
    return record, history


def main() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    archives = find_archives()
    summaries: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []
    wallets: dict[str, pd.DataFrame] = {}
    for note, label in RUNS.items():
        archive, strategy_name, run_id = archives[note]
        summary, run_trades, wallet = load_result(
            archive, strategy_name, run_id, label
        )
        summaries.append(summary)
        trades.extend(run_trades)
        wallets[label] = wallet

    summary_frame = pd.DataFrame.from_records(summaries)
    trade_frame = pd.DataFrame.from_records(trades)
    summary_frame.to_csv(OUTPUT_DIRECTORY / "strategy_summary.csv", index=False)
    trade_frame.to_csv(OUTPUT_DIRECTORY / "trade_log.csv", index=False)
    exit_attribution = (
        trade_frame.groupby(["model", "exit_reason"], as_index=False)
        .agg(
            trades=("net_profit_usdt", "size"),
            net_profit_usdt=("net_profit_usdt", "sum"),
            mean_net_return=("net_return", "mean"),
        )
        .sort_values(["model", "net_profit_usdt"], ascending=[True, False])
    )
    exit_attribution.to_csv(OUTPUT_DIRECTORY / "exit_attribution.csv", index=False)

    calendar_rows: list[dict[str, object]] = []
    for label, wallet in wallets.items():
        for period, start, end in (
            ("2025", "2025-01-01", "2026-01-01"),
            ("2026_ytd", "2026-01-01", "2026-09-18"),
        ):
            calendar_rows.append(
                calendar_metrics(label, wallet, period=period, start=start, end=end)
            )
    calendar_frame = pd.DataFrame.from_records(calendar_rows)
    calendar_frame.to_csv(OUTPUT_DIRECTORY / "calendar_summary.csv", index=False)

    diagnostic_rows: list[dict[str, object]] = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        record, history = regime_diagnostics(symbol)
        diagnostic_rows.append(record)
        history.rename_axis("date").reset_index().to_csv(
            OUTPUT_DIRECTORY / f"{symbol.lower()}_regime_history.csv.gz",
            index=False,
            compression="gzip",
        )
    diagnostics = pd.DataFrame.from_records(diagnostic_rows)
    diagnostics.to_csv(OUTPUT_DIRECTORY / "regime_diagnostics.csv", index=False)

    displayed = summary_frame[
        [
            "model",
            "return",
            "max_drawdown",
            "wallet_sharpe",
            "profit_factor",
            "trades",
            "btc_return",
            "eth_return",
        ]
    ].copy()
    for column in ("return", "max_drawdown", "btc_return", "eth_return"):
        displayed[column] = (100 * displayed[column].astype(float)).round(2).astype(str) + "%"
    for column in ("wallet_sharpe", "profit_factor"):
        displayed[column] = displayed[column].astype(float).round(3)

    calendar_display = calendar_frame[
        ["model", "period", "return", "max_drawdown", "wallet_sharpe"]
    ].copy()
    for column in ("return", "max_drawdown"):
        calendar_display[column] = (
            100 * calendar_display[column].astype(float)
        ).round(2).astype(str) + "%"
    calendar_display["wallet_sharpe"] = calendar_display["wallet_sharpe"].round(3)

    diagnostics_display = diagnostics.copy()
    for column in ("uncertain_share", "transition_pending_share", "crisis_share"):
        diagnostics_display[column] = (
            100 * diagnostics_display[column].astype(float)
        ).round(2).astype(str) + "%"
    diagnostics_display["mean_confidence"] = diagnostics_display["mean_confidence"].round(3)
    defensive_exit_display = exit_attribution.loc[
        exit_attribution["model"].str.contains("defensive"),
        ["model", "exit_reason", "trades", "net_profit_usdt", "mean_net_return"],
    ].copy()
    defensive_exit_display["net_profit_usdt"] = defensive_exit_display[
        "net_profit_usdt"
    ].round(2)
    defensive_exit_display["mean_net_return"] = (
        100 * defensive_exit_display["mean_net_return"]
    ).round(2).astype(str) + "%"

    baseline = summary_frame.set_index("model")
    defensive_delta = float(
        baseline.at["HMM defensive three sleeve", "return"]
        - baseline.at["HMM three sleeve", "return"]
    )
    trend_delta = float(
        baseline.at["HMM defensive trend only", "return"]
        - baseline.at["HMM trend only", "return"]
    )
    report = f"""# Regime lessons applied: extended 2025–September 2026 OOS backtest

This is a research backtest, not a live-trading recommendation. The HMM/scaler remains fit only on 2020–2024 data. The evaluation ends at the latest complete checksum-verified daily archive, **2026-09-17 23:00 UTC**. The full 2025–2026 span is out of sample relative to model fitting, but 2025 was previously inspected, so **2026 YTD is the cleaner forward extension—not a pristine untouched holdout after this report is read**.

## What Lessons 12 and 13 add

- Judge regime detection by economic value after fees, drawdown, and switching—not classification accuracy alone.
- Keep probabilities and admit an explicit uncertain/transition state instead of forcing every gray-zone candle into trend or sideways.
- Use asymmetric switching: crisis protection should be immediate, while ordinary trend/sideways changes should require persistence.
- In uncertainty, prioritize risk reduction. Because this Freqtrade test uses indivisible 5,000 USDT slots rather than continuous sizing, the defensive implementation exits to cash and blocks new entries.
- Track switch frequency, uncertain-state share, and sleeve-level attribution so a regime router cannot hide excessive churn.

Implementation: crisis probability at or above 45% routes to cash immediately; trend/sideways requires confidence at or above 55% for three consecutive hourly candles; all other observations are `uncertain`. These thresholds were carried from the frozen model/local protocol, not selected on 2025–2026 results.

Sources: [Lesson 12: Regime Detection](https://waylandz.com/quant-book-en/Lesson-12-Regime-Detection/) and [Lesson 13: Regime Misjudgment and Systemic Collapse](https://waylandz.com/quant-book-en/Lesson-13-Regime-Misjudgment-and-Systemic-Collapse/).

## Full OOS results: 2025-01-01 through 2026-09-17

All results use 10,000 USDT starting capital, two 5,000 USDT slots, 1x leverage, and 0.10% fees per side. Funding, slippage, market impact, and liquidation dynamics remain excluded.

{markdown_table(displayed)}

The defensive policy changed three-sleeve return by **{100 * defensive_delta:+.2f} percentage points** and trend-only return by **{100 * trend_delta:+.2f} percentage points** versus their otherwise identical raw-HMM versions. A negative delta is still useful: it means the proposed protection cost more opportunity/turnover than it saved in this sample and should not be promoted merely because it sounds safer.

### Defensive exit attribution

{markdown_table(defensive_exit_display)}

The uncertainty rule is the failure point: it repeatedly crystallized small transition losses. The lesson is to test gradual exposure scaling or entry blocking separately from forced liquidation; combining all three in one hard cash switch is too blunt for this hourly model.

## Calendar split

{markdown_table(calendar_display)}

## Router health

{markdown_table(diagnostics_display)}

`raw_switches` counts every argmax-label flip. `defensive_committed_switches` ignores uncertain rows and counts only changes among committed trend/sideways/crisis states. `transition_pending_share` isolates the three-candle hysteresis cost; the remainder of uncertain time comes from confidence below 55%.

## Interpretation rules

1. Prefer the simplest survivor that improves return/drawdown after fees across both assets; do not select a policy from 2025–2026 total return alone.
2. Treat the no-HMM Bollinger strategy as the economic-value control. If the router lowers Sharpe without a material drawdown benefit, it has not earned its complexity.
3. The defensive variant is an ablation, not a tuned winner. Validate confirmation lengths only on rolling 2022–2024 folds before freezing another future test.
4. Add historical funding, bid/ask slippage, a one-candle execution delay, and partial exposure scaling before any deployment decision.
"""
    (OUTPUT_DIRECTORY / "research_report.md").write_text(report, encoding="utf-8")
    print(displayed.to_string(index=False))
    print(f"Artifacts -> {OUTPUT_DIRECTORY.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
