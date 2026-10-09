from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIRECTORY = ROOT / "user_data" / "backtest_results"
OUTPUT_DIRECTORY = ROOT / "reports" / "2025_altcoin_screen"
RUNS = {
    "alt4-bollinger-2025": "Bollinger 40d",
    "alt4-rnn-2025": "Bollinger + RNN",
    "alt4-gru-2025": "Bollinger + GRU",
    "alt4-lstm-2025": "Bollinger + LSTM",
    "alt4-hmm-trend-only-2025": "HMM trend only",
    "alt4-hmm-regime-2025": "HMM regime",
    "alt4-hmm-regime-lstm-2025": "HMM regime + LSTM",
}
PAIR_ORDER = ("SOL/USDT:USDT", "XRP/USDT:USDT", "BNB/USDT:USDT", "DOGE/USDT:USDT")


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
                selected[note] = (archive_path, strategy_name, run_metadata["run_id"])
    missing = set(RUNS) - set(selected)
    if missing:
        raise FileNotFoundError(f"Missing altcoin backtests for notes: {sorted(missing)}")
    return selected


def result_member(names: list[str]) -> str:
    candidates = [
        name for name in names if name.endswith(".json") and not name.endswith("_config.json")
    ]
    if len(candidates) != 1:
        raise ValueError(f"Expected one result JSON, found {candidates}")
    return candidates[0]


def load_result(
    archive_path: Path, strategy_name: str, run_id: str, note: str, label: str
) -> tuple[dict, list[dict], list[dict]]:
    with zipfile.ZipFile(archive_path) as archive:
        raw = json.loads(archive.read(result_member(archive.namelist())))
    strategy = raw["strategy"][strategy_name]
    wallet_stats = strategy["wallet_stats"]
    summary = {
        "model": label,
        "note": note,
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
        "market_change": float(strategy["market_change"]),
    }
    pair_rows = []
    for row in strategy["results_per_pair"]:
        if row["key"] not in PAIR_ORDER:
            continue
        pair_rows.append(
            {
                "model": label,
                "pair": row["key"],
                "trades": int(row["trades"]),
                "profit_usdt": float(row["profit_total_abs"]),
                "return_contribution": float(row["profit_total"]),
                "win_rate": float(row["winrate"]),
                "profit_factor": float(row["profit_factor"]),
                "sharpe": float(row["sharpe"]),
                "max_drawdown": float(row["max_drawdown_account"]),
            }
        )
    trades = [
        {
            "model": label,
            "pair": trade["pair"],
            "side": "short" if trade["is_short"] else "long",
            "open_date": trade["open_date"],
            "close_date": trade["close_date"],
            "profit_usdt": float(trade["profit_abs"]),
            "return": float(trade["profit_ratio"]),
            "entry_signal": trade["enter_tag"],
            "exit_reason": trade["exit_reason"],
        }
        for trade in strategy["trades"]
    ]
    return summary, pair_rows, trades


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    view = frame[columns]
    header = "| " + " | ".join(columns) + " |"
    rule = "| " + " | ".join("---" for _ in columns) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in view.itertuples(index=False, name=None)
    ]
    return "\n".join([header, rule, *rows])


def build_report(summaries: pd.DataFrame, pairs: pd.DataFrame) -> str:
    ranked = summaries.sort_values("return", ascending=False).copy()
    ranked["return_pct"] = (100 * ranked["return"]).map(lambda value: f"{value:.2f}%")
    ranked["drawdown_pct"] = (100 * ranked["max_drawdown"]).map(lambda value: f"{value:.2f}%")
    ranked["sharpe"] = ranked["wallet_sharpe"].map(lambda value: f"{value:.2f}")
    ranked["profit_factor"] = ranked["profit_factor"].map(lambda value: f"{value:.2f}")

    best = ranked.iloc[0]
    positive = ranked.loc[ranked["return"] > 0, "model"].tolist()
    pair_pivot = pairs.pivot(index="model", columns="pair", values="return_contribution")
    pair_pivot = pair_pivot.reindex(index=ranked["model"], columns=PAIR_ORDER)
    pair_pivot = pair_pivot.reset_index()
    for pair in PAIR_ORDER:
        pair_pivot[pair] = (100 * pair_pivot[pair]).map(lambda value: f"{value:.2f}%")

    positive_text = ", ".join(positive) if positive else "None"
    return f"""# 2025 SOL/XRP/BNB/DOGE strategy screen

## Conclusion

The best unchanged BTC/ETH strategy on the four-altcoin portfolio was **{best['model']}**, with
**{best['return_pct']}** net return, **{best['drawdown_pct']}** maximum drawdown, and a
**{best['sharpe']}** wallet Sharpe after 0.10% entry and exit fees. Strategies with a positive
portfolio result: {positive_text}.

This is a transfer test, not an altcoin-specific optimization. The parameters were copied without
retuning, HMMs were fit only on 2020-2024 data, and the 2025 period was held out. A positive result
means the existing rule set transferred to this sample; it does not establish live profitability.

## Portfolio results

{markdown_table(ranked, ['model', 'return_pct', 'drawdown_pct', 'sharpe', 'profit_factor', 'trades'])}

## Return contribution by pair

These percentages are each pair's contribution to the shared 10,000 USDT wallet, not standalone
pair returns.

{markdown_table(pair_pivot, ['model', *PAIR_ORDER])}

## Method

- Pairs: SOL, XRP, BNB, and DOGE USD-M perpetual futures.
- Period: 2025-01-01 through 2025-12-31 on one-hour candles.
- Starting wallet: 10,000 USDT; four concurrent 2,500 USDT positions; 1x isolated leverage.
- Costs: 0.10% on entry and 0.10% on exit; historical funding and slippage are not included.
- Sequence models: 48-hour inputs, 24-hour target, trailing 365-day training window, refreshed every 90 days, seed 42.
- HMM: three states fit separately for each pair on 2020-2024, then frozen and filtered causally during 2025.
- No missing candles were forward-filled.

Treat 2025 as consumed for these altcoins after reading this report. Any tuning should be done on
earlier rolling folds and evaluated on a new untouched period.
"""


def main() -> None:
    archives = find_archives()
    summaries: list[dict] = []
    pair_rows: list[dict] = []
    trades: list[dict] = []
    for note, label in RUNS.items():
        summary, result_pairs, result_trades = load_result(
            *archives[note], note=note, label=label
        )
        summaries.append(summary)
        pair_rows.extend(result_pairs)
        trades.extend(result_trades)

    summary_frame = pd.DataFrame(summaries)
    pair_frame = pd.DataFrame(pair_rows)
    trade_frame = pd.DataFrame(trades)
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    summary_frame.to_csv(OUTPUT_DIRECTORY / "strategy_summary.csv", index=False)
    pair_frame.to_csv(OUTPUT_DIRECTORY / "pair_summary.csv", index=False)
    trade_frame.to_csv(OUTPUT_DIRECTORY / "trade_log.csv", index=False)
    (OUTPUT_DIRECTORY / "report_data.json").write_text(
        json.dumps(
            {
                "period": "2025-01-01 through 2025-12-31",
                "pairs": list(PAIR_ORDER),
                "summaries": summaries,
                "pair_summaries": pair_rows,
                "trades": trades,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUTPUT_DIRECTORY / "research_report.md").write_text(
        build_report(summary_frame, pair_frame), encoding="utf-8"
    )
    print(
        f"Wrote {len(summaries)} strategy summaries, {len(pair_rows)} pair summaries, "
        f"and {len(trades)} trades to {OUTPUT_DIRECTORY}"
    )


if __name__ == "__main__":
    main()
