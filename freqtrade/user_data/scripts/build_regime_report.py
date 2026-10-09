from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parent
RESULTS_DIRECTORY = ROOT / "user_data" / "backtest_results"
OUTPUT_DIRECTORY = ROOT / "reports" / "2025_regime_baseline"
STRATEGY_DIRECTORY = ROOT / "user_data" / "strategies"
sys.path.insert(0, str(STRATEGY_DIRECTORY))

from regime_hmm import build_regime_features, causal_filter, load_hmm_parameters


RUNS = {
    "hmm-trend-only-2025": "HMM trend only",
    "hmm-sideways-only-2025": "HMM sideways only",
    "hmm-regime-2025": "HMM three sleeve",
    "hmm-regime-lstm-2025": "HMM + LSTM gate",
}

COST_RUNS = {
    "hmm-regime-fee-005-2025": ("HMM three sleeve", "0.05%", 0.0005),
    "hmm-regime-2025": ("HMM three sleeve", "0.10%", 0.0010),
    "hmm-regime-fee-020-2025": ("HMM three sleeve", "0.20%", 0.0020),
    "hmm-trend-only-fee-005-2025": ("HMM trend only", "0.05%", 0.0005),
    "hmm-trend-only-2025": ("HMM trend only", "0.10%", 0.0010),
    "hmm-trend-only-fee-020-2025": ("HMM trend only", "0.20%", 0.0020),
}


def find_archives(notes: set[str]) -> dict[str, tuple[Path, str, str]]:
    selected: dict[str, tuple[Path, str, str]] = {}
    for metadata_path in sorted(RESULTS_DIRECTORY.glob("*.meta.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        for strategy_name, run_metadata in metadata.items():
            note = run_metadata.get("notes")
            if note in notes:
                archive_path = metadata_path.with_name(
                    metadata_path.name.replace(".meta.json", ".zip")
                )
                selected[note] = (archive_path, strategy_name, run_metadata["run_id"])
    missing = notes - set(selected)
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
) -> tuple[dict, list[dict], pd.DataFrame]:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        raw = json.loads(archive.read(result_member(names)))
        strategy = raw["strategy"][strategy_name]
        wallet_name = next(name for name in names if name.endswith("_wallet.feather"))
        wallet = pd.read_feather(io.BytesIO(archive.read(wallet_name)))

    wallet["date"] = pd.to_datetime(wallet["date"], utc=True).dt.tz_localize(None)
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

    trades = []
    cumulative_profit = 0.0
    ordered_trades = sorted(
        strategy["trades"],
        key=lambda trade: (trade["close_timestamp"], trade["open_timestamp"]),
    )
    for trade_number, trade in enumerate(ordered_trades, 1):
        cumulative_profit += float(trade["profit_abs"])
        entry_signal = trade["enter_tag"]
        sleeve = "Trend" if "trend" in entry_signal else "Sideways"
        trades.append(
            {
                "model": label,
                "trade_number": trade_number,
                "sleeve": sleeve,
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
                "cumulative_profit_usdt": cumulative_profit,
                "entry_signal": entry_signal,
                "exit_reason": trade["exit_reason"],
            }
        )
    return summary, trades, daily_wallet


def regime_history(symbol: str) -> pd.DataFrame:
    source_path = REPOSITORY_ROOT / "processed" / "usdt_futures" / f"{symbol}_1h.csv.gz"
    raw = pd.read_csv(source_path, compression="gzip")
    raw["date"] = pd.to_datetime(raw["open_time"], utc=True)
    raw = raw.sort_values("date").set_index("date")
    raw = raw.loc["2024-11-20 08:00:00":"2025-12-31 23:00:00"]
    parameters = load_hmm_parameters(
        ROOT / "user_data" / "regime_models" / f"{symbol}_3state_hmm.json"
    )
    filtered = causal_filter(build_regime_features(raw), parameters)
    result = raw[["close"]].join(filtered)
    result = result.loc["2025-01-01":"2025-12-31 23:00:00"]
    daily = result.resample("1D").last().dropna(subset=["close"])
    return daily


def build_dashboard(
    summaries: list[dict],
    trades: pd.DataFrame,
    wallets: dict[str, pd.DataFrame],
    histories: dict[str, pd.DataFrame],
) -> None:
    figure = make_subplots(
        rows=5,
        cols=1,
        vertical_spacing=0.055,
        row_heights=[0.25, 0.17, 0.17, 0.20, 0.20],
        subplot_titles=(
            "2025 wallet equity",
            "Return and maximum drawdown",
            "Net profit by strategy sleeve",
            "BTC daily regime (frozen HMM, causal filter)",
            "ETH daily regime (frozen HMM, causal filter)",
        ),
        specs=[[{}], [{"secondary_y": True}], [{}], [{}], [{}]],
    )
    colors = {
        "HMM trend only": "#2ca02c",
        "HMM sideways only": "#d62728",
        "HMM three sleeve": "#1f77b4",
        "HMM + LSTM gate": "#9467bd",
    }
    for label, wallet in wallets.items():
        figure.add_trace(
            go.Scatter(
                x=wallet["date"],
                y=wallet["total_quote"],
                name=label,
                line={"color": colors[label], "width": 2},
            ),
            row=1,
            col=1,
        )

    labels = [summary["model"] for summary in summaries]
    figure.add_trace(
        go.Bar(
            x=labels,
            y=[100 * summary["return"] for summary in summaries],
            name="Return %",
            marker_color="#1f77b4",
        ),
        row=2,
        col=1,
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=labels,
            y=[100 * summary["max_drawdown"] for summary in summaries],
            name="Max drawdown %",
            mode="lines+markers",
            line={"color": "#d62728", "width": 2},
        ),
        row=2,
        col=1,
        secondary_y=True,
    )

    sleeve_profit = (
        trades.groupby(["model", "sleeve"], as_index=False)["net_profit_usdt"].sum()
    )
    for sleeve, color in (("Trend", "#2ca02c"), ("Sideways", "#ff7f0e")):
        sleeve_rows = sleeve_profit[sleeve_profit["sleeve"] == sleeve].set_index("model")
        figure.add_trace(
            go.Bar(
                x=labels,
                y=[
                    float(sleeve_rows.loc[label, "net_profit_usdt"])
                    if label in sleeve_rows.index
                    else 0.0
                    for label in labels
                ],
                name=f"{sleeve} sleeve P&L",
                marker_color=color,
            ),
            row=3,
            col=1,
        )

    regime_colors = {"trend": "#2ca02c", "sideways": "#ffbf00", "crisis": "#d62728"}
    for row_number, symbol in ((4, "BTCUSDT"), (5, "ETHUSDT")):
        history = histories[symbol]
        figure.add_trace(
            go.Scatter(
                x=history.index,
                y=history["close"],
                name=f"{symbol} price",
                mode="lines",
                line={"color": "#777", "width": 1},
                showlegend=False,
            ),
            row=row_number,
            col=1,
        )
        for regime, color in regime_colors.items():
            subset = history[history["regime"] == regime]
            figure.add_trace(
                go.Scatter(
                    x=subset.index,
                    y=subset["close"],
                    name=f"{regime.title()} regime",
                    mode="markers",
                    marker={"color": color, "size": 5},
                    legendgroup=regime,
                    showlegend=row_number == 4,
                    hovertemplate=(
                        "%{x|%Y-%m-%d}<br>Price %{y:,.2f}<br>"
                        + regime.title()
                        + "<extra></extra>"
                    ),
                ),
                row=row_number,
                col=1,
            )

    figure.update_layout(
        title="BTC/ETH three-regime strategy baseline",
        template="plotly_white",
        height=1600,
        barmode="group",
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "x": 0},
        margin={"l": 70, "r": 70, "t": 120, "b": 50},
    )
    figure.update_yaxes(title_text="Wallet (USDT)", row=1, col=1)
    figure.update_yaxes(title_text="Return (%)", row=2, col=1, secondary_y=False)
    figure.update_yaxes(title_text="Drawdown (%)", row=2, col=1, secondary_y=True)
    figure.update_yaxes(title_text="Net P&L (USDT)", row=3, col=1)
    figure.update_yaxes(title_text="BTC/USDT", type="log", row=4, col=1)
    figure.update_yaxes(title_text="ETH/USDT", type="log", row=5, col=1)
    figure.write_html(
        OUTPUT_DIRECTORY / "regime_dashboard.html",
        include_plotlyjs=True,
        full_html=True,
    )


