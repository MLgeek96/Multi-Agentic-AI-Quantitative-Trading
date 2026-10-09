from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "user_data" / "backtest_results"
OUTPUT_DIR = ROOT / "reports" / "2025_sequence_baseline"

RUNS = {
    "baseline-2025": ("Bollinger only", "BollingerBreakout40D"),
    "rnn-seed42-2025": ("RNN gate", "SequenceBreakoutStrategy"),
    "gru-seed42-2025": ("GRU gate", "SequenceBreakoutStrategy"),
    "lstm-seed42-2025": ("LSTM gate", "SequenceBreakoutStrategy"),
    "transformer-seed42-2025": ("Transformer gate", "SequenceBreakoutStrategy"),
}


def find_result_archives() -> dict[str, tuple[Path, str, str]]:
    selected: dict[str, tuple[Path, str, str]] = {}
    for meta_path in sorted(RESULTS_DIR.glob("*.meta.json")):
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        for strategy_name, run_metadata in metadata.items():
            note = run_metadata.get("notes")
            if note in RUNS:
                archive_path = meta_path.with_name(meta_path.name.replace(".meta.json", ".zip"))
                selected[note] = (archive_path, strategy_name, run_metadata["run_id"])
    missing = set(RUNS) - set(selected)
    if missing:
        raise FileNotFoundError(f"Missing final backtests: {sorted(missing)}")
    return selected


def result_member(names: list[str]) -> str:
    candidates = [name for name in names if name.endswith(".json") and not name.endswith("_config.json")]
    if len(candidates) != 1:
        raise ValueError(f"Expected one result JSON, found {candidates}")
    return candidates[0]


def pair_profit(strategy: dict, pair: str) -> float:
    row = next(item for item in strategy["results_per_pair"] if item["key"] == pair)
    return float(row["profit_total"])


def load_run(
    note: str, archive_path: Path, strategy_name: str, run_id: str
) -> tuple[dict, list[dict], list[dict]]:
    label, _ = RUNS[note]
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        raw = json.loads(archive.read(result_member(names)))
        strategy = raw["strategy"][strategy_name]
        wallet_name = next(name for name in names if name.endswith("_wallet.feather"))
        wallet = pd.read_feather(io.BytesIO(archive.read(wallet_name)))

    wallet["date"] = pd.to_datetime(wallet["date"], utc=True).dt.tz_localize(None)
    daily = (
        wallet.set_index("date")["total_quote"]
        .resample("1D")
        .last()
        .ffill()
        .reset_index()
    )
    equity = [
        {"date": row.date.strftime("%Y-%m-%d"), "equity": round(float(row.total_quote), 6)}
        for row in daily.itertuples(index=False)
    ]

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
        "cagr": float(strategy["cagr"]),
        "max_drawdown": float(wallet_stats["max_drawdown_account"]),
        "wallet_sharpe": float(wallet_stats["sharpe"]),
        "wallet_sortino": float(wallet_stats["sortino"]),
        "profit_factor": float(strategy["profit_factor"]),
        "trades": int(strategy["total_trades"]),
        "wins": int(strategy["wins"]),
        "losses": int(strategy["losses"]),
        "win_rate": float(strategy["winrate"]),
        "long_trades": int(strategy["trade_count_long"]),
        "short_trades": int(strategy["trade_count_short"]),
        "long_return": float(strategy["profit_total_long"]),
        "short_return": float(strategy["profit_total_short"]),
        "btc_return": pair_profit(strategy, "BTC/USDT:USDT"),
        "eth_return": pair_profit(strategy, "ETH/USDT:USDT"),
        "market_change": float(strategy["market_change"]),
        "fee_per_side": 0.001,
        "funding_assumption": 0.0,
    }

    trades = []
    cumulative = 0.0
    ordered = sorted(strategy["trades"], key=lambda trade: (trade["close_timestamp"], trade["open_timestamp"]))
    for trade_number, trade in enumerate(ordered, 1):
        cumulative += float(trade["profit_abs"])
        trades.append(
            {
                "model": label,
                "trade_number": trade_number,
                "pair": trade["pair"],
                "side": "Short" if trade["is_short"] else "Long",
                "open_date": trade["open_date"],
                "close_date": trade["close_date"],
                "duration_hours": int(trade["trade_duration"]) / 60,
                "entry_price": float(trade["open_rate"]),
                "exit_price": float(trade["close_rate"]),
                "minimum_price": float(trade["min_rate"]),
                "maximum_price": float(trade["max_rate"]),
                "stake_usdt": float(trade["stake_amount"]),
                "quantity": float(trade["amount"]),
                "leverage": float(trade["leverage"]),
                "entry_fee_rate": float(trade["fee_open"]),
                "exit_fee_rate": float(trade["fee_close"]),
                "funding_fees_usdt": float(trade["funding_fees"]),
                "net_profit_usdt": float(trade["profit_abs"]),
                "net_return": float(trade["profit_ratio"]),
                "cumulative_profit_usdt": cumulative,
                "entry_signal": trade["enter_tag"],
                "exit_reason": trade["exit_reason"],
                "weekday_opened": trade["weekday"],
            }
        )
    return summary, trades, equity


def main() -> None:
    selected = find_result_archives()
    summaries: list[dict] = []
    trades: list[dict] = []
    equity: dict[str, list[dict]] = {}
    for note in RUNS:
        summary, run_trades, run_equity = load_run(note, *selected[note])
        summaries.append(summary)
        trades.extend(run_trades)
        equity[summary["model"]] = run_equity

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_from": "Freqtrade 2026.8 backtest archives",
        "period": "2025-01-01 through 2025-12-31",
        "summaries": summaries,
        "trades": trades,
        "equity": equity,
    }
    (OUTPUT_DIR / "report_data.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(summaries)} summaries, {len(trades)} trades, and daily equity to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
