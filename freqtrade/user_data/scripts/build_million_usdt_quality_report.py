from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"]
PORTFOLIO_ORDER = [
    "Ensemble equal",
    "Ensemble equal + HMM gate",
    "Ensemble variable",
    "Ensemble variable + HMM gate",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reprice the frozen six-coin portfolios for a USD 1 million wallet."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/million_usdt_backtest.json"),
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("freqtrade/user_data/data/binanceusdm/futures"),
    )
    parser.add_argument(
        "--source-report-root",
        type=Path,
        default=Path("freqtrade/reports/2026_sixcoin_validation"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("freqtrade/reports/2026_million_usdt_quality"),
    )
    return parser.parse_args()


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_weights(path: Path) -> dict[str, pd.DataFrame]:
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    portfolios = {}
    for name in PORTFOLIO_ORDER:
        selected = frame.loc[frame["portfolio"] == name].set_index("date")
        if selected.empty:
            raise ValueError(f"Missing target weights for {name}")
        portfolios[name] = selected[SYMBOLS].astype(float).sort_index()
    return portfolios


def build_market_inputs(
    data_root: Path,
    adv_window: int,
    volatility_window: int,
    minimum_history: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    closes: dict[str, pd.Series] = {}
    quote_volumes: dict[str, pd.Series] = {}
    coverage_rows = []
    for symbol in SYMBOLS:
        path = data_root / f"{symbol}_USDT_USDT-1h-futures.feather"
        frame = pd.read_feather(path).sort_values("date")
        frame["date"] = pd.to_datetime(frame["date"], utc=True)
        indexed = frame.set_index("date")
        closes[symbol] = indexed["close"].astype(float).resample("1D").last()
        quote_volumes[symbol] = (
            indexed["close"].astype(float) * indexed["volume"].astype(float)
        ).resample("1D").sum(min_count=1)
        coverage_rows.append(
            {
                "symbol": symbol,
                "start": frame["date"].min(),
                "end": frame["date"].max(),
                "hourly_rows": len(frame),
            }
        )

    daily_close = pd.DataFrame(closes).sort_index().ffill()
    daily_returns = daily_close.pct_change(fill_method=None)
    daily_quote_volume = pd.DataFrame(quote_volumes).sort_index()
    trailing_adv = (
        daily_quote_volume.rolling(adv_window, min_periods=minimum_history).mean().shift(1)
    )
    trailing_volatility = (
        daily_returns.rolling(volatility_window, min_periods=minimum_history)
        .std(ddof=0)
        .shift(1)
    )
    coverage = pd.DataFrame(coverage_rows)
    return daily_returns, daily_quote_volume, trailing_adv, trailing_volatility, coverage


def load_daily_funding(path: Path) -> pd.DataFrame:
    funding = pd.read_csv(path)
    funding["funding_time"] = pd.to_datetime(
        funding["funding_time"], utc=True, format="mixed"
    )
    funding["date"] = funding["funding_time"].dt.floor("D")
    return (
        funding.pivot_table(
            index="date", columns="symbol", values="funding_rate", aggfunc="sum"
        )
        .reindex(columns=SYMBOLS)
        .fillna(0.0)
    )


def square_root_impact_rate(
    order_notional: pd.Series,
    trailing_adv: pd.Series,
    daily_volatility: pd.Series,
    coefficient: float,
) -> tuple[pd.Series, pd.Series]:
    safe_adv = trailing_adv.replace(0.0, np.nan)
    participation = (order_notional / safe_adv).clip(lower=0.0)
    rate = coefficient * daily_volatility.clip(lower=0.0) * np.sqrt(participation)
    rate = rate.where(order_notional > 0.0, 0.0)
    return rate.fillna(0.0), participation.fillna(0.0)


def capacity_path(
    weights: pd.DataFrame,
    daily_returns: pd.DataFrame,
    daily_funding: pd.DataFrame,
    trailing_adv: pd.DataFrame,
    trailing_volatility: pd.DataFrame,
    initial_equity: float,
    fee_rate: float,
    slippage_rate: float,
    impact_coefficient: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = weights.index
    asset_returns = daily_returns.reindex(dates)[SYMBOLS].fillna(0.0)
    funding = daily_funding.reindex(dates)[SYMBOLS].fillna(0.0)
    adv = trailing_adv.reindex(dates)[SYMBOLS]
    volatility = trailing_volatility.reindex(dates)[SYMBOLS]
    previous_weights = pd.Series(0.0, index=SYMBOLS)
    equity = float(initial_equity)
    path_rows = []
    capacity_rows = []

    for date in dates:
        target_weights = weights.loc[date].astype(float)
        held_weights = previous_weights.copy()
        weight_change = (target_weights - previous_weights).abs()
        order_notional = weight_change * equity
        impact_rate, participation = square_root_impact_rate(
            order_notional,
            adv.loc[date],
            volatility.loc[date],
            impact_coefficient,
        )
        impact_cost_by_symbol = weight_change * impact_rate
        turnover = float(weight_change.sum())
        price_return = float((held_weights * asset_returns.loc[date]).sum())
        funding_cost = float((held_weights * funding.loc[date]).sum())
        fee_cost = turnover * fee_rate
        slippage_cost = turnover * slippage_rate
        impact_cost = float(impact_cost_by_symbol.sum())
        net_return = (
            price_return - funding_cost - fee_cost - slippage_cost - impact_cost
        )
        equity_before = equity
        equity *= 1.0 + net_return

        path_rows.append(
            {
                "date": date,
                "price_return": price_return,
                "funding_cost": funding_cost,
                "fee_cost": fee_cost,
                "slippage_cost": slippage_cost,
                "market_impact_cost": impact_cost,
                "net_return": net_return,
                "turnover": turnover,
                "gross_exposure": float(target_weights.abs().sum()),
                "equity_before_usdt": equity_before,
                "equity_usdt": equity,
            }
        )
        for symbol in SYMBOLS:
            if order_notional[symbol] <= 0.0:
                continue
            capacity_rows.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "order_notional_usdt": order_notional[symbol],
                    "trailing_adv_usdt": adv.loc[date, symbol],
                    "participation_rate": participation[symbol],
                    "daily_volatility": volatility.loc[date, symbol],
                    "impact_rate": impact_rate[symbol],
                    "impact_cost_usdt": equity_before * impact_cost_by_symbol[symbol],
                }
            )
        previous_weights = target_weights

    return pd.DataFrame(path_rows).set_index("date"), pd.DataFrame(capacity_rows)


def summarize_path(
    portfolio: str,
    slippage_bps: float,
    path: pd.DataFrame,
    capacity: pd.DataFrame,
    initial_equity: float,
) -> dict:
    equity = path["equity_usdt"]
    net = path["net_return"]
    drawdown = equity / equity.cummax() - 1.0
    annual_volatility = net.std(ddof=0) * math.sqrt(365)
    capacity_nonempty = not capacity.empty
    return {
        "portfolio": portfolio,
        "slippage_bps_per_side": slippage_bps,
        "initial_equity_usdt": initial_equity,
        "final_equity_usdt": equity.iloc[-1],
        "profit_usdt": equity.iloc[-1] - initial_equity,
        "return_pct": (equity.iloc[-1] / initial_equity - 1.0) * 100,
        "annualized_volatility_pct": annual_volatility * 100,
        "sharpe": net.mean() * 365 / annual_volatility if annual_volatility > 0 else np.nan,
        "max_drawdown_pct": -drawdown.min() * 100,
        "total_turnover_x": path["turnover"].sum(),
        "fee_cost_usdt": (path["fee_cost"] * path["equity_before_usdt"]).sum(),
        "slippage_cost_usdt": (
            path["slippage_cost"] * path["equity_before_usdt"]
        ).sum(),
        "funding_cost_usdt": (
            path["funding_cost"] * path["equity_before_usdt"]
        ).sum(),
        "market_impact_cost_usdt": (
            path["market_impact_cost"] * path["equity_before_usdt"]
        ).sum(),
        "max_order_usdt": capacity["order_notional_usdt"].max()
        if capacity_nonempty
        else 0.0,
        "max_adv_participation_pct": capacity["participation_rate"].max() * 100
        if capacity_nonempty
        else 0.0,
        "p95_impact_bps": capacity["impact_rate"].quantile(0.95) * 10_000
        if capacity_nonempty
        else 0.0,
    }


def block_bootstrap_indices(
    length: int, block_size: int, rng: np.random.Generator
) -> np.ndarray:
    if length <= 0:
        return np.array([], dtype=int)
    block_size = max(1, min(block_size, length))
    starts = rng.integers(0, length - block_size + 1, size=math.ceil(length / block_size))
    return np.concatenate(
        [np.arange(start, start + block_size) for start in starts]
    )[:length]


def monte_carlo(
    portfolio: str,
    path: pd.DataFrame,
    runs: int,
    block_size: int,
    price_perturbation: float,
    cost_perturbation: float,
    seed: int,
) -> tuple[dict, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    price = path["price_return"].to_numpy()
    funding = path["funding_cost"].to_numpy()
    execution_cost = path[
        ["fee_cost", "slippage_cost", "market_impact_cost"]
    ].sum(axis=1).to_numpy()
    outcomes = []
    for run in range(runs):
        sampled = block_bootstrap_indices(len(path), block_size, rng)
        price_noise = rng.uniform(
            1.0 - price_perturbation, 1.0 + price_perturbation, len(path)
        )
        cost_noise = rng.uniform(
            1.0 - cost_perturbation, 1.0 + cost_perturbation, len(path)
        )
        simulated = (
            price[sampled] * price_noise
            - funding[sampled]
            - execution_cost[sampled] * cost_noise
        )
        equity = np.cumprod(1.0 + simulated)
        drawdown = equity / np.maximum.accumulate(equity) - 1.0
        outcomes.append(
            {
                "portfolio": portfolio,
                "run": run + 1,
                "return_pct": (equity[-1] - 1.0) * 100,
                "max_drawdown_pct": -drawdown.min() * 100,
            }
        )
    simulations = pd.DataFrame(outcomes)
    summary = {
        "portfolio": portfolio,
        "runs": runs,
        "positive_outcomes_pct": (simulations["return_pct"] > 0.0).mean() * 100,
        "return_p05_pct": simulations["return_pct"].quantile(0.05),
        "return_p50_pct": simulations["return_pct"].quantile(0.50),
        "return_p95_pct": simulations["return_pct"].quantile(0.95),
        "max_drawdown_p50_pct": simulations["max_drawdown_pct"].quantile(0.50),
        "max_drawdown_p95_pct": simulations["max_drawdown_pct"].quantile(0.95),
    }
    return summary, simulations


def half_gross_return(path: pd.DataFrame) -> float:
    execution_cost = path[
        ["fee_cost", "slippage_cost", "market_impact_cost"]
    ].sum(axis=1)
    decayed = 0.5 * path["price_return"] - path["funding_cost"] - execution_cost
    return ((1.0 + decayed).prod() - 1.0) * 100


def capacity_by_coin(capacity: pd.DataFrame) -> pd.DataFrame:
    if capacity.empty:
        return pd.DataFrame()
    return (
        capacity.groupby("symbol")
        .agg(
            orders=("order_notional_usdt", "size"),
            median_order_usdt=("order_notional_usdt", "median"),
            max_order_usdt=("order_notional_usdt", "max"),
            median_adv_usdt=("trailing_adv_usdt", "median"),
            max_participation_pct=("participation_rate", lambda values: values.max() * 100),
            p95_impact_bps=("impact_rate", lambda values: values.quantile(0.95) * 10_000),
            impact_cost_usdt=("impact_cost_usdt", "sum"),
        )
        .reindex(SYMBOLS)
        .reset_index()
    )


def coin_pnl_attribution(
    portfolio: str,
    weights: pd.DataFrame,
    path: pd.DataFrame,
    daily_returns: pd.DataFrame,
    daily_funding: pd.DataFrame,
    trailing_adv: pd.DataFrame,
    trailing_volatility: pd.DataFrame,
    fee_rate: float,
    slippage_rate: float,
    impact_coefficient: float,
) -> pd.DataFrame:
    dates = weights.index
    asset_returns = daily_returns.reindex(dates)[SYMBOLS].fillna(0.0)
    funding = daily_funding.reindex(dates)[SYMBOLS].fillna(0.0)
    adv = trailing_adv.reindex(dates)[SYMBOLS]
    volatility = trailing_volatility.reindex(dates)[SYMBOLS]
    previous_weights = pd.Series(0.0, index=SYMBOLS)
    totals = {
        symbol: {
            "price_pnl_usdt": 0.0,
            "funding_cost_usdt": 0.0,
            "fee_cost_usdt": 0.0,
            "slippage_cost_usdt": 0.0,
            "market_impact_cost_usdt": 0.0,
            "net_pnl_usdt": 0.0,
        }
        for symbol in SYMBOLS
    }
    for date in dates:
        target_weights = weights.loc[date].astype(float)
        weight_change = (target_weights - previous_weights).abs()
        equity_before = float(path.loc[date, "equity_before_usdt"])
        order_notional = weight_change * equity_before
        impact_rate, _ = square_root_impact_rate(
            order_notional,
            adv.loc[date],
            volatility.loc[date],
            impact_coefficient,
        )
        for symbol in SYMBOLS:
            price_pnl = (
                equity_before
                * previous_weights[symbol]
                * asset_returns.loc[date, symbol]
            )
            funding_cost = (
                equity_before * previous_weights[symbol] * funding.loc[date, symbol]
            )
            fee_cost = equity_before * weight_change[symbol] * fee_rate
            slippage_cost = equity_before * weight_change[symbol] * slippage_rate
            impact_cost = equity_before * weight_change[symbol] * impact_rate[symbol]
            net_pnl = (
                price_pnl - funding_cost - fee_cost - slippage_cost - impact_cost
            )
            totals[symbol]["price_pnl_usdt"] += price_pnl
            totals[symbol]["funding_cost_usdt"] += funding_cost
            totals[symbol]["fee_cost_usdt"] += fee_cost
            totals[symbol]["slippage_cost_usdt"] += slippage_cost
            totals[symbol]["market_impact_cost_usdt"] += impact_cost
            totals[symbol]["net_pnl_usdt"] += net_pnl
        previous_weights = target_weights

    attribution = pd.DataFrame.from_dict(totals, orient="index").reset_index(
        names="symbol"
    )
    attribution.insert(0, "portfolio", portfolio)
    total_pnl = attribution["net_pnl_usdt"].sum()
    attribution["share_of_total_pnl_pct"] = np.where(
        abs(total_pnl) > 1e-12,
        attribution["net_pnl_usdt"] / total_pnl * 100,
        np.nan,
    )
    return attribution


def make_quality_gate(
    coverage: pd.DataFrame,
    primary_results: pd.DataFrame,
    monte_carlo_results: pd.DataFrame,
    decay_results: pd.DataFrame,
) -> pd.DataFrame:
    variable = primary_results.loc[
        primary_results["portfolio"] == "Ensemble variable"
    ].iloc[0]
    variable_mc = monte_carlo_results.loc[
        monte_carlo_results["portfolio"] == "Ensemble variable"
    ].iloc[0]
    variable_decay = decay_results.loc[
        decay_results["portfolio"] == "Ensemble variable"
    ].iloc[0]
    minimum_start = pd.to_datetime(coverage["start"], utc=True).max().date()
    maximum_end = pd.to_datetime(coverage["end"], utc=True).min().date()
    monte_carlo_status = (
        "PASS" if variable_mc["positive_outcomes_pct"] >= 90.0 else "FAIL"
    )
    decay_status = "PASS" if variable_decay["half_gross_return_pct"] > 0.0 else "FAIL"
    rows = [
        ("1.1", "Data coverage", "PASS", f"Common six-coin history {minimum_start} to {maximum_end}; more than five years."),
        ("1.2", "Adjustment / roll handling", "NOT_APPLICABLE", "USD-M perpetuals do not expire or require a futures roll; raw exchange candles are used."),
        ("1.3", "Survivorship bias", "FAIL", "The universe contains six currently surviving liquid coins and no delisted-contract history."),
        ("1.4", "Timezone alignment", "PASS", "Candles, funding, signals, and portfolio dates are normalized to UTC."),
        ("2.1", "Look-ahead bias", "PARTIAL", "Portfolio weights are lagged one day and principal rule/HMM checks exist, but not every neural variant has a fresh automated look-ahead run."),
        ("2.2", "Data leakage", "PASS", "The primary models are frozen at 2025-12-31 and evaluated on 2026 without refitting."),
        ("2.3", "Feature calculation", "PARTIAL", "Indicators are causal and execution is delayed, but the entire feature set lacks a single end-to-end mutation test."),
        ("2.4", "Label definition", "PASS", "Future returns are training targets only; they are not available to the live feature matrix."),
        ("3.1", "OOS versus training performance", "FAIL", "Comparable training-return records are not stored for every final method, so the >50% ratio cannot be verified."),
        ("3.2", "Parameter stability +/-20%", "FAIL", "Bollinger has a coarse 20/40-day and 1.5/2.0/2.5 grid, not a complete +/-20% stability surface for every parameter and model."),
        ("3.3", "Multiple-testing control", "FAIL", "Many strategies were explored; no project-wide Bonferroni, deflated-Sharpe, or probability-of-backtest-overfitting correction is complete."),
        ("3.4", "Cross-period stability", "FAIL", "Several models and years fail the stated Sharpe >0.5 requirement."),
        ("4.1", "Commission", "PASS", "The capacity run charges 10 bps per side."),
        ("4.2", "Slippage", "PASS", "The capacity run reports 5, 10, 20, and 30 bps per-side scenarios."),
        ("4.3", "Market impact", "PARTIAL", f"Square-root impact is included; max modeled participation is {variable['max_adv_participation_pct']:.4f}% but no order-book replay is available."),
        ("4.4", "Funding costs", "PASS", "Observed Binance USD-M funding is charged at the portfolio layer."),
        ("5.1", "Walk-forward validation", "FAIL", "The studies use chronological folds, but the final combined system does not have at least ten rolling validations."),
        ("5.2", "Monte Carlo robustness", monte_carlo_status, f"{variable_mc['positive_outcomes_pct']:.1f}% of 1,000 block-bootstrap perturbations finish positive; threshold is 90%."),
        ("5.3", "Crisis stress test", "FAIL", "2020 and 2022 appear in development history, but there is no separate full-system OOS crisis test; 2008 predates crypto."),
        ("5.4", "50% return decay", decay_status, f"Halving gross price returns while retaining costs produces {variable_decay['half_gross_return_pct']:.2f}% for Ensemble variable."),
    ]
    return pd.DataFrame(rows, columns=["check_id", "check_item", "status", "evidence"])


def markdown_table(frame: pd.DataFrame, columns: list[str], decimals: int = 2) -> str:
    view = frame[columns].copy()
    for column in view.select_dtypes(include=["float"]).columns:
        view[column] = view[column].map(lambda value: f"{value:,.{decimals}f}")
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in view.to_numpy()]
    return "\n".join([header, divider, *rows])


def write_report(
    output_root: Path,
    config: dict,
    results: pd.DataFrame,
    primary: pd.DataFrame,
    by_coin: pd.DataFrame,
    coin_pnl: pd.DataFrame,
    monte_carlo_results: pd.DataFrame,
    decay_results: pd.DataFrame,
    gate: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    counts = gate["status"].value_counts()
    overall = "FAIL" if (gate["status"] == "FAIL").any() else "PASS"
    report = f"""# USD 1 million capacity and backtest-quality report

This report reprices the frozen six-coin 2026 portfolio weights from {start.date()} through {end.date()} with a starting wallet of **USDT {config['initial_equity_usdt']:,.0f}**. It adds a capacity-sensitive market-impact estimate and audits the research against the cited backtesting-pitfalls checklist.

## Result at the primary 10 bps slippage assumption

{markdown_table(primary, ['portfolio', 'initial_equity_usdt', 'final_equity_usdt', 'profit_usdt', 'return_pct', 'sharpe', 'max_drawdown_pct', 'market_impact_cost_usdt'])}

These are portfolio-layer results. The target weights are unchanged from the frozen 2026 run, so differences from the earlier percentage results come from increasing slippage from 5 to 10 bps and adding the square-root market-impact estimate. Starting capital alone does not multiply percentage return; it converts the return into dollar P&L and can change return only through capacity-dependent costs.

## Slippage stress

{markdown_table(results, ['portfolio', 'slippage_bps_per_side', 'final_equity_usdt', 'profit_usdt', 'return_pct', 'max_drawdown_pct'])}

## Per-coin capacity for Ensemble variable

{markdown_table(by_coin, ['symbol', 'orders', 'median_order_usdt', 'max_order_usdt', 'median_adv_usdt', 'max_participation_pct', 'p95_impact_bps', 'impact_cost_usdt'], decimals=4)}

Capacity model: `impact rate = daily volatility × sqrt(order notional / trailing ADV)`. ADV and volatility use 30 prior days and are shifted one day, so the execution estimate does not use future liquidity or volatility. Quote volume is approximated as the sum of hourly `close × base volume`. This is an analytical approximation, not historical order-book reconstruction.

## Per-coin dollar P&L attribution for Ensemble variable

{markdown_table(coin_pnl, ['symbol', 'price_pnl_usdt', 'funding_cost_usdt', 'fee_cost_usdt', 'slippage_cost_usdt', 'market_impact_cost_usdt', 'net_pnl_usdt', 'share_of_total_pnl_pct'])}

The six net contributions add exactly to portfolio profit. A negative funding-cost number is a funding credit. Because capital compounds, these are dollar contributions calculated from each day's pre-return equity, not standalone per-coin backtests.

## Monte Carlo robustness

{markdown_table(monte_carlo_results, ['portfolio', 'runs', 'positive_outcomes_pct', 'return_p05_pct', 'return_p50_pct', 'return_p95_pct', 'max_drawdown_p95_pct'])}

The simulation uses 1,000 five-day block-bootstrap paths, perturbs price returns by ±10%, and perturbs fees, slippage, and impact by ±20%. It is a robustness distribution, not a forecast probability.

## 50% gross-return decay

{markdown_table(decay_results, ['portfolio', 'base_return_pct', 'half_gross_return_pct'])}

Gross market P&L is halved while observed funding and all execution costs remain fully charged.

## Line-by-line quality gate

Overall status: **{overall}** — {counts.get('PASS', 0)} PASS, {counts.get('PARTIAL', 0)} PARTIAL, {counts.get('FAIL', 0)} FAIL, and {counts.get('NOT_APPLICABLE', 0)} not applicable.

{markdown_table(gate, ['check_id', 'check_item', 'status', 'evidence'])}

The strict rule is therefore **no live deployment yet**. The modelled USDT 1 million order sizes are small relative to reported exchange volume, but liquidity is not the main research blocker. Survivorship bias, incomplete project-wide multiple-testing correction, fewer than ten final walk-forward validations, and the absence of a separate crisis OOS test remain unresolved.

## Reproduction

```powershell
& '.\\.freqtrade-venv\\Scripts\\python.exe' 'freqtrade/user_data/scripts/build_million_usdt_quality_report.py'
```

Inputs and assumptions are frozen in `config/million_usdt_backtest.json`. Detailed daily paths, individual Monte Carlo outcomes, the quality-gate CSV, and the per-coin capacity table are saved beside this report.

This is research, not financial advice or authorization to trade.
"""
    (output_root / "million_usdt_quality_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    portfolios = load_weights(args.source_report_root / "daily_target_weights.csv")
    market = config["market_impact"]
    daily_returns, daily_volume, trailing_adv, trailing_volatility, coverage = (
        build_market_inputs(
            args.data_root,
            int(market["adv_window_days"]),
            int(market["volatility_window_days"]),
            int(market["minimum_history_days"]),
        )
    )
    daily_funding = load_daily_funding(args.source_report_root / "funding_rates.csv.gz")
    initial_equity = float(config["initial_equity_usdt"])
    fee_rate = float(config["fee_bps_per_side"]) / 10_000
    primary_bps = float(config["primary_slippage_bps_per_side"])
    summaries = []
    all_paths = []
    all_capacity = []
    primary_paths: dict[str, pd.DataFrame] = {}
    primary_capacity: dict[str, pd.DataFrame] = {}

    for portfolio, weights in portfolios.items():
        for slippage_bps in config["slippage_scenarios_bps_per_side"]:
            path, capacity = capacity_path(
                weights,
                daily_returns,
                daily_funding,
                trailing_adv,
                trailing_volatility,
                initial_equity,
                fee_rate,
                float(slippage_bps) / 10_000,
                float(market["coefficient"]),
            )
            summaries.append(
                summarize_path(
                    portfolio,
                    float(slippage_bps),
                    path,
                    capacity,
                    initial_equity,
                )
            )
            exported_path = path.reset_index()
            exported_path.insert(1, "portfolio", portfolio)
            exported_path.insert(2, "slippage_bps_per_side", float(slippage_bps))
            all_paths.append(exported_path)
            if not capacity.empty:
                exported_capacity = capacity.copy()
                exported_capacity.insert(1, "portfolio", portfolio)
                exported_capacity.insert(2, "slippage_bps_per_side", float(slippage_bps))
                all_capacity.append(exported_capacity)
            if float(slippage_bps) == primary_bps:
                primary_paths[portfolio] = path
                primary_capacity[portfolio] = capacity

    results = pd.DataFrame(summaries)
    primary = results.loc[results["slippage_bps_per_side"] == primary_bps].copy()
    monte_carlo_rows = []
    simulation_frames = []
    decay_rows = []
    mc = config["monte_carlo"]
    for offset, portfolio in enumerate(PORTFOLIO_ORDER):
        path = primary_paths[portfolio]
        summary, simulations = monte_carlo(
            portfolio,
            path,
            int(mc["runs"]),
            int(mc["block_size_days"]),
            float(mc["price_return_perturbation_pct"]) / 100,
            float(mc["execution_cost_perturbation_pct"]) / 100,
            int(mc["random_seed"]) + offset,
        )
        monte_carlo_rows.append(summary)
        simulation_frames.append(simulations)
        base_return = primary.loc[primary["portfolio"] == portfolio, "return_pct"].iloc[0]
        decay_rows.append(
            {
                "portfolio": portfolio,
                "base_return_pct": base_return,
                "half_gross_return_pct": half_gross_return(path),
            }
        )

    monte_carlo_results = pd.DataFrame(monte_carlo_rows)
    decay_results = pd.DataFrame(decay_rows)
    by_coin = capacity_by_coin(primary_capacity["Ensemble variable"])
    coin_pnl_frames = []
    for portfolio in PORTFOLIO_ORDER:
        coin_pnl_frames.append(
            coin_pnl_attribution(
                portfolio,
                portfolios[portfolio],
                primary_paths[portfolio],
                daily_returns,
                daily_funding,
                trailing_adv,
                trailing_volatility,
                fee_rate,
                primary_bps / 10_000,
                float(market["coefficient"]),
            )
        )
    coin_pnl = pd.concat(coin_pnl_frames, ignore_index=True)
    variable_coin_pnl = coin_pnl.loc[
        coin_pnl["portfolio"] == "Ensemble variable"
    ].copy()
    expected_profit = primary.loc[
        primary["portfolio"] == "Ensemble variable", "profit_usdt"
    ].iloc[0]
    if not math.isclose(
        variable_coin_pnl["net_pnl_usdt"].sum(), expected_profit, abs_tol=1e-6
    ):
        raise RuntimeError("Per-coin P&L attribution does not reconcile to portfolio profit")
    gate = make_quality_gate(coverage, primary, monte_carlo_results, decay_results)

    results.to_csv(output_root / "portfolio_capacity_results.csv", index=False)
    pd.concat(all_paths, ignore_index=True).to_csv(
        output_root / "daily_capacity_paths.csv.gz", index=False, compression="gzip"
    )
    pd.concat(all_capacity, ignore_index=True).to_csv(
        output_root / "order_capacity_details.csv.gz", index=False, compression="gzip"
    )
    by_coin.to_csv(output_root / "ensemble_variable_capacity_by_coin.csv", index=False)
    coin_pnl.to_csv(output_root / "coin_pnl_attribution.csv", index=False)
    monte_carlo_results.to_csv(output_root / "monte_carlo_summary.csv", index=False)
    pd.concat(simulation_frames, ignore_index=True).to_csv(
        output_root / "monte_carlo_outcomes.csv.gz", index=False, compression="gzip"
    )
    decay_results.to_csv(output_root / "return_decay_results.csv", index=False)
    gate.to_csv(output_root / "quality_gate.csv", index=False)
    coverage.to_csv(output_root / "data_coverage.csv", index=False)
    daily_volume.loc[
        portfolios[PORTFOLIO_ORDER[0]].index.min() : portfolios[PORTFOLIO_ORDER[0]].index.max()
    ].to_csv(output_root / "daily_quote_volume.csv.gz", compression="gzip")
    write_report(
        output_root,
        config,
        results,
        primary,
        by_coin,
        variable_coin_pnl,
        monte_carlo_results,
        decay_results,
        gate,
        portfolios[PORTFOLIO_ORDER[0]].index.min(),
        portfolios[PORTFOLIO_ORDER[0]].index.max(),
    )
    print(primary[["portfolio", "final_equity_usdt", "return_pct", "max_drawdown_pct"]].to_string(index=False))
    print(f"Quality gate: {(gate['status'] == 'PASS').sum()} PASS, {(gate['status'] == 'PARTIAL').sum()} PARTIAL, {(gate['status'] == 'FAIL').sum()} FAIL")


if __name__ == "__main__":
    main()
