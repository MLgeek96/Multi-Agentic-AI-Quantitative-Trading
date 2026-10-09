from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"]
VALIDATION_START = pd.Timestamp("2026-01-01", tz="UTC")
VALIDATION_END = pd.Timestamp("2026-09-17", tz="UTC")
FEE_PER_SIDE = 0.001
BASE_SLIPPAGE_PER_SIDE = 0.0005
PORTFOLIO_VOL_TARGET = 0.20
PER_COIN_CAP = 0.25

RESULT_PATTERNS = {
    "Bollinger 40d": "bollinger/*.zip",
    "RNN static": "rnn_static-*.zip",
    "GRU static": "gru_static-*.zip",
    "LSTM static": "lstm_static-*.zip",
    "Transformer static": "transformer_static-*.zip",
    "HMM trend": "hmm_trend-*.zip",
    "HMM switching": "hmm_regime-*.zip",
    "HMM defensive": "hmm_defensive-*.zip",
    "HMM trend defensive": "hmm_trend_defensive-*.zip",
    "HMM + LSTM static": "hmm_lstm_static-*.zip",
}

ENSEMBLE_MODELS = [
    "Bollinger 40d",
    "RNN static",
    "GRU static",
    "LSTM static",
    "Transformer static",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the six-coin frozen-2025 / 2026 holdout validation report."
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("freqtrade/validation_runs/2026_sixcoin"),
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("freqtrade/user_data/data/binanceusdm/futures"),
    )
    parser.add_argument(
        "--regime-model-root",
        type=Path,
        default=Path("freqtrade/user_data/regime_models"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("freqtrade/reports/2026_sixcoin_validation"),
    )
    parser.add_argument(
        "--refresh-funding",
        action="store_true",
        help="Refresh funding observations from Binance USD-M Futures.",
    )
    return parser.parse_args()


def latest_match(root: Path, pattern: str) -> Path:
    matches = sorted(root.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No result archive matches {root / pattern}")
    return matches[-1]


def load_result_archive(path: Path) -> tuple[str, dict]:
    with zipfile.ZipFile(path) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.endswith(".json") and not name.endswith("_config.json")
        ]
        if len(candidates) != 1:
            raise ValueError(f"Expected one result JSON in {path}, found {candidates}")
        payload = json.loads(archive.read(candidates[0]))
    strategy_name, result = next(iter(payload["strategy"].items()))
    return strategy_name, result


def load_all_results(results_root: Path) -> tuple[dict[str, dict], pd.DataFrame]:
    results: dict[str, dict] = {}
    rows: list[dict] = []
    for label, pattern in RESULT_PATTERNS.items():
        archive = latest_match(results_root, pattern)
        strategy_name, result = load_result_archive(archive)
        results[label] = result
        rows.append(
            {
                "model": label,
                "strategy": strategy_name,
                "archive": str(archive),
                "train_design": (
                    "2025 static fit"
                    if "static" in label.lower()
                    else "parameters frozen before 2026"
                ),
                "validation_start": result["backtest_start"],
                "validation_end": result["backtest_end"],
                "trades": int(result["total_trades"]),
                "long_trades": int(result["trade_count_long"]),
                "short_trades": int(result["trade_count_short"]),
                "win_rate_pct": float(result["winrate"]) * 100,
                "return_pct": float(result["profit_total"]) * 100,
                "final_balance_usdt": float(result["final_balance"]),
                "max_drawdown_pct": float(result["max_relative_drawdown"]) * 100,
                "closed_trade_sharpe": float(result["sharpe"]),
                "profit_factor": float(result["profit_factor"]),
                "mean_profit_p_value": float(result["p_value"]),
                "fee_bps_per_side": FEE_PER_SIDE * 10_000,
                "funding_included": False,
                "slippage_included": False,
            }
        )
    return results, pd.DataFrame(rows).sort_values("return_pct", ascending=False)


def load_hourly_data(data_root: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        path = data_root / f"{symbol}_USDT_USDT-1h-futures.feather"
        frame = pd.read_feather(path).sort_values("date").reset_index(drop=True)
        frame["date"] = pd.to_datetime(frame["date"], utc=True)
        frames[symbol] = frame
    return frames


def build_daily_market(hourly: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    closes = {}
    for symbol, frame in hourly.items():
        series = frame.set_index("date")["close"].astype(float).resample("1D").last()
        closes[symbol] = series
    daily_close = pd.DataFrame(closes).sort_index().ffill()
    daily_returns = daily_close.pct_change(fill_method=None)
    return daily_close, daily_returns


def trade_positions(results: dict[str, dict], dates: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    observation_times = dates + pd.Timedelta(hours=23)
    positions: dict[str, pd.DataFrame] = {}
    for label in ENSEMBLE_MODELS:
        position = pd.DataFrame(0.0, index=dates, columns=SYMBOLS)
        for trade in results[label]["trades"]:
            symbol = trade["pair"].split("/")[0]
            opened = pd.Timestamp(trade["open_date"])
            closed = pd.Timestamp(trade["close_date"])
            side = -1.0 if trade["is_short"] else 1.0
            active = (observation_times >= opened) & (observation_times < closed)
            position.loc[active, symbol] = side
        positions[label] = position
    return positions


def build_regime_gate(
    hourly: dict[str, pd.DataFrame], regime_model_root: Path, dates: pd.DatetimeIndex
) -> dict[str, pd.DataFrame]:
    strategy_dir = Path("freqtrade/user_data/strategies").resolve()
    if str(strategy_dir) not in sys.path:
        sys.path.insert(0, str(strategy_dir))
    from regime_hmm import (  # pylint: disable=import-outside-toplevel
        apply_defensive_router,
        build_regime_features,
        causal_filter,
        load_hmm_parameters,
    )

    output = {
        "regime": pd.DataFrame("unknown", index=dates, columns=SYMBOLS),
        "confidence": pd.DataFrame(0.0, index=dates, columns=SYMBOLS),
        "crisis_probability": pd.DataFrame(0.0, index=dates, columns=SYMBOLS),
        "gate": pd.DataFrame(0.0, index=dates, columns=SYMBOLS),
    }
    for symbol, frame in hourly.items():
        parameters = load_hmm_parameters(regime_model_root / f"{symbol}USDT_3state_hmm.json")
        filtered = causal_filter(build_regime_features(frame), parameters)
        routed = apply_defensive_router(
            filtered,
            confidence_threshold=0.55,
            crisis_probability_threshold=0.45,
            confirmation_candles=3,
        )
        routed = routed.set_axis(frame["date"])
        daily = routed.resample("1D").last().reindex(dates)
        output["regime"][symbol] = daily["regime"].fillna("unknown")
        output["confidence"][symbol] = daily["regime_confidence"].fillna(0.0)
        output["crisis_probability"][symbol] = daily["regime_crisis_prob"].fillna(0.0)
        output["gate"][symbol] = (
            daily["regime"].map({"trend": 1.0, "sideways": 0.5}).fillna(0.0)
        )
    return output


def fetch_funding(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    query = urllib.parse.urlencode(
        {
            "symbol": f"{symbol}USDT",
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000),
            "limit": 1000,
        }
    )
    request = urllib.request.Request(
        f"https://fapi.binance.com/fapi/v1/fundingRate?{query}",
        headers={"User-Agent": "sixcoin-validation/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Binance funding response for {symbol}: {payload}")
    return payload


def load_funding(output_root: Path, refresh: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    cache = output_root / "funding_rates.csv.gz"
    if cache.exists() and not refresh:
        funding = pd.read_csv(cache)
    else:
        records = []
        end_exclusive = VALIDATION_END + pd.Timedelta(days=1)
        for symbol in SYMBOLS:
            for row in fetch_funding(symbol, VALIDATION_START, end_exclusive):
                records.append(
                    {
                        "symbol": symbol,
                        "funding_time": pd.to_datetime(row["fundingTime"], unit="ms", utc=True),
                        "funding_rate": float(row["fundingRate"]),
                        "mark_price": float(row["markPrice"]) if row.get("markPrice") else np.nan,
                    }
                )
        funding = pd.DataFrame(records).sort_values(["funding_time", "symbol"])
        funding.to_csv(cache, index=False, compression="gzip")
    funding["funding_time"] = pd.to_datetime(
        funding["funding_time"], utc=True, format="mixed"
    )
    funding["date"] = funding["funding_time"].dt.floor("D")
    daily = (
        funding.pivot_table(index="date", columns="symbol", values="funding_rate", aggfunc="sum")
        .reindex(columns=SYMBOLS)
        .fillna(0.0)
    )
    return funding, daily


def cap_weights(weights: pd.Series, cap: float = PER_COIN_CAP) -> pd.Series:
    return weights.clip(lower=-cap, upper=cap)


def make_allocations(
    positions: dict[str, pd.DataFrame],
    regimes: dict[str, pd.DataFrame],
    daily_returns: pd.DataFrame,
    dates: pd.DatetimeIndex,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    stack = np.stack([positions[label].to_numpy() for label in ENSEMBLE_MODELS], axis=2)
    long_votes = pd.DataFrame((stack > 0).sum(axis=2), index=dates, columns=SYMBOLS)
    short_votes = pd.DataFrame((stack < 0).sum(axis=2), index=dates, columns=SYMBOLS)
    direction = pd.DataFrame(0.0, index=dates, columns=SYMBOLS)
    direction[long_votes >= 3] = 1.0
    direction[short_votes >= 3] = -1.0
    confidence = pd.DataFrame(
        np.maximum(long_votes, short_votes).to_numpy() / len(ENSEMBLE_MODELS),
        index=dates,
        columns=SYMBOLS,
    ).where(direction != 0, 0.0)

    equal = pd.DataFrame(0.0, index=dates, columns=SYMBOLS)
    variable = pd.DataFrame(0.0, index=dates, columns=SYMBOLS)
    variable_gated = pd.DataFrame(0.0, index=dates, columns=SYMBOLS)
    trailing_vol = daily_returns[SYMBOLS].rolling(30, min_periods=20).std() * math.sqrt(365)

    for date in dates:
        active = direction.loc[date] != 0
        active_count = int(active.sum())
        if active_count:
            equal.loc[date, active] = direction.loc[date, active] / max(4, active_count)

        vol = trailing_vol.loc[date].clip(lower=0.05)
        raw = direction.loc[date] * confidence.loc[date] / vol
        raw = raw.replace([np.inf, -np.inf], 0.0).fillna(0.0)
        gross = raw.abs().sum()
        if gross <= 0:
            continue
        proposed = cap_weights(raw / gross)
        history = daily_returns.loc[:date, SYMBOLS].tail(30).dropna(how="any")
        if len(history) >= 20:
            covariance = history.cov().to_numpy() * 365
            forecast_vol = math.sqrt(max(float(proposed.to_numpy() @ covariance @ proposed.to_numpy()), 0.0))
            if forecast_vol > PORTFOLIO_VOL_TARGET:
                proposed *= PORTFOLIO_VOL_TARGET / forecast_vol
        variable.loc[date] = proposed

        gated = proposed * regimes["gate"].loc[date]
        if len(history) >= 20:
            covariance = history.cov().to_numpy() * 365
            forecast_vol = math.sqrt(max(float(gated.to_numpy() @ covariance @ gated.to_numpy()), 0.0))
            if forecast_vol > PORTFOLIO_VOL_TARGET:
                gated *= PORTFOLIO_VOL_TARGET / forecast_vol
        variable_gated.loc[date] = gated

    allocations = {
        "Ensemble equal": equal,
        "Ensemble equal + HMM gate": equal * regimes["gate"],
        "Ensemble variable": variable,
        "Ensemble variable + HMM gate": variable_gated,
    }
    diagnostics = {
        "long_votes": long_votes,
        "short_votes": short_votes,
        "direction": direction,
        "confidence": confidence,
        "trailing_vol": trailing_vol.reindex(dates),
    }
    return allocations, diagnostics


def portfolio_path(
    weights: pd.DataFrame,
    daily_returns: pd.DataFrame,
    daily_funding: pd.DataFrame,
    slippage: float,
) -> pd.DataFrame:
    asset_returns = daily_returns.reindex(weights.index)[SYMBOLS].fillna(0.0)
    funding = daily_funding.reindex(weights.index)[SYMBOLS].fillna(0.0)
    held_weights = weights.shift(1).fillna(0.0)
    turnover = weights.diff().abs().sum(axis=1)
    turnover.iloc[0] = weights.iloc[0].abs().sum()
    price_return = (held_weights * asset_returns).sum(axis=1)
    funding_cost = (held_weights * funding).sum(axis=1)
    fee_cost = turnover * FEE_PER_SIDE
    slippage_cost = turnover * slippage
    net_return = price_return - funding_cost - fee_cost - slippage_cost
    equity = (1.0 + net_return).cumprod()
    return pd.DataFrame(
        {
            "price_return": price_return,
            "funding_cost": funding_cost,
            "fee_cost": fee_cost,
            "slippage_cost": slippage_cost,
            "net_return": net_return,
            "turnover": turnover,
            "gross_exposure": weights.abs().sum(axis=1),
            "equity": equity,
        }
    )


def summarize_path(name: str, path: pd.DataFrame, slippage: float) -> dict:
    net = path["net_return"]
    equity = path["equity"]
    drawdown = equity / equity.cummax() - 1.0
    annual_vol = net.std(ddof=0) * math.sqrt(365)
    return {
        "portfolio": name,
        "return_pct": (equity.iloc[-1] - 1.0) * 100,
        "annualized_vol_pct": annual_vol * 100,
        "sharpe": (net.mean() * 365 / annual_vol) if annual_vol > 0 else np.nan,
        "max_drawdown_pct": -drawdown.min() * 100,
        "avg_gross_exposure_pct": path["gross_exposure"].mean() * 100,
        "max_gross_exposure_pct": path["gross_exposure"].max() * 100,
        "total_turnover_x": path["turnover"].sum(),
        "fee_drag_pct_simple": path["fee_cost"].sum() * 100,
        "slippage_drag_pct_simple": path["slippage_cost"].sum() * 100,
        "funding_cost_pct_simple": path["funding_cost"].sum() * 100,
        "slippage_bps_per_side": slippage * 10_000,
        "fee_bps_per_side": FEE_PER_SIDE * 10_000,
    }


def action_from_weights(weights: pd.DataFrame) -> pd.DataFrame:
    previous = weights.shift(1).fillna(0.0)
    action = pd.DataFrame("HOLD", index=weights.index, columns=weights.columns)
    action[(weights == 0) & (previous == 0)] = "CASH"
    action[(weights > 0) & (previous == 0)] = "ENTER_LONG"
    action[(weights < 0) & (previous == 0)] = "ENTER_SHORT"
    action[(weights == 0) & (previous != 0)] = "EXIT"
    action[(weights * previous < 0)] = "REVERSE"
    changed = (weights - previous).abs() > 1e-12
    same_side = (weights * previous > 0) & changed
    action[same_side] = "REBALANCE"
    return action


def build_signal_file(
    positions: dict[str, pd.DataFrame],
    regimes: dict[str, pd.DataFrame],
    diagnostics: dict[str, pd.DataFrame],
    allocations: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    actions = action_from_weights(allocations["Ensemble variable + HMM gate"])
    rows = []
    for date in allocations["Ensemble variable + HMM gate"].index:
        for symbol in SYMBOLS:
            row = {
                "date": date,
                "symbol": f"{symbol}USDT",
                "long_votes": int(diagnostics["long_votes"].loc[date, symbol]),
                "short_votes": int(diagnostics["short_votes"].loc[date, symbol]),
                "ensemble_direction": int(diagnostics["direction"].loc[date, symbol]),
                "ensemble_confidence": diagnostics["confidence"].loc[date, symbol],
                "hmm_regime": regimes["regime"].loc[date, symbol],
                "hmm_confidence": regimes["confidence"].loc[date, symbol],
                "hmm_crisis_probability": regimes["crisis_probability"].loc[date, symbol],
                "hmm_gate_multiplier": regimes["gate"].loc[date, symbol],
                "equal_weight": allocations["Ensemble equal"].loc[date, symbol],
                "equal_hmm_weight": allocations["Ensemble equal + HMM gate"].loc[date, symbol],
                "variable_weight": allocations["Ensemble variable"].loc[date, symbol],
                "recommended_weight": allocations["Ensemble variable + HMM gate"].loc[date, symbol],
                "recommended_action": actions.loc[date, symbol],
            }
            for label in ENSEMBLE_MODELS:
                key = label.lower().replace(" ", "_").replace("40d", "40d")
                row[f"{key}_position"] = int(positions[label].loc[date, symbol])
            rows.append(row)
    return pd.DataFrame(rows)


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    view = frame[columns].copy()
    for column in view.select_dtypes(include=["float"]).columns:
        view[column] = view[column].map(lambda value: f"{value:.2f}")
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in view.to_numpy()]
    return "\n".join([header, divider, *rows])


def write_report(
    output_root: Path,
    standalone: pd.DataFrame,
    comparison: pd.DataFrame,
    stress: pd.DataFrame,
    funding: pd.DataFrame,
    dates: pd.DatetimeIndex,
) -> None:
    top = standalone.iloc[0]
    recommended = comparison.loc[
        comparison["portfolio"] == "Ensemble variable + HMM gate"
    ].iloc[0]
    report = f"""# Six-coin USD-M futures validation

Generated from the frozen-parameter validation run on six Binance USD-M perpetuals: BTC, ETH, SOL, XRP, BNB, and DOGE.

## Test design

- Parameter/model-selection boundary: 2025-12-31. Neural weights are fit once on 2025-01-01 through 2025-12-31; there is no 2026 refit in the primary results.
- Reported holdout: {dates.min().date()} through {dates.max().date()}. The intended September endpoint is truncated because the common verified candle set ends on 2026-09-17 23:00 UTC.
- Instrument: Binance USD-M isolated perpetual futures at 1x notional exposure. These numbers are not a spot backtest.
- Freqtrade standalone costs: 10 bps per side fee, with no funding or slippage inside Freqtrade.
- Portfolio-layer costs: 10 bps fee plus 5 bps modeled slippage per one-way turnover, and observed Binance funding events.
- Ensemble: strict 3-of-5 majority across Bollinger, RNN, GRU, LSTM, and Transformer positions, sampled at 23:00 UTC and applied to the next daily return.
- HMM gate: trend 1.0, sideways 0.5, crisis/uncertain 0.0. The variable allocator uses inverse 30-day volatility, model-vote confidence, a 25% per-coin cap, and a 20% annualized portfolio-volatility ceiling. It never scales above 1x gross.

## Standalone Freqtrade results

{markdown_table(standalone, ['model', 'trades', 'return_pct', 'max_drawdown_pct', 'closed_trade_sharpe', 'profit_factor'])}

The strongest standalone result is **{top['model']}** at {top['return_pct']:.2f}%. The result dispersion is important: neural architecture choice matters, and the standalone HMM sleeves are negative in this holdout.

## Allocation validation after fee, slippage, and funding

{markdown_table(comparison, ['portfolio', 'return_pct', 'annualized_vol_pct', 'sharpe', 'max_drawdown_pct', 'avg_gross_exposure_pct', 'total_turnover_x'])}

The proposed variable/HMM portfolio returned {recommended['return_pct']:.2f}% with a {recommended['max_drawdown_pct']:.2f}% maximum drawdown under the base cost assumptions. Compare it directly with both the equal-weight and ungated variable rows; variable sizing is only justified if its risk-adjusted result is stronger, not by assumption.

## Slippage stress for the proposed portfolio

{markdown_table(stress, ['slippage_bps_per_side', 'return_pct', 'sharpe', 'max_drawdown_pct', 'slippage_drag_pct_simple'])}

Slippage is a scenario assumption because this workspace does not contain historical order-book snapshots. Funding is based on {len(funding):,} observed funding-rate events cached in `funding_rates.csv.gz`.

## Interpretation

- Treat the 2026 period as validation, not a new tuning set. Do not change thresholds after seeing these results unless a later period is reserved as a fresh test.
- HMM is more defensible here as a risk gate than as a standalone return engine: every tested standalone HMM variant lost money.
- The Transformer result is dominated by short trades, so it should not be presented as broad proof that deep learning is superior.
- Signals are hourly inside each strategy, but the portfolio overlay rebalances once daily at 23:00 UTC to control turnover and keep the allocation comparison causal.
- Spot deployment needs a separate long-only rerun: remove short positions and funding, then use spot fees and spot liquidity assumptions.

## Reproduction

The raw Freqtrade archives are under `freqtrade/validation_runs/2026_sixcoin`. Rebuild the portfolio outputs with:

```powershell
.\\.freqtrade-venv\\Scripts\\python.exe freqtrade/user_data/scripts/build_sixcoin_validation_report.py
```
"""
    (output_root / "validation_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)

    results, standalone = load_all_results(args.results_root)
    hourly = load_hourly_data(args.data_root)
    daily_close, daily_returns = build_daily_market(hourly)
    dates = pd.date_range(VALIDATION_START, VALIDATION_END, freq="1D")
    positions = trade_positions(results, dates)
    regimes = build_regime_gate(hourly, args.regime_model_root, dates)
    funding, daily_funding = load_funding(args.output_root, args.refresh_funding)
    allocations, diagnostics = make_allocations(positions, regimes, daily_returns, dates)

    paths = {}
    comparison_rows = []
    for name, weights in allocations.items():
        path = portfolio_path(weights, daily_returns, daily_funding, BASE_SLIPPAGE_PER_SIDE)
        paths[name] = path
        comparison_rows.append(summarize_path(name, path, BASE_SLIPPAGE_PER_SIDE))
    comparison = pd.DataFrame(comparison_rows).sort_values("return_pct", ascending=False)

    stress_rows = []
    recommended_weights = allocations["Ensemble variable + HMM gate"]
    for slippage_bps in (2.0, 5.0, 10.0):
        slippage = slippage_bps / 10_000
        path = portfolio_path(recommended_weights, daily_returns, daily_funding, slippage)
        stress_rows.append(summarize_path("Ensemble variable + HMM gate", path, slippage))
    stress = pd.DataFrame(stress_rows)

    signals = build_signal_file(positions, regimes, diagnostics, allocations)
    standalone.to_csv(args.output_root / "standalone_freqtrade_results.csv", index=False)
    comparison.to_csv(args.output_root / "portfolio_comparison.csv", index=False)
    stress.to_csv(args.output_root / "slippage_stress.csv", index=False)
    signals.to_csv(args.output_root / "ensemble_daily_signals.csv", index=False)
    daily_close.reindex(dates).to_csv(args.output_root / "daily_closing_prices.csv", index_label="date")

    weight_panels = []
    for name, weights in allocations.items():
        panel = weights.copy()
        panel.insert(0, "portfolio", name)
        panel.insert(0, "date", panel.index)
        weight_panels.append(panel.reset_index(drop=True))
    pd.concat(weight_panels, ignore_index=True).to_csv(
        args.output_root / "daily_target_weights.csv", index=False
    )

    path_panels = []
    for name, path in paths.items():
        panel = path.copy()
        panel.insert(0, "portfolio", name)
        panel.insert(0, "date", panel.index)
        path_panels.append(panel.reset_index(drop=True))
    pd.concat(path_panels, ignore_index=True).to_csv(
        args.output_root / "daily_portfolio_paths.csv", index=False
    )

    manifest = {
        "validation_start": str(dates.min()),
        "validation_end": str(dates.max()),
        "symbols": SYMBOLS,
        "instrument": "Binance USD-M isolated perpetual futures",
        "leverage": 1.0,
        "parameter_selection_cutoff": "2025-12-31",
        "neural_train_start": "2025-01-01",
        "neural_train_end_exclusive": "2026-01-01",
        "fee_per_side": FEE_PER_SIDE,
        "base_slippage_per_side": BASE_SLIPPAGE_PER_SIDE,
        "portfolio_vol_target": PORTFOLIO_VOL_TARGET,
        "per_coin_cap": PER_COIN_CAP,
        "result_archives": standalone.set_index("model")["archive"].to_dict(),
    }
    (args.output_root / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    write_report(args.output_root, standalone, comparison, stress, funding, dates)

    print(standalone[["model", "trades", "return_pct", "max_drawdown_pct"]].to_string(index=False))
    print()
    print(comparison[["portfolio", "return_pct", "sharpe", "max_drawdown_pct"]].to_string(index=False))
    print(f"\nWrote validation bundle to {args.output_root.resolve()}")


if __name__ == "__main__":
    main()
