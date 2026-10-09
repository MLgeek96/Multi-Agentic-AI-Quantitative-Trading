from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crypto_quant.market_cycle_hmm import (  # noqa: E402
    ALTCOINS,
    SEASONS,
    bucket_returns,
    build_bucket_weights,
    build_cycle_features,
    causal_cycle_filter,
    fit_cycle_hmm,
)
from build_million_usdt_quality_report import (  # noqa: E402
    PORTFOLIO_ORDER,
    SYMBOLS,
    build_market_inputs,
    capacity_path,
    coin_pnl_attribution,
    load_daily_funding,
    load_weights,
    monte_carlo,
    summarize_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a causal BTC/ETH/altcoin-season HMM allocation report."
    )
    parser.add_argument(
        "--config", type=Path, default=Path("config/market_cycle_hmm.json")
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
        default=Path("freqtrade/reports/2026_market_cycle_hmm"),
    )
    return parser.parse_args()


def load_daily_close(data_root: Path) -> pd.DataFrame:
    closes = {}
    for symbol in SYMBOLS:
        frame = pd.read_feather(
            data_root / f"{symbol}_USDT_USDT-1h-futures.feather"
        )
        frame["date"] = pd.to_datetime(frame["date"], utc=True)
        closes[symbol] = (
            frame.sort_values("date")
            .set_index("date")["close"]
            .astype(float)
            .resample("1D")
            .last()
        )
    return pd.DataFrame(closes).sort_index().ffill()


def long_only_bucket_weights(index: pd.DatetimeIndex) -> pd.DataFrame:
    directions = pd.DataFrame(1.0, index=index, columns=SYMBOLS)
    return build_bucket_weights(directions)


def model_state_statistics(parameters: dict) -> pd.DataFrame:
    rows = []
    for state, values in parameters["state_statistics"].items():
        rows.append({"state": int(state), **values})
    return pd.DataFrame(rows).sort_values("state")


def cycle_validation_statistics(
    cycles: pd.DataFrame,
    returns_by_bucket: pd.DataFrame,
    dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    future_returns = returns_by_bucket.shift(-1).reindex(dates)
    cycle_rows = cycles.reindex(dates)
    expected_bucket = {
        "bitcoin_season": "bitcoin",
        "ethereum_season": "ethereum",
        "altcoin_season": "altcoins",
    }
    rows = []
    for season in SEASONS:
        mask = cycle_rows["cycle"] == season
        selected = future_returns.loc[mask].dropna(how="any")
        leader = selected.idxmax(axis=1) if not selected.empty else pd.Series(dtype=str)
        bucket = expected_bucket[season]
        rows.append(
            {
                "cycle": season,
                "days": int(mask.sum()),
                "share_of_validation_pct": mask.mean() * 100,
                "average_confidence_pct": cycle_rows.loc[
                    mask, "cycle_confidence"
                ].mean()
                * 100,
                "next_day_bitcoin_return_bps": selected["bitcoin"].mean() * 10_000,
                "next_day_ethereum_return_bps": selected["ethereum"].mean() * 10_000,
                "next_day_altcoin_return_bps": selected["altcoins"].mean() * 10_000,
                "expected_bucket": bucket,
                "expected_bucket_led_next_day_pct": (leader == bucket).mean() * 100
                if len(leader)
                else np.nan,
            }
        )
    return pd.DataFrame(rows)


def cycle_pnl_attribution(
    portfolio: str,
    path: pd.DataFrame,
    cycles: pd.DataFrame,
) -> pd.DataFrame:
    # A state known after day T close controls weights held over T+1.
    execution_cycle = cycles["cycle"].shift(1).reindex(path.index).fillna("unknown")
    daily_pnl = path["equity_usdt"] - path["equity_before_usdt"]
    frame = pd.DataFrame(
        {
            "portfolio": portfolio,
            "cycle": execution_cycle,
            "daily_pnl_usdt": daily_pnl,
            "net_return": path["net_return"],
        }
    )
    return (
        frame.groupby(["portfolio", "cycle"], as_index=False)
        .agg(
            days=("daily_pnl_usdt", "size"),
            net_pnl_usdt=("daily_pnl_usdt", "sum"),
            average_daily_return_bps=("net_return", lambda values: values.mean() * 10_000),
        )
        .sort_values(["portfolio", "cycle"])
    )


def markdown_table(frame: pd.DataFrame, columns: list[str], decimals: int = 2) -> str:
    view = frame[columns].copy()
    for column in view.select_dtypes(include=["float"]).columns:
        view[column] = view[column].map(lambda value: f"{value:,.{decimals}f}")
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(map(str, row)) + " |" for row in view.to_numpy()]
    return "\n".join([header, divider, *body])


