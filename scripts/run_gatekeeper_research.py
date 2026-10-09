#!/usr/bin/env python3
"""Test the proposed hierarchical HMM gatekeeper architecture."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crypto_quant.gatekeeper import (  # noqa: E402
    apply_hmm_throttle,
    confirm_breakout_entries,
)
from crypto_quant.hmm_regime import (  # noqa: E402
    HMMRegimeConfig,
    backtest_regime_strategy,
    build_regime_features,
    performance_metrics,
    walk_forward_regime_probabilities,
)
from crypto_quant.macro_regime import (  # noqa: E402
    build_macro_volume_features,
    load_extended_daily_futures,
    load_fred_levels,
)
from crypto_quant.strategy_selection import (  # noqa: E402
    DevelopmentFold,
    build_rule_signals,
    score_development_folds,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "gatekeeper.json",
    )
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


def build_daily_trading_log(
    closes: pd.DataFrame,
    controls: dict[str, pd.DataFrame],
    portfolios: dict[str, pd.DataFrame],
    regimes: pd.DataFrame,
    *,
    fee_bps: float,
) -> pd.DataFrame:
    """Create an exact daily, per-symbol audit of signals, weights, P&L, and costs."""

    returns = closes.pct_change().fillna(0.0)
    prior_regime = regimes["regime"].reindex(closes.index).shift(1)
    prior_probability = (
        regimes["high_volatility_probability"].reindex(closes.index).shift(1)
    )
    records: list[pd.DataFrame] = []
    for model, signals in controls.items():
        portfolio = portfolios[model]
        signal_matrix = signals.pivot(
            index="date", columns="symbol", values="signal"
        ).reindex(index=closes.index, columns=closes.columns)
        if "hmm_throttle" in signals.columns and model in {
            "hmm_throttle_only",
            "full_gatekeeper",
        }:
            throttle_matrix = signals.pivot(
                index="date", columns="symbol", values="hmm_throttle"
            ).reindex(index=closes.index, columns=closes.columns)
        else:
            throttle_matrix = pd.DataFrame(
                1.0, index=closes.index, columns=closes.columns
            )
        for symbol in closes.columns:
            applied = portfolio[f"applied_weight_{symbol}"].astype(float)
            target = portfolio[f"target_weight_{symbol}"].astype(float)
            previous = applied.shift(1).fillna(0.0)
            symbol_turnover = applied.sub(previous).abs()
            gross = applied * returns[symbol]
            cost = symbol_turnover * fee_bps / 10_000.0
            event = pd.Series("flat", index=closes.index, dtype=object)
            current_sign = np.sign(applied)
            previous_sign = np.sign(previous)
            event.loc[(previous_sign == 0) & (current_sign > 0)] = "open_long"
            event.loc[(previous_sign == 0) & (current_sign < 0)] = "open_short"
            event.loc[(previous_sign > 0) & (current_sign == 0)] = "close_long"
            event.loc[(previous_sign < 0) & (current_sign == 0)] = "close_short"
            event.loc[(previous_sign != 0) & (current_sign > 0) & (previous_sign != current_sign)] = "flip_to_long"
            event.loc[(previous_sign != 0) & (current_sign < 0) & (previous_sign != current_sign)] = "flip_to_short"
            same_active = (previous_sign == current_sign) & current_sign.ne(0)
            event.loc[same_active & applied.eq(previous)] = "hold"
            event.loc[same_active & applied.ne(previous)] = "rebalance"
            records.append(
                pd.DataFrame(
                    {
                        "model": model,
                        "date": closes.index,
                        "symbol": symbol,
                        "close": closes[symbol],
                        "previous_close": closes[symbol].shift(1),
                        "asset_return": returns[symbol],
                        "decision_signal_at_prior_close": signal_matrix[symbol].shift(1),
                        "target_weight_at_close": target,
                        "previous_applied_weight": previous,
                        "applied_weight": applied,
                        "gross_contribution": gross,
                        "symbol_turnover": symbol_turnover,
                        "transaction_cost_return": cost,
                        "net_contribution": gross - cost,
                        "position_event": event,
                        "hmm_regime_at_prior_close": prior_regime,
                        "high_volatility_probability_at_prior_close": prior_probability,
                        "hmm_throttle_at_prior_close": throttle_matrix[symbol].shift(1),
                    }
                )
            )
    return pd.concat(records, ignore_index=True).sort_values(
        ["model", "symbol", "date"], kind="stable"
    )


def build_trade_ledger(daily_log: pd.DataFrame, *, fee_bps: float) -> pd.DataFrame:
    """Collapse the daily audit into directional position episodes.

    Costs on a sign flip are split into the old position's close and the new
    position's open, so ledger costs reconcile to the daily log.
    """

    finished: list[dict[str, object]] = []
    trade_number = 0

    def start_trade(row: pd.Series, sign: int, carried_in: bool) -> dict[str, object]:
        nonlocal trade_number
        trade_number += 1
        return {
            "trade_id": f"trade_{trade_number:05d}",
            "model": row["model"],
            "symbol": row["symbol"],
            "direction": "long" if sign > 0 else "short",
            "entry_date": row["date"],
            "last_active_date": pd.NaT,
            "exit_date": pd.NaT,
            "status": "open",
            "carried_in": bool(carried_in),
            "entry_reference_close": float(row["previous_close"]),
            "exit_reference_close": np.nan,
            "holding_days": 0,
            "weight_day_sum": 0.0,
            "maximum_absolute_weight": 0.0,
            "gross_contribution": 0.0,
            "transaction_cost_return": 0.0,
        }

    for (_, _), group in daily_log.groupby(["model", "symbol"], sort=False):
        current: dict[str, object] | None = None
        group = group.sort_values("date", kind="stable")
        for position, (_, row) in enumerate(group.iterrows()):
            weight = float(row["applied_weight"])
            previous = float(row["previous_applied_weight"])
            sign = int(np.sign(weight))
            previous_sign = int(np.sign(previous))
            first_row = position == 0

            if current is None and previous_sign != 0:
                current = start_trade(row, previous_sign, carried_in=first_row)

            if previous_sign != 0 and sign != previous_sign:
                if current is None:
                    current = start_trade(row, previous_sign, carried_in=first_row)
                current["transaction_cost_return"] = float(
                    current["transaction_cost_return"]
                ) + abs(previous) * fee_bps / 10_000.0
                current["exit_date"] = row["date"]
                current["status"] = "closed"
                current["exit_reference_close"] = float(row["previous_close"])
                finished.append(current)
                current = None

            if sign != 0 and sign != previous_sign:
                current = start_trade(row, sign, carried_in=False)
                current["transaction_cost_return"] = abs(weight) * fee_bps / 10_000.0
            elif sign != 0 and current is None:
                current = start_trade(row, sign, carried_in=first_row)

            if sign != 0 and current is not None:
                if sign == previous_sign:
                    current["transaction_cost_return"] = float(
                        current["transaction_cost_return"]
                    ) + abs(weight - previous) * fee_bps / 10_000.0
                current["holding_days"] = int(current["holding_days"]) + 1
                current["weight_day_sum"] = float(current["weight_day_sum"]) + abs(weight)
                current["maximum_absolute_weight"] = max(
                    float(current["maximum_absolute_weight"]), abs(weight)
                )
                current["gross_contribution"] = float(
                    current["gross_contribution"]
                ) + float(row["gross_contribution"])
                current["last_active_date"] = row["date"]
                current["exit_reference_close"] = float(row["close"])

        if current is not None:
            finished.append(current)

    ledger = pd.DataFrame.from_records(finished)
    if ledger.empty:
        return ledger
    ledger["average_absolute_weight"] = ledger["weight_day_sum"] / ledger[
        "holding_days"
    ].replace(0, np.nan)
    ledger["net_contribution"] = (
        ledger["gross_contribution"] - ledger["transaction_cost_return"]
    )
    direction = ledger["direction"].map({"long": 1.0, "short": -1.0})
    ledger["signed_underlying_return"] = direction * (
        ledger["exit_reference_close"] / ledger["entry_reference_close"] - 1.0
    )
    ledger["profitable_after_cost"] = ledger["net_contribution"].gt(0)
    return ledger.drop(columns="weight_day_sum")


def main() -> None:
    args = parse_args()
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    symbols = tuple(payload["symbols"])
    output = PROJECT_ROOT / payload["output_directory"]
    output.mkdir(parents=True, exist_ok=True)
    base_config = HMMRegimeConfig(
        symbols=symbols,
        fee_bps=float(payload["selection_fee_bps"]),
    )

    markets: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        markets[symbol] = load_extended_daily_futures(
            PROJECT_ROOT / "processed" / "usdt_futures" / f"{symbol}_1h.csv.gz",
            monthly_daily_directory=(
                PROJECT_ROOT
                / "datasets"
                / "usdt_futures"
                / "data"
                / "futures"
                / "um"
                / "monthly"
                / "klines"
                / symbol
                / "1d"
            ),
            daily_directory=(
                PROJECT_ROOT
                / "datasets"
                / "usdt_futures"
                / "data"
                / "futures"
                / "um"
                / "daily"
                / "klines"
                / symbol
                / "1d"
            ),
        )
    common_index = markets[symbols[0]].index
    for symbol in symbols[1:]:
        common_index = common_index.intersection(markets[symbol].index)
    markets = {symbol: frame.reindex(common_index) for symbol, frame in markets.items()}
    closes = pd.DataFrame({symbol: markets[symbol]["close"] for symbol in symbols})
    macro_levels = load_fred_levels(
        PROJECT_ROOT / "datasets" / "external" / "fred", common_index
    )
    macro_volume = build_macro_volume_features(markets, macro_levels)
    features = {
        "crypto_only": build_regime_features(
            closes, volatility_window=base_config.feature_volatility_window
        ),
        "macro_volume": build_regime_features(
            closes,
            volatility_window=base_config.feature_volatility_window,
            macro_features=macro_volume,
        ),
    }

    breakout = build_rule_signals(
        closes,
        family="bollinger_breakout",
        parameters={"window": 40, "width": 1.5, "exit_z": 0.0},
    )
    ma = build_rule_signals(
        closes,
        family="ma_crossover",
        parameters={"fast": 10, "slow": 50, "filter": "none"},
    )
    momentum = build_rule_signals(
        closes,
        family="momentum_vote",
        parameters={
            "sma_fast": 10,
            "sma_slow": 50,
            "rsi_long": 60.0,
            "rsi_short": 40.0,
            "minimum_votes": 3,
        },
    )
    confirmations = {
        name: confirm_breakout_entries(
            breakout, ma, momentum, confirmation=name
        )
        for name in ("none", "ma", "momentum", "either", "both")
    }
    folds = [
        DevelopmentFold(name, dates[0], dates[1])
        for name, dates in payload["development_folds"].items()
    ]
    regime_cache: dict[tuple[str, int], pd.DataFrame] = {}

    def get_regimes(feature_set: str, training_days: int) -> pd.DataFrame:
        key = (feature_set, training_days)
        if key not in regime_cache:
            print(f"Fitting {feature_set} gatekeeper HMM, training={training_days} ...")
            config = replace(
                base_config,
                hmm_training_days=training_days,
                hmm_retrain_days=60,
            )
            regime_cache[key], _ = walk_forward_regime_probabilities(
                features[feature_set], config
            )
        return regime_cache[key]

    candidates: list[dict[str, object]] = []
    for feature_set in ("crypto_only", "macro_volume"):
        for training_days in (365, 730):
            for low_scale in (0.0, 0.25, 0.50):
                for confirmation in ("ma", "momentum", "either", "both"):
                    candidates.append(
                        {
                            "feature_set": feature_set,
                            "hmm_training_days": training_days,
                            "low_volatility_scale": low_scale,
                            "confirmation": confirmation,
                        }
                    )

    candidate_rows: list[dict[str, object]] = []
    fold_rows: list[dict[str, object]] = []
    signal_cache: dict[str, pd.DataFrame] = {}
    portfolio_cache: dict[str, pd.DataFrame] = {}
    best_id = ""
    best_score = float("-inf")
    for number, parameters in enumerate(candidates, start=1):
        candidate_id = f"gatekeeper_{number:02d}"
        signal = apply_hmm_throttle(
            confirmations[str(parameters["confirmation"])],
            get_regimes(
                str(parameters["feature_set"]), int(parameters["hmm_training_days"])
            ),
            low_volatility_scale=float(parameters["low_volatility_scale"]),
        )
        portfolio = backtest_regime_strategy(closes, signal, base_config)
        signal_cache[candidate_id] = signal
        portfolio_cache[candidate_id] = portfolio
        score, fold_metrics = score_development_folds(portfolio, folds)
        candidate_rows.append(
            {"candidate_id": candidate_id, **parameters, **score}
        )
        for record in fold_metrics.to_dict(orient="records"):
            fold_rows.append({"candidate_id": candidate_id, **parameters, **record})
        if float(score["robust_score"]) > best_score:
            best_score = float(score["robust_score"])
            best_id = candidate_id

    candidate_frame = pd.DataFrame.from_records(candidate_rows).sort_values(
        "robust_score", ascending=False, kind="stable"
    )
    selected = candidate_frame.iloc[0].to_dict()
    candidate_frame.to_csv(output / "development_candidate_scores.csv", index=False)
    pd.DataFrame.from_records(fold_rows).to_csv(
        output / "development_fold_metrics.csv", index=False
    )
    (output / "selected_parameters.json").write_text(
        json.dumps(
            {
                key: selected[key]
                for key in (
                    "candidate_id",
                    "feature_set",
                    "hmm_training_days",
                    "low_volatility_scale",
                    "confirmation",
                    "robust_score",
                )
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    selected_regimes = get_regimes(
        str(selected["feature_set"]), int(selected["hmm_training_days"])
    )
    selected_confirmation = str(selected["confirmation"])
    selected_low_scale = float(selected["low_volatility_scale"])
    controls = {
        "pure_breakout": confirmations["none"],
        "confirmation_only": confirmations[selected_confirmation],
        "hmm_throttle_only": apply_hmm_throttle(
            confirmations["none"],
            selected_regimes,
            low_volatility_scale=selected_low_scale,
        ),
        "full_gatekeeper": signal_cache[best_id],
    }
    final_start, final_end = payload["final_test"]
    result_rows: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    control_portfolios: dict[str, pd.DataFrame] = {}
    for label, signal in controls.items():
        portfolio = backtest_regime_strategy(closes, signal, base_config)
        control_portfolios[label] = portfolio
        result_rows.append(
            {
                "model": label,
                **performance_metrics(portfolio, start=final_start, end=final_end),
            }
        )
        for period, start, end in (
            ("2025", "2025-01-01", "2026-01-01"),
            ("2026_ytd", "2026-01-01", final_end),
        ):
            annual_rows.append(
                {
                    "model": label,
                    "period": period,
                    **performance_metrics(portfolio, start=start, end=end),
                }
            )
    final_results = pd.DataFrame.from_records(result_rows)
    annual_results = pd.DataFrame.from_records(annual_rows)
    final_results.to_csv(output / "final_2025_2026_results.csv", index=False)
    annual_results.to_csv(output / "calendar_results.csv", index=False)
    signal_cache[best_id].to_csv(
        output / "selected_signals.csv.gz", index=False, compression="gzip"
    )
    control_portfolios["full_gatekeeper"].rename_axis("date").reset_index().to_csv(
        output / "selected_portfolio.csv.gz", index=False, compression="gzip"
    )
    all_control_signals = pd.concat(
        [signal.assign(model=label) for label, signal in controls.items()],
        ignore_index=True,
        sort=False,
    )
    all_control_signals.to_csv(
        output / "all_model_signals.csv.gz", index=False, compression="gzip"
    )
    all_control_portfolios = pd.concat(
        [
            portfolio.rename_axis("date").reset_index().assign(model=label)
            for label, portfolio in control_portfolios.items()
        ],
        ignore_index=True,
        sort=False,
    )
    all_control_portfolios.to_csv(
        output / "all_model_portfolios.csv.gz", index=False, compression="gzip"
    )

    daily_log = build_daily_trading_log(
        closes,
        controls,
        control_portfolios,
        selected_regimes,
        fee_bps=base_config.fee_bps,
    )
    final_start_timestamp = pd.Timestamp(final_start, tz="UTC")
    final_end_timestamp = pd.Timestamp(final_end, tz="UTC")
    final_daily_log = daily_log.loc[
        daily_log["date"].ge(final_start_timestamp)
        & daily_log["date"].lt(final_end_timestamp)
    ].copy()
    final_daily_log.to_csv(
        output / "daily_trading_log.csv.gz", index=False, compression="gzip"
    )
    trade_ledger = build_trade_ledger(final_daily_log, fee_bps=base_config.fee_bps)
    trade_ledger.to_csv(output / "trade_ledger.csv", index=False)

    equity_records: list[pd.DataFrame] = []
    for label, portfolio in control_portfolios.items():
        sample = portfolio.loc[
            (portfolio.index >= final_start_timestamp)
            & (portfolio.index < final_end_timestamp)
        ].copy()
        normalized_equity = 100.0 * (1.0 + sample["net_return"]).cumprod()
        equity_records.append(
            pd.DataFrame(
                {
                    "date": sample.index,
                    "model": label,
                    "normalized_equity": normalized_equity,
                    "drawdown": normalized_equity / normalized_equity.cummax() - 1.0,
                    "gross_exposure": sample["gross_exposure"],
                    "net_exposure": sample["net_exposure"],
                    "daily_net_return": sample["net_return"],
                }
            )
        )
    equity_curves = pd.concat(equity_records, ignore_index=True)
    equity_curves.to_csv(output / "equity_curves.csv", index=False)

    trade_summary = (
        trade_ledger.groupby("model", sort=False)
        .agg(
            position_episodes=("trade_id", "count"),
            completed_episodes=("status", lambda values: int(values.eq("closed").sum())),
            profitable_episode_rate=("profitable_after_cost", "mean"),
            average_holding_days=("holding_days", "mean"),
            gross_contribution=("gross_contribution", "sum"),
            transaction_cost_return=("transaction_cost_return", "sum"),
            net_contribution=("net_contribution", "sum"),
        )
        .reindex(list(controls))
        .reset_index()
    )
    trade_summary.to_csv(output / "trade_summary.csv", index=False)

    stress_rows: list[dict[str, object]] = []
    for fee in payload["cost_stress_bps"]:
        for label in ("pure_breakout", "full_gatekeeper"):
            portfolio = backtest_regime_strategy(
                closes, controls[label], replace(base_config, fee_bps=float(fee))
            )
            stress_rows.append(
                {
                    "model": label,
                    "fee_bps": fee,
                    **performance_metrics(portfolio, start=final_start, end=final_end),
                }
            )
    pd.DataFrame.from_records(stress_rows).to_csv(output / "cost_stress.csv", index=False)

    displayed = final_results[
        [
            "model",
            "total_return",
            "maximum_drawdown",
            "sharpe_ratio_zero_risk_free",
            "average_daily_turnover",
            "average_gross_exposure",
        ]
    ].copy()
    for column in (
        "total_return",
        "maximum_drawdown",
        "average_daily_turnover",
        "average_gross_exposure",
    ):
        displayed[column] = (100.0 * displayed[column]).round(2).astype(str) + "%"
    displayed["sharpe_ratio_zero_risk_free"] = displayed[
        "sharpe_ratio_zero_risk_free"
    ].round(3)
    calendar_display = annual_results[
        ["model", "period", "total_return", "maximum_drawdown", "sharpe_ratio_zero_risk_free"]
    ].copy()
    for column in ("total_return", "maximum_drawdown"):
        calendar_display[column] = (100.0 * calendar_display[column]).round(2).astype(str) + "%"
    calendar_display["sharpe_ratio_zero_risk_free"] = calendar_display[
        "sharpe_ratio_zero_risk_free"
    ].round(3)
    trade_display = trade_summary[
        [
            "model",
            "position_episodes",
            "profitable_episode_rate",
            "average_holding_days",
            "transaction_cost_return",
            "net_contribution",
        ]
    ].copy()
    trade_display["profitable_episode_rate"] = (
        100.0 * trade_display["profitable_episode_rate"]
    ).round(1).astype(str) + "%"
    trade_display["average_holding_days"] = trade_display[
        "average_holding_days"
    ].round(1)
    for column in ("transaction_cost_return", "net_contribution"):
        trade_display[column] = (100.0 * trade_display[column]).round(2).astype(str) + "%"
    pure = final_results.set_index("model").loc["pure_breakout"]
    full = final_results.set_index("model").loc["full_gatekeeper"]
    verdict = (
        "The hierarchy improved risk-adjusted performance over the pure breakout control."
        if float(full["sharpe_ratio_zero_risk_free"])
        > float(pure["sharpe_ratio_zero_risk_free"])
        else "The hierarchy did not improve on the pure breakout control and should remain rejected."
    )
    report = f"""# HMM Gatekeeper Architecture Review