def main() -> None:
    notes = set(RUNS) | set(COST_RUNS)
    archives = find_archives(notes)
    summaries: list[dict] = []
    all_trades: list[dict] = []
    wallets: dict[str, pd.DataFrame] = {}

    for note, label in RUNS.items():
        summary, trades, wallet = load_result(*archives[note], label)
        summary["note"] = note
        summaries.append(summary)
        all_trades.extend(trades)
        wallets[label] = wallet

    cost_summaries = []
    for note, (strategy_label, fee_label, fee) in COST_RUNS.items():
        summary, _, _ = load_result(*archives[note], strategy_label)
        cost_summaries.append(
            {
                "model": strategy_label,
                "fee_per_side": fee,
                "fee_label": fee_label,
                "return": summary["return"],
                "max_drawdown": summary["max_drawdown"],
                "wallet_sharpe": summary["wallet_sharpe"],
                "profit_factor": summary["profit_factor"],
                "trades": summary["trades"],
            }
        )

    trades_frame = pd.DataFrame(all_trades)
    histories = {
        symbol: regime_history(symbol) for symbol in ("BTCUSDT", "ETHUSDT")
    }
    occupancy = {
        symbol: {
            regime: int(count)
            for regime, count in history["regime"].value_counts().items()
        }
        for symbol, history in histories.items()
    }

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summaries).to_csv(OUTPUT_DIRECTORY / "strategy_summary.csv", index=False)
    trades_frame.to_csv(OUTPUT_DIRECTORY / "full_trade_log.csv", index=False)
    pd.DataFrame(cost_summaries).to_csv(OUTPUT_DIRECTORY / "cost_stress.csv", index=False)

    previous_report = json.loads(
        (ROOT / "reports" / "2025_sequence_baseline" / "report_data.json").read_text(
            encoding="utf-8"
        )
    )
    all_strategy_summaries = previous_report["summaries"] + summaries
    pd.DataFrame(all_strategy_summaries).to_csv(
        OUTPUT_DIRECTORY / "all_strategy_summary.csv", index=False
    )

    payload = {
        "generated_from": "Freqtrade 2026.8 backtest archives",
        "period": "2025-01-01 through 2025-12-31",
        "summaries": summaries,
        "cost_stress": cost_summaries,
        "regime_occupancy_days": occupancy,
        "trades": all_trades,
        "previous_sequence_controls": previous_report["summaries"],
    }
    (OUTPUT_DIRECTORY / "report_data.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    build_dashboard(summaries, trades_frame, wallets, histories)
    print(
        f"Wrote {len(summaries)} summaries, {len(all_trades)} trades, "
        f"cost stress, regime history, and dashboard to {OUTPUT_DIRECTORY}"
    )


if __name__ == "__main__":
    main()
