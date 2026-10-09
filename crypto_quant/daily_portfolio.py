"""Daily adaptive trend portfolio and paper-account workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .binance_public import BinancePublicClient
from .data_quality import audit_ohlcv, require_quality, write_audit


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DailyConfig:
    symbols: tuple[str, ...]
    api_base_url: str
    eligibility_cutoff: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    initial_equity: float
    history_days: int
    parameter_training_days: int
    volatility_window_days: int
    covariance_window_days: int
    target_annual_volatility: float
    minimum_training_sharpe: float
    signal_model: str
    bollinger_window: int
    bollinger_standard_deviations: float
    rsi_period: int
    rsi_long_minimum: float
    rsi_long_maximum: float
    max_asset_weight: float
    fee_bps: float
    parameter_grid: tuple[tuple[int, int], ...]
    output_directory: Path


def load_daily_config(path: str | Path) -> DailyConfig:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    symbols = tuple(str(value).upper() for value in payload["symbols"])
    if len(symbols) < 2 or len(set(symbols)) != len(symbols):
        raise ValueError("symbols must contain at least two unique instruments")
    grid = tuple((int(fast), int(slow)) for fast, slow in payload["parameter_grid"])
    if not grid or any(fast <= 1 or fast >= slow for fast, slow in grid):
        raise ValueError("each parameter pair must satisfy 1 < fast < slow")
    max_weight = float(payload["max_asset_weight"])
    if not 0 < max_weight <= 1:
        raise ValueError("max_asset_weight must be in (0, 1]")
    signal_model = str(payload.get("signal_model", "adaptive_trend"))
    if signal_model not in {"adaptive_trend", "trend_bb_rsi"}:
        raise ValueError("signal_model must be 'adaptive_trend' or 'trend_bb_rsi'")
    output = Path(payload["output_directory"])
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    return DailyConfig(
        symbols=symbols,
        api_base_url=str(payload["api_base_url"]),
        eligibility_cutoff=_utc(payload["eligibility_cutoff"]),
        test_start=_utc(payload["test_start"]),
        test_end=_utc(payload["test_end"]),
        initial_equity=float(payload["initial_equity"]),
        history_days=int(payload["history_days"]),
        parameter_training_days=int(payload["parameter_training_days"]),
        volatility_window_days=int(payload["volatility_window_days"]),
        covariance_window_days=int(payload["covariance_window_days"]),
        target_annual_volatility=float(payload["target_annual_volatility"]),
        minimum_training_sharpe=float(payload.get("minimum_training_sharpe", 0.0)),
        signal_model=signal_model,
        bollinger_window=int(payload.get("bollinger_window", 20)),
        bollinger_standard_deviations=float(
            payload.get("bollinger_standard_deviations", 2.0)
        ),
        rsi_period=int(payload.get("rsi_period", 14)),
        rsi_long_minimum=float(payload.get("rsi_long_minimum", 45.0)),
        rsi_long_maximum=float(payload.get("rsi_long_maximum", 70.0)),
        max_asset_weight=max_weight,
        fee_bps=float(payload["fee_bps"]),
        parameter_grid=grid,
        output_directory=output,
    )


def fit_adaptive_trend(
    close: pd.Series,
    parameter_grid: Iterable[tuple[int, int]],
    *,
    training_days: int,
    fee_bps: float,
    volatility_window: int,
    minimum_training_sharpe: float = 0.0,
    signal_model: str = "adaptive_trend",
    bollinger_window: int = 20,
    bollinger_standard_deviations: float = 2.0,
    rsi_period: int = 14,
    rsi_long_minimum: float = 45.0,
    rsi_long_maximum: float = 70.0,
) -> dict[str, float | int]:
    """Select a moving-average pair on trailing data and forecast the next day."""

    close = close.dropna().astype(float)
    returns = close.pct_change()
    rsi = _rsi(close, rsi_period)
    bollinger_middle = close.rolling(bollinger_window).mean()
    bollinger_std = close.rolling(bollinger_window).std(ddof=0)
    bollinger_upper = bollinger_middle + bollinger_standard_deviations * bollinger_std
    bollinger_lower = bollinger_middle - bollinger_standard_deviations * bollinger_std
    indicator_confirmation = (
        rsi.between(rsi_long_minimum, rsi_long_maximum, inclusive="both")
        & close.ge(bollinger_lower)
        & close.le(bollinger_upper)
    )
    best: dict[str, float | int] | None = None
    for fast, slow in parameter_grid:
        if len(close) < slow + training_days:
            continue
        fast_average = close.rolling(fast).mean()
        slow_average = close.rolling(slow).mean()
        trend_position = fast_average.gt(slow_average)
        if signal_model == "adaptive_trend":
            position = trend_position.astype(float)
        elif signal_model == "trend_bb_rsi":
            position = (trend_position & indicator_confirmation).astype(float)
        else:
            raise ValueError(f"Unknown signal_model {signal_model!r}")
        turnover = position.diff().abs().fillna(0.0)
        strategy_returns = position.shift(1) * returns - turnover * fee_bps / 10_000.0
        sample = strategy_returns.dropna().iloc[-training_days:]
        standard_deviation = float(sample.std(ddof=1))
        sharpe = (
            float(sample.mean()) / standard_deviation * sqrt(365)
            if len(sample) > 30 and standard_deviation > 0
            else -np.inf
        )
        candidate: dict[str, float | int] = {
            "fast_window": fast,
            "slow_window": slow,
            "training_sharpe": sharpe,
            "signal": int(position.iloc[-1]),
            "trend_signal": int(trend_position.iloc[-1]),
            "indicator_confirmation": int(indicator_confirmation.iloc[-1]),
            "trend_spread": float(fast_average.iloc[-1] / slow_average.iloc[-1] - 1.0),
        }
        if best is None or (candidate["training_sharpe"], -slow, -fast) > (
            best["training_sharpe"],
            -int(best["slow_window"]),
            -int(best["fast_window"]),
        ):
            best = candidate
    if best is None:
        raise ValueError("Not enough history to fit any parameter pair")
    best["signal"] = int(
        int(best["signal"]) == 1
        and float(best["training_sharpe"]) >= minimum_training_sharpe
    )
    realized_volatility = returns.iloc[-volatility_window:].std(ddof=1) * sqrt(365)
    best["annualized_volatility"] = float(realized_volatility)
    best["close"] = float(close.iloc[-1])
    best["rsi"] = float(rsi.iloc[-1])
    best["bollinger_middle"] = float(bollinger_middle.iloc[-1])
    best["bollinger_upper"] = float(bollinger_upper.iloc[-1])
    best["bollinger_lower"] = float(bollinger_lower.iloc[-1])
    best["bollinger_percent_b"] = float(
        (close.iloc[-1] - bollinger_lower.iloc[-1])
        / (bollinger_upper.iloc[-1] - bollinger_lower.iloc[-1])
    )
    return best


def capped_inverse_volatility_weights(
    models: dict[str, dict[str, float | int]],
    returns: pd.DataFrame,
    *,
    max_asset_weight: float,
    target_annual_volatility: float,
    covariance_window: int,
) -> dict[str, float]:
    """Allocate active long signals, cap concentration, and scale to a vol target."""

    active = {
        symbol: 1.0 / max(float(model["annualized_volatility"]), 0.05)
        for symbol, model in models.items()
        if int(model["signal"]) == 1 and np.isfinite(float(model["annualized_volatility"]))
    }
    weights = {symbol: 0.0 for symbol in models}
    if not active:
        return weights

    remaining_weight = 1.0
    remaining = dict(active)
    while remaining and remaining_weight > 1e-12:
        denominator = sum(remaining.values())
        proposed = {
            symbol: remaining_weight * score / denominator for symbol, score in remaining.items()
        }
        capped = [symbol for symbol, weight in proposed.items() if weight > max_asset_weight]
        if not capped:
            for symbol, weight in proposed.items():
                weights[symbol] += weight
            break
        for symbol in capped:
            allocation = min(max_asset_weight - weights[symbol], remaining_weight)
            weights[symbol] += allocation
            remaining_weight -= allocation
            remaining.pop(symbol)

    ordered = list(models)
    vector = np.array([weights[symbol] for symbol in ordered], dtype=float)
    sample = returns.reindex(columns=ordered).dropna().iloc[-covariance_window:]
    if len(sample) >= 20 and vector.sum() > 0:
        covariance = sample.cov().to_numpy(dtype=float) * 365.0
        portfolio_variance = float(vector @ covariance @ vector)
        portfolio_volatility = sqrt(max(portfolio_variance, 0.0))
        if portfolio_volatility > target_annual_volatility > 0:
            scale = target_annual_volatility / portfolio_volatility
            weights = {symbol: weight * scale for symbol, weight in weights.items()}
    return weights


def compute_daily_decision(
    closes: pd.DataFrame, as_of: pd.Timestamp, config: DailyConfig
) -> tuple[pd.DataFrame, dict[str, float]]:
    history = closes.loc[closes.index <= as_of, list(config.symbols)].dropna(how="any")
    maximum_slow_window = max(slow for _, slow in config.parameter_grid)
    required_history = max(
        config.parameter_training_days + maximum_slow_window + 5,
        config.covariance_window_days + 5,
    )
    history = history.iloc[-required_history:]
    models = {
        symbol: fit_adaptive_trend(
            history[symbol],
            config.parameter_grid,
            training_days=config.parameter_training_days,
            fee_bps=config.fee_bps,
            volatility_window=config.volatility_window_days,
            minimum_training_sharpe=config.minimum_training_sharpe,
            signal_model=config.signal_model,
            bollinger_window=config.bollinger_window,
            bollinger_standard_deviations=config.bollinger_standard_deviations,
            rsi_period=config.rsi_period,
            rsi_long_minimum=config.rsi_long_minimum,
            rsi_long_maximum=config.rsi_long_maximum,
        )
        for symbol in config.symbols
    }
    weights = capped_inverse_volatility_weights(
        models,
        history.pct_change(),
        max_asset_weight=config.max_asset_weight,
        target_annual_volatility=config.target_annual_volatility,
        covariance_window=config.covariance_window_days,
    )
    records = []
    for symbol, model in models.items():
        records.append(
            {
                "date": as_of.date().isoformat(),
                "symbol": symbol,
                **model,
                "target_weight": weights[symbol],
                "cash_weight": max(0.0, 1.0 - sum(weights.values())),
            }
        )
    return pd.DataFrame.from_records(records), weights


def backtest_daily_portfolio(
    closes: pd.DataFrame,
    config: DailyConfig,
    *,
    start: pd.Timestamp | str,
    end: pd.Timestamp | str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Walk a period one close at a time with daily model re-estimation."""

    start = _utc(start)
    end = _utc(end)
    decision_dates = closes.index[(closes.index >= start) & (closes.index < end)]
    state: dict[str, Any] | None = None
    signals: list[pd.DataFrame] = []
    portfolio: list[dict[str, object]] = []
    orders: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []
    for decision_date in decision_dates:
        try:
            daily_signals, weights = compute_daily_decision(closes, decision_date, config)
        except ValueError as error:
            if "Not enough history" in str(error):
                continue
            raise
        prices = {symbol: float(closes.loc[decision_date, symbol]) for symbol in config.symbols}
        state, daily_record, daily_orders, daily_trades = update_paper_state(
            state,
            date=decision_date,
            prices=prices,
            weights=weights,
            config=config,
        )
        signals.append(daily_signals)
        portfolio.append(daily_record)
        orders.extend(daily_orders)
        trades.extend(daily_trades)
    return (
        pd.concat(signals, ignore_index=True) if signals else pd.DataFrame(),
        pd.DataFrame.from_records(portfolio),
        pd.DataFrame.from_records(orders),
        pd.DataFrame.from_records(trades),
    )