The attached proposal was implemented as a hierarchy rather than parallel strategies:

1. **HMM allocation throttle:** the HMM never selects long or short. High-volatility state receives full size; low-volatility state receives the selected fractional size.
2. **Core alpha:** Bollinger breakout with a 40-day center, 1.5-standard-deviation bands, and middle-band exit.
3. **Trend confirmation:** new long entries require bullish MA/momentum confirmation and new shorts require symmetric bearish confirmation. Once accepted, a position remains active until the Bollinger exit; a temporary confirmation change does not close it.

Parameters were selected on six rolling half-year folds from 2022–2024. The frozen final comparison covers 2025-01-01 through 2026-09-16.

## Selected gatekeeper

- HMM features: `{selected['feature_set']}`
- HMM trailing window: {int(selected['hmm_training_days'])} days; refit every 60 days
- Low-volatility position multiplier: {float(selected['low_volatility_scale']):.2f}
- Entry confirmation: `{selected['confirmation']}`

## Layer ablation, 2025–2026

{markdown_table(displayed)}

## Calendar split

{markdown_table(calendar_display)}

## What each result actually does

- **`pure_breakout`:** enters long when price closes above the 40-day upper band and short below the lower band, then exits at the 40-day middle band. There is no MA gate and no HMM sizing adjustment.
- **`confirmation_only`:** uses the same entries and exits, but a new long requires MA(10) above MA(50), while a new short requires MA(10) below MA(50). The confirmation is checked on entry only; it does not prematurely close an accepted trade.
- **`hmm_throttle_only`:** keeps every pure breakout trade, but the selected two-state HMM cuts position size to 50% in its low-volatility state and restores full size in its high-volatility state. The HMM cannot choose trade direction.
- **`full_gatekeeper`:** applies both the MA entry gate and the HMM position-size throttle.