def write_report(
    output_root: Path,
    config: dict,
    state_stats: pd.DataFrame,
    cycle_stats: pd.DataFrame,
    results: pd.DataFrame,
    monte_carlo_results: pd.DataFrame,
    cycle_pnl: pd.DataFrame,
    coin_pnl: pd.DataFrame,
    latest: pd.Series,
    fit: dict,
) -> None:
    equal_result = results.loc[results["portfolio"] == "Signal equal buckets"].iloc[0]
    tilt_result = results.loc[results["portfolio"] == "Signal 50/25/25 cycle tilt"].iloc[0]
    better = (
        "improved"
        if tilt_result["sharpe"] > equal_result["sharpe"]
        else "did not improve"
    )
    report = f"""# BTC, ETH, and altcoin-season HMM research

This extension tests the market-cycle hypothesis described in the referenced Binance Square post while preserving the original 2026 signal directions. The source is a third-party opinion article, so its Bitcoin-season, Ethereum-season, and altcoin-season narrative is treated as a testable hypothesis rather than a fact.

## Design

- Training: {config['training_start']} through {config['training_end']}; validation: {config['validation_start']} through {config['validation_end']}.
- Model: frozen three-state diagonal Gaussian HMM using 30-day relative momentum, normalized relative-strength shares, BTC/alt and ETH/BTC correlations, and alt breadth. No 2026 observations are used to fit, select, or label states.
- Mapping: each state receives one unique season label by maximizing its training-period mean 30-day relative momentum for the BTC, ETH, or four-coin alt bucket. Candidate fits are rejected unless every state actually favors its assigned bucket and every state occupies at least 10% of training observations.
- Causality: features are known after day T close; HMM state and target weights are applied to T+1 returns.
- Equal buckets: one third BTC, one third ETH, and one third altcoins. When all four alt signals are active, each has 8.33% absolute target weight. An inactive bucket remains cash.
- Experimental tilt: 50% to the HMM-favored bucket and 25% to each other bucket. It is compared against, not substituted for, equal buckets.
- Capital and costs: USDT {config['starting_equity_usdt']:,.0f}; {config['fee_bps_per_side']:.0f} bps fee and {config['slippage_bps_per_side']:.0f} bps slippage per side, observed funding, and the same square-root impact model as the USDT 1 million audit.

## Frozen HMM state mapping

{markdown_table(state_stats, ['state', 'label', 'observations', 'occupancy_pct', 'bitcoin_relative_momentum_30d', 'ethereum_relative_momentum_30d', 'altcoin_relative_momentum_30d'], decimals=4)}

Selected fit seed: {fit['selected_seed']}; log likelihood: {fit['log_likelihood']:.2f}; minimum state occupancy: {fit['minimum_state_occupancy'] * 100:.2f}%; minimum assigned-bucket semantic margin: {fit['minimum_semantic_margin'] * 100:.2f} percentage points; converged: {fit['converged']}.

## 2026 cycle mapping diagnostic

{markdown_table(cycle_stats, ['cycle', 'days', 'share_of_validation_pct', 'average_confidence_pct', 'next_day_bitcoin_return_bps', 'next_day_ethereum_return_bps', 'next_day_altcoin_return_bps', 'expected_bucket_led_next_day_pct'])}

The last available classification on **{latest.name.date()}** is **{latest['cycle']}** at {latest['cycle_confidence'] * 100:.2f}% confidence: BTC {latest['prob_bitcoin_season'] * 100:.2f}%, ETH {latest['prob_ethereum_season'] * 100:.2f}%, altcoins {latest['prob_altcoin_season'] * 100:.2f}%. This is the state at the data cutoff, not a current real-time signal.

## USDT 1 million portfolio comparison

{markdown_table(results, ['portfolio', 'final_equity_usdt', 'profit_usdt', 'return_pct', 'sharpe', 'max_drawdown_pct', 'total_turnover_x', 'market_impact_cost_usdt'])}

The 50/25/25 HMM tilt **{better}** Sharpe versus equal buckets in this validation. It reduced maximum drawdown, but also reduced final return and increased turnover. It must not be promoted merely because its final return is positive; the state labels were mapped in sample and the 2026 period is short.

## Monte Carlo comparison

{markdown_table(monte_carlo_results, ['portfolio', 'runs', 'positive_outcomes_pct', 'return_p05_pct', 'return_p50_pct', 'return_p95_pct', 'max_drawdown_p95_pct'])}

These are 1,000 five-day block-bootstrap paths with ±10% return and ±20% execution-cost perturbations. They measure sensitivity, not forecast probabilities.

## Net P&L by execution cycle

{markdown_table(cycle_pnl, ['portfolio', 'cycle', 'days', 'net_pnl_usdt', 'average_daily_return_bps'])}

## Equal-bucket signal portfolio: per-coin contribution

{markdown_table(coin_pnl, ['symbol', 'price_pnl_usdt', 'funding_cost_usdt', 'fee_cost_usdt', 'slippage_cost_usdt', 'market_impact_cost_usdt', 'net_pnl_usdt', 'share_of_total_pnl_pct'])}

## Interpretation and decision

1. The HMM is a probabilistic clustering of relative momentum, normalized relative strength, breadth, and correlation. It does not observe a literal market-cycle label.
2. One-to-one state naming prevents all three states from being called “Bitcoin season,” but it cannot guarantee that the names remain economically stable out of sample.
3. The post also suggests BTC dominance, order books, news, sentiment, and on-chain data. Those are not present in this historical dataset, so they are not claimed here.
4. The equal-bucket portfolio is the governance baseline because its one-third sleeves are transparent. The HMM tilt remains experimental unless it improves multiple untouched periods after all costs.
5. This experiment reuses the already-inspected 2026 period and therefore is not a new pristine holdout.
6. In 2026, the bucket named by the HMM led the following day only about one third of the time. The cycle state is therefore descriptive, not demonstrated as a short-horizon predictor. Its near-100% probabilities are model-relative and are not calibrated real-world probabilities.

This is research, not financial advice or authorization to trade.
"""
    (output_root / "market_cycle_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    daily_close = load_daily_close(args.data_root)
    features = build_cycle_features(
        daily_close,
        momentum_window=int(config["relative_momentum_window_days"]),
        correlation_window=int(config["correlation_window_days"]),
    )
    parameters = fit_cycle_hmm(
        features,
        training_start=config["training_start"],
        training_end=config["training_end"],
        seeds=[int(value) for value in config["hmm_seeds"]],
        minimum_state_occupancy=float(config["minimum_state_occupancy_pct"]) / 100,
    )
    cycles = causal_cycle_filter(features, parameters)
    parameters_path = output_root / "market_cycle_hmm_parameters.json"
    parameters_path.write_text(json.dumps(parameters, indent=2), encoding="utf-8")

    validation_start = pd.Timestamp(config["validation_start"], tz="UTC")
    validation_end = pd.Timestamp(config["validation_end"], tz="UTC")
    dates = pd.date_range(validation_start, validation_end, freq="D")
    source_weights = load_weights(args.source_report_root / "daily_target_weights.csv")
    source_equal = source_weights["Ensemble equal"].reindex(dates).fillna(0.0)
    directions = np.sign(source_equal)
    equal_buckets = build_bucket_weights(directions)
    cycle_tilt = build_bucket_weights(
        directions,
        cycles["cycle"].reindex(dates),
        favored_bucket_weight=float(config["cycle_tilt_weights"]["favored_bucket"]),
        other_bucket_weight=float(config["cycle_tilt_weights"]["other_bucket"]),
    )
    long_only = long_only_bucket_weights(dates)
    portfolios = {
        "Original variable allocator": source_weights["Ensemble variable"].reindex(dates).fillna(0.0),
        "Signal equal buckets": equal_buckets,
        "Signal 50/25/25 cycle tilt": cycle_tilt,
        "Long-only equal-bucket benchmark": long_only,
    }

    daily_returns, _, trailing_adv, trailing_volatility, _ = build_market_inputs(
        args.data_root, 30, 30, 20
    )
    daily_funding = load_daily_funding(args.source_report_root / "funding_rates.csv.gz")
    initial_equity = float(config["starting_equity_usdt"])
    fee_rate = float(config["fee_bps_per_side"]) / 10_000
    slippage_rate = float(config["slippage_bps_per_side"]) / 10_000
    impact_coefficient = float(config["market_impact_coefficient"])
    summary_rows = []
    path_frames = []
    capacity_frames = []
    pnl_frames = []
    cycle_pnl_frames = []
    monte_carlo_rows = []
    monte_carlo_frames = []
    paths: dict[str, pd.DataFrame] = {}

    for offset, (name, weights) in enumerate(portfolios.items()):
        path, capacity = capacity_path(
            weights,
            daily_returns,
            daily_funding,
            trailing_adv,
            trailing_volatility,
            initial_equity,
            fee_rate,
            slippage_rate,
            impact_coefficient,
        )
        paths[name] = path
        summary_rows.append(
            summarize_path(
                name,
                float(config["slippage_bps_per_side"]),
                path,
                capacity,
                initial_equity,
            )
        )
        exported_path = path.reset_index()
        exported_path.insert(1, "portfolio", name)
        path_frames.append(exported_path)
        if not capacity.empty:
            exported_capacity = capacity.copy()
            exported_capacity.insert(1, "portfolio", name)
            capacity_frames.append(exported_capacity)
        pnl_frames.append(
            coin_pnl_attribution(
                name,
                weights,
                path,
                daily_returns,
                daily_funding,
                trailing_adv,
                trailing_volatility,
                fee_rate,
                slippage_rate,
                impact_coefficient,
            )
        )
        cycle_pnl_frames.append(cycle_pnl_attribution(name, path, cycles))
        mc_summary, mc_paths = monte_carlo(
            name,
            path,
            1000,
            5,
            0.10,
            0.20,
            420 + offset,
        )
        monte_carlo_rows.append(mc_summary)
        monte_carlo_frames.append(mc_paths)

    results = pd.DataFrame(summary_rows)
    monte_carlo_results = pd.DataFrame(monte_carlo_rows)
    coin_pnl = pd.concat(pnl_frames, ignore_index=True)
    cycle_pnl = pd.concat(cycle_pnl_frames, ignore_index=True)
    state_stats = model_state_statistics(parameters)
    cycle_stats = cycle_validation_statistics(
        cycles,
        bucket_returns(daily_close),
        dates,
    )
    latest = cycles.reindex(dates).iloc[-1]

    cycles.loc[dates].reset_index(names="date").to_csv(
        output_root / "daily_cycle_probabilities.csv", index=False
    )
    features.loc[dates].reset_index(names="date").to_csv(
        output_root / "daily_cycle_features.csv", index=False
    )
    state_stats.to_csv(output_root / "training_state_statistics.csv", index=False)
    cycle_stats.to_csv(output_root / "validation_cycle_statistics.csv", index=False)
    results.to_csv(output_root / "portfolio_results.csv", index=False)
    monte_carlo_results.to_csv(output_root / "monte_carlo_summary.csv", index=False)
    pd.concat(monte_carlo_frames, ignore_index=True).to_csv(
        output_root / "monte_carlo_outcomes.csv.gz", index=False, compression="gzip"
    )
    coin_pnl.to_csv(output_root / "coin_pnl_attribution.csv", index=False)
    cycle_pnl.to_csv(output_root / "cycle_pnl_attribution.csv", index=False)
    pd.concat(path_frames, ignore_index=True).to_csv(
        output_root / "daily_portfolio_paths.csv.gz", index=False, compression="gzip"
    )
    pd.concat(capacity_frames, ignore_index=True).to_csv(
        output_root / "order_capacity_details.csv.gz", index=False, compression="gzip"
    )
    target_rows = []
    for name, weights in portfolios.items():
        exported = weights.reset_index(names="date")
        exported.insert(1, "portfolio", name)
        target_rows.append(exported)
    pd.concat(target_rows, ignore_index=True).to_csv(
        output_root / "daily_target_weights.csv", index=False
    )
    equal_coin_pnl = coin_pnl.loc[coin_pnl["portfolio"] == "Signal equal buckets"]
    write_report(
        output_root,
        config,
        state_stats,
        cycle_stats,
        results,
        monte_carlo_results,
        cycle_pnl,
        equal_coin_pnl,
        latest,
        parameters["fit"],
    )
    print(results[["portfolio", "return_pct", "sharpe", "max_drawdown_pct"]].to_string(index=False))
    print(
        f"Latest cycle: {latest['cycle']} ({latest['cycle_confidence'] * 100:.2f}% confidence)"
    )


if __name__ == "__main__":
    main()