def update_paper_state(
    state: dict[str, Any] | None,
    *,
    date: pd.Timestamp,
    prices: dict[str, float],
    weights: dict[str, float],
    config: DailyConfig,
) -> tuple[dict[str, Any], dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    """Mark the paper account, charge turnover costs, and rebalance at the close."""

    if state is None:
        state = {
            "last_date": None,
            "equity": config.initial_equity,
            "peak_equity": config.initial_equity,
            "cash": config.initial_equity,
            "units": {symbol: 0.0 for symbol in config.symbols},
            "episodes": {symbol: None for symbol in config.symbols},
            "benchmark_btc_units": config.initial_equity / prices[config.symbols[0]],
            "benchmark_equal_units": {
                symbol: config.initial_equity / len(config.symbols) / prices[symbol]
                for symbol in config.symbols
            },
        }
    if state.get("last_date") == date.date().isoformat():
        raise ValueError(f"Paper state already processed {date.date().isoformat()}")
    units = {symbol: float(state["units"].get(symbol, 0.0)) for symbol in config.symbols}
    previous_equity = float(state["equity"])
    marked_equity = float(state["cash"]) + sum(units[symbol] * prices[symbol] for symbol in config.symbols)
    current_notional = {symbol: units[symbol] * prices[symbol] for symbol in config.symbols}
    # Rebalancing cost depends on target equity after cost. A few fixed-point
    # iterations resolve that small circular dependency deterministically.
    closing_equity = marked_equity
    for _ in range(5):
        desired_notional = {
            symbol: closing_equity * weights[symbol] for symbol in config.symbols
        }
        traded_notional = sum(
            abs(desired_notional[symbol] - current_notional[symbol])
            for symbol in config.symbols
        )
        transaction_cost = traded_notional * config.fee_bps / 10_000.0
        closing_equity = marked_equity - transaction_cost
    units = {symbol: closing_equity * weights[symbol] / prices[symbol] for symbol in config.symbols}
    cash = closing_equity - sum(units[symbol] * prices[symbol] for symbol in config.symbols)
    peak_equity = max(float(state["peak_equity"]), closing_equity)
    daily_return = closing_equity / previous_equity - 1.0
    benchmark_btc_value = float(state["benchmark_btc_units"]) * prices[config.symbols[0]]
    benchmark_equal_value = sum(
        float(state["benchmark_equal_units"][symbol]) * prices[symbol]
        for symbol in config.symbols
    )

    episodes = dict(state.get("episodes", {symbol: None for symbol in config.symbols}))
    order_records: list[dict[str, object]] = []
    closed_trades: list[dict[str, object]] = []
    for symbol in config.symbols:
        delta_units = units[symbol] - float(state["units"].get(symbol, 0.0))
        notional = abs(delta_units) * prices[symbol]
        if notional <= 1e-8:
            continue
        side = "buy" if delta_units > 0 else "sell"
        order_fee = notional * config.fee_bps / 10_000.0
        reference = f"PAPER-{date.strftime('%Y%m%d')}-{symbol}"
        order_records.append(
            {
                "date": date.date().isoformat(),
                "order_reference": reference,
                "symbol": symbol,
                "side": side,
                "units": abs(delta_units),
                "price": prices[symbol],
                "notional": notional,
                "fee": order_fee,
                "target_weight": weights[symbol],
            }
        )
        episode = episodes.get(symbol)
        if episode is None and delta_units > 0:
            episode = {
                "entry_date": date.date().isoformat(),
                "net_cash_flow": 0.0,
                "capital_deployed": 0.0,
            }
        if episode is not None:
            if delta_units > 0:
                episode["net_cash_flow"] -= notional + order_fee
                episode["capital_deployed"] += notional + order_fee
            else:
                episode["net_cash_flow"] += notional - order_fee
            if units[symbol] <= 1e-12:
                pnl = float(episode["net_cash_flow"])
                capital = float(episode["capital_deployed"])
                entry_date = pd.Timestamp(episode["entry_date"])
                closed_trades.append(
                    {
                        "trade_reference": f"TRADE-{episode['entry_date']}-{date.date().isoformat()}-{symbol}",
                        "symbol": symbol,
                        "entry_date": episode["entry_date"],
                        "exit_date": date.date().isoformat(),
                        "holding_days": (date.tz_localize(None).normalize() - entry_date).days,
                        "net_pnl": pnl,
                        "return_on_deployed_capital": pnl / capital if capital else 0.0,
                    }
                )
                episode = None
        episodes[symbol] = episode

    new_state = {
        "last_date": date.date().isoformat(),
        "equity": closing_equity,
        "peak_equity": peak_equity,
        "cash": cash,
        "units": units,
        "episodes": episodes,
        "benchmark_btc_units": state["benchmark_btc_units"],
        "benchmark_equal_units": state["benchmark_equal_units"],
    }
    record: dict[str, object] = {
        "date": date.date().isoformat(),
        "portfolio_closing_value": closing_equity,
        "daily_return": daily_return,
        "cumulative_return": closing_equity / config.initial_equity - 1.0,
        "drawdown": closing_equity / peak_equity - 1.0,
        "turnover": traded_notional / marked_equity if marked_equity else 0.0,
        "transaction_cost": transaction_cost,
        "cash_weight": cash / closing_equity if closing_equity else 0.0,
        "benchmark_btc_value": benchmark_btc_value,
        "benchmark_equal_weight_value": benchmark_equal_value,
        "excess_return_vs_btc": closing_equity / benchmark_btc_value - 1.0,
        "excess_return_vs_equal_weight": closing_equity / benchmark_equal_value - 1.0,
    }
    for symbol in config.symbols:
        record[f"weight_{symbol}"] = weights[symbol]
        record[f"units_{symbol}"] = units[symbol]
    return new_state, record, order_records, closed_trades


def calculate_portfolio_kpis(
    portfolio: pd.DataFrame,
    closed_trades: pd.DataFrame,
    *,
    initial_equity: float,
) -> dict[str, object]:
    """Calculate the assignment KPIs from the persisted OOS paper ledger."""

    if portfolio.empty:
        return {"observations": 0, "status": "awaiting_test_window"}
    portfolio = portfolio.sort_values("date", kind="stable")
    equity = portfolio["portfolio_closing_value"].astype(float)
    returns = portfolio["daily_return"].astype(float)
    total_return = float(equity.iloc[-1] / initial_equity - 1.0)
    periods = max(len(portfolio), 1)
    annualized_return = float((1.0 + total_return) ** (365.0 / periods) - 1.0)
    volatility = float(returns.std(ddof=1) * sqrt(365)) if len(returns) > 1 else 0.0
    sharpe = (
        float(returns.mean() / returns.std(ddof=1) * sqrt(365))
        if len(returns) > 1 and returns.std(ddof=1) > 0
        else 0.0
    )
    drawdown = portfolio["drawdown"].astype(float)
    underwater = drawdown.lt(0)
    drawdown_events = int((underwater & ~underwater.shift(1, fill_value=False)).sum())
    durations: list[int] = []
    current = 0
    for value in underwater:
        current = current + 1 if value else 0
        durations.append(current)
    trades = closed_trades if not closed_trades.empty else pd.DataFrame(columns=["net_pnl", "holding_days"])
    return {
        "observations": len(portfolio),
        "total_return": total_return,
        "annualized_return": annualized_return,
        "annualized_volatility": volatility,
        "sharpe_ratio_zero_risk_free": sharpe,
        "maximum_drawdown": float(drawdown.min()),
        "daily_win_rate": float(returns.gt(0).mean()),
        "drawdown_events": drawdown_events,
        "maximum_drawdown_duration_days": max(durations, default=0),
        "average_daily_turnover": float(portfolio["turnover"].mean()),
        "total_transaction_cost": float(portfolio["transaction_cost"].sum()),
        "closed_round_trips": len(trades),
        "round_trip_win_rate": float(trades["net_pnl"].gt(0).mean()) if len(trades) else None,
        "average_profit_per_closed_trade": float(trades["net_pnl"].mean()) if len(trades) else None,
        "average_holding_days": float(trades["holding_days"].mean()) if len(trades) else None,
        "btc_benchmark_return": float(
            portfolio["benchmark_btc_value"].iloc[-1] / initial_equity - 1.0
        ),
        "equal_weight_benchmark_return": float(
            portfolio["benchmark_equal_weight_value"].iloc[-1] / initial_equity - 1.0
        ),
        "excess_return_vs_btc": float(portfolio["excess_return_vs_btc"].iloc[-1]),
        "excess_return_vs_equal_weight": float(
            portfolio["excess_return_vs_equal_weight"].iloc[-1]
        ),
    }


def run_daily_pipeline(
    config: DailyConfig,
    *,
    client: BinancePublicClient | None = None,
    now: pd.Timestamp | None = None,
) -> dict[str, object]:
    """Fetch data, refit signals, backfill the OOS window, and persist artifacts."""

    client = client or BinancePublicClient(config.api_base_url)
    now = _utc(now) if now is not None else client.server_time()
    fetch_start = now.normalize() - pd.Timedelta(days=config.history_days)
    fetch_end = now.normalize() + pd.Timedelta(days=1)
    histories: dict[str, pd.DataFrame] = {}
    eligibility: dict[str, str] = {}
    quality_reports: list[dict] = []
    expected_latest = now.normalize() - pd.Timedelta(days=1)
    for symbol in config.symbols:
        listing_time = client.listing_time(symbol)
        if listing_time >= config.eligibility_cutoff:
            raise ValueError(
                f"{symbol} first daily candle {listing_time.date()} is not before "
                f"{config.eligibility_cutoff.date()}"
            )
        eligibility[symbol] = listing_time.isoformat()
        frame = client.fetch_klines(
            symbol,
            interval="1d",
            start=fetch_start,
            end=fetch_end,
            closed_at=now,
        )
        required_rows = config.parameter_training_days + max(slow for _, slow in config.parameter_grid) + 5
        quality = audit_ohlcv(frame, symbol=symbol, closed_at=now,
                             expected_last=expected_latest, minimum_rows=required_rows,
                             expected_first=min(config.test_start, expected_latest) - pd.Timedelta(days=required_rows - 1))
        quality_reports.append(quality)
        histories[symbol] = frame

    quality_bundle = {"generated_at_utc": now.isoformat(), "source": config.api_base_url,
                      "status": "PASS" if all(item["status"] == "PASS" for item in quality_reports) else "FAIL",
                      "datasets": quality_reports}
    write_audit(quality_bundle, config.output_directory / "data_quality.json")
    for quality in quality_reports:
        require_quality(quality)

    closes = pd.concat(
        [frame.set_index("open_time")["close"].rename(symbol) for symbol, frame in histories.items()],
        axis=1,
        join="inner",
    ).sort_index()
    if closes.empty:
        raise ValueError("No common closed daily candles across the configured universe")
    latest_close = closes.index[-1]
    output = config.output_directory
    output.mkdir(parents=True, exist_ok=True)
    for symbol, frame in histories.items():
        _write_csv_atomic(frame, output / "market_data" / f"{symbol}_1d.csv")

    test_closes = closes.loc[
        (closes.index >= config.test_start)
        & (closes.index <= config.test_end)
        & (closes.index <= latest_close)
    ].copy()
    price_output = test_closes.copy()
    price_output.index = price_output.index.date
    price_output.index.name = "date"
    _write_csv_atomic(price_output.reset_index(), output / "portfolio_closing_prices.csv")

    state_path = output / "paper_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else None
    if state is not None and set(state.get("units", {})) != set(config.symbols):
        raise ValueError(
            "Configured symbols changed after the paper account was initialized; "
            "archive the existing live directory before starting a new universe"
        )
    last_processed = _utc(state["last_date"]) if state and state.get("last_date") else None
    due_dates = test_closes.index
    if last_processed is not None:
        due_dates = due_dates[due_dates > last_processed]

    signal_frames: list[pd.DataFrame] = []
    portfolio_records: list[dict[str, object]] = []
    order_records: list[dict[str, object]] = []
    trade_records: list[dict[str, object]] = []
    for decision_date in due_dates:
        signals, weights = compute_daily_decision(closes, decision_date, config)
        signal_frames.append(signals)
        prices = {symbol: float(closes.loc[decision_date, symbol]) for symbol in config.symbols}
        state, portfolio_record, daily_orders, daily_trades = update_paper_state(
            state,
            date=decision_date,
            prices=prices,
            weights=weights,
            config=config,
        )
        portfolio_records.append(portfolio_record)
        order_records.extend(daily_orders)
        trade_records.extend(daily_trades)

    status = "pre_test"
    if latest_close >= config.test_start:
        status = "active" if latest_close <= config.test_end else "complete"
    if not len(due_dates):
        preview_date = min(latest_close, config.test_end)
        if latest_close < config.test_start:
            preview_date = latest_close
        preview, _ = compute_daily_decision(closes, preview_date, config)
        preview.insert(1, "run_type", "preview" if status == "pre_test" else "rerun")
        signal_frames.append(preview)
    else:
        for frame in signal_frames:
            frame.insert(1, "run_type", "oos")

    if signal_frames:
        signals_path = output / "daily_signals.csv"
        combined_signals = pd.concat(signal_frames, ignore_index=True)
        if status == "pre_test":
            # Preview history is disposable and may come from an earlier
            # universe/model configuration. Keep only the current preview.
            _write_csv_atomic(combined_signals, signals_path)
        else:
            _upsert_csv(combined_signals, signals_path, ["date", "symbol"])
        saved_signals = pd.read_csv(signals_path)
        saved_signals = saved_signals.loc[saved_signals["symbol"].isin(config.symbols)]
        _write_csv_atomic(saved_signals, signals_path)
    if portfolio_records:
        _upsert_csv(
            pd.DataFrame.from_records(portfolio_records),
            output / "portfolio_daily.csv",
            ["date"],
        )
    if order_records:
        _upsert_csv(
            pd.DataFrame.from_records(order_records),
            output / "paper_orders.csv",
            ["order_reference"],
        )
    if trade_records:
        _upsert_csv(
            pd.DataFrame.from_records(trade_records),
            output / "closed_trades.csv",
            ["trade_reference"],
        )
    if state is not None:
        _write_json_atomic(state, state_path)
    manifest = {
        "run_time_utc": now.isoformat(),
        "latest_closed_candle": latest_close.isoformat(),
        "status": status,
        "symbols": list(config.symbols),
        "eligibility_listing_times": eligibility,
        "processed_dates_this_run": [value.date().isoformat() for value in due_dates],
        "data_source": config.api_base_url,
        "orders_enabled": False,
        "data_quality_status": quality_bundle["status"],
        "data_quality_file": "data_quality.json",
        "data_fingerprints": {item["symbol"]: item["frame_sha256"] for item in quality_reports},
    }
    _write_json_atomic(manifest, output / "run_manifest.json")
    portfolio_path = output / "portfolio_daily.csv"
    trades_path = output / "closed_trades.csv"
    portfolio_frame = pd.read_csv(portfolio_path) if portfolio_path.exists() else pd.DataFrame()
    trades_frame = pd.read_csv(trades_path) if trades_path.exists() else pd.DataFrame()
    kpis = calculate_portfolio_kpis(
        portfolio_frame,
        trades_frame,
        initial_equity=config.initial_equity,
    )
    _write_json_atomic(kpis, output / "portfolio_kpis.json")
    return manifest


def _upsert_csv(frame: pd.DataFrame, path: Path, keys: list[str]) -> None:
    if path.exists():
        existing = pd.read_csv(path)
        frame = pd.concat([existing, frame], ignore_index=True)
    frame = frame.drop_duplicates(keys, keep="last").sort_values(keys, kind="stable")
    _write_csv_atomic(frame, path)


def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _write_json_atomic(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _utc(value: pd.Timestamp | str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tz is None else timestamp.tz_convert("UTC")


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    average_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss.replace(0.0, np.nan)
    result = 100.0 - 100.0 / (1.0 + relative_strength)
    return result.where(average_loss.ne(0.0), 100.0)