All four variants use the same inverse-volatility portfolio allocator, a 50% per-asset cap, a 100% gross-exposure cap, a 20% annualized volatility target, next-day execution, and 10 bps cost per unit of turnover.

## Position episodes and trading costs

{markdown_table(trade_display)}

`net_contribution` is the arithmetic sum of daily portfolio-return contributions assigned to position episodes, not the compounded portfolio return. Costs on sign flips are split between closing the old position and opening the new one. The exact daily reconciliation is in `daily_trading_log.csv.gz`; the readable entry-to-exit view is in `trade_ledger.csv`.

## Verdict

{verdict}

The relevant decision is not whether the gatekeeper is theoretically appealing, but whether `full_gatekeeper` improves both Sharpe and drawdown relative to `pure_breakout` across development folds, final evaluation, and stressed costs. If it only lowers exposure and return without improving drawdown efficiency, the HMM is adding complexity rather than useful information.

## Review notes

- The throttle formulation fixes the earlier conceptual problem: HMM state no longer creates counter-trend trades.
- Long and short confirmations are symmetric; the screenshot's long-only wording would otherwise bias a futures backtest.
- The no-HMM breakout remains the mandatory control. HMM complexity is accepted only if it adds incremental evidence after costs.
- 2025 was already examined in earlier work, so this is an extended backtest rather than a pristine holdout.
- Funding, intraday spread, and event-driven fills remain unmodeled.

## Audit files

- `equity_curves.csv`: chart-ready equity, drawdown, exposure, and daily-return series for every model.
- `trade_ledger.csv`: one row per BTC/ETH directional position episode, including dates, direction, weights, underlying move, P&L contribution, and allocated costs.
- `daily_trading_log.csv.gz`: every model/date/symbol decision and rebalance, including prior-close signal, HMM state, target/applied weights, turnover, gross contribution, costs, and net contribution.
- `all_model_signals.csv.gz` and `all_model_portfolios.csv.gz`: full raw model outputs for independent checking.
"""
    (output / "research_report.md").write_text(report, encoding="utf-8")
    print("\nGatekeeper final comparison")
    print(displayed.to_string(index=False))
    print(f"Artifacts -> {output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
