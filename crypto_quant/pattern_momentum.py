"""Pattern-first, momentum-confirmed crypto strategy research engine.

The module deliberately uses only pandas and NumPy.  It is a research/backtest
implementation, not an exchange execution client.  Structural signals are
formed on completed 4-hour candles and are filled at the next available
execution-bar open, which prevents close-price look-ahead.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {"open_time", "open", "high", "low", "close", "volume"}
NUMERIC_COLUMNS = ["open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class StrategyConfig:
    """Parameters shared by signal generation and execution."""

    name: str
    structure_rule: str = "4h"
    execution_rule: str = "1h"
    pattern_lookback: int = 48
    volume_multiplier: float = 1.50
    rsi_period: int = 14
    rsi_long_min: float = 45.0
    rsi_long_max: float = 78.0
    rsi_short_min: float = 22.0
    rsi_short_max: float = 55.0
    divergence_lookback: int = 24
    min_reward_risk: float = 3.0
    risk_fraction: float = 0.01
    max_notional_leverage: float = 1.0
    fee_bps: float = 4.0
    slippage_bps: float = 2.0
    max_holding_bars: int = 24 * 21
    max_drawdown: float = 0.25
    stop_atr_buffer: float = 0.50


DEFAULT_CONFIGS = {
    "double_reversal": StrategyConfig(
        name="double_reversal",
        pattern_lookback=60,
        max_holding_bars=24 * 21,
    ),
    "triangle_breakout": StrategyConfig(
        name="triangle_breakout",
        pattern_lookback=30,
        max_holding_bars=24 * 14,
    ),
    "flag_breakout": StrategyConfig(
        name="flag_breakout",
        pattern_lookback=16,
        max_holding_bars=24 * 10,
    ),
}


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.DataFrame
    audit: pd.DataFrame
    rejections: pd.DataFrame
    killed: bool


def load_ohlcv(path: str | Path) -> pd.DataFrame:
    """Load and validate a normalized OHLCV file."""

    frame = pd.read_csv(path, parse_dates=["open_time"])
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True)
    frame = frame.sort_values("open_time", kind="stable").drop_duplicates("open_time")
    frame = frame.set_index("open_time")
    if not frame.index.is_monotonic_increasing:
        raise ValueError(f"{path} timestamps are not increasing")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError(f"{path} contains non-positive prices")
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError(f"{path} contains invalid high prices")
    if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError(f"{path} contains invalid low prices")
    return frame


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    average_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss.replace(0.0, np.nan)
    result = 100.0 - (100.0 / (1.0 + relative_strength))
    return result.where(average_loss.ne(0.0), 100.0)


def _divergence_flags(frame: pd.DataFrame, lookback: int) -> tuple[pd.Series, pd.Series]:
    """Compare price/RSI extrema in two completed halves of a rolling window."""

    bearish = np.zeros(len(frame), dtype=bool)
    bullish = np.zeros(len(frame), dtype=bool)
    half = lookback // 2
    high = frame["high"].to_numpy()
    low = frame["low"].to_numpy()
    rsi = frame["rsi"].to_numpy()
    for position in range(lookback, len(frame)):
        old = slice(position - lookback, position - half)
        recent = slice(position - half, position)
        if np.isnan(rsi[position - lookback : position]).any():
            continue
        old_high_offset = int(np.argmax(high[old]))
        recent_high_offset = int(np.argmax(high[recent]))
        old_high_position = position - lookback + old_high_offset
        recent_high_position = position - half + recent_high_offset
        bearish[position] = (
            high[recent_high_position] > high[old_high_position] * 1.002
            and rsi[recent_high_position] < rsi[old_high_position] - 2.0
        )
        old_low_offset = int(np.argmin(low[old]))
        recent_low_offset = int(np.argmin(low[recent]))
        old_low_position = position - lookback + old_low_offset
        recent_low_position = position - half + recent_low_offset
        bullish[position] = (
            low[recent_low_position] < low[old_low_position] * 0.998
            and rsi[recent_low_position] > rsi[old_low_position] + 2.0
        )
    return (
        pd.Series(bearish, index=frame.index),
        pd.Series(bullish, index=frame.index),
    )


def build_structure_bars(
    execution: pd.DataFrame,
    structure_rule: str = "4h",
    execution_rule: str = "1h",
    rsi_period: int = 14,
    divergence_lookback: int = 24,
) -> pd.DataFrame:
    """Resample execution bars and compute close-known momentum features.

    A 4-hour candle containing 00:00, 01:00, 02:00 and 03:00 bars is stamped
    04:00.  Therefore a signal at 04:00 can only fill at or after 04:00.
    Incomplete structure candles remain present as NaN rows so rolling windows
    cannot silently bridge source-data gaps.
    """

    expected_count = int(pd.Timedelta(structure_rule) / pd.Timedelta(execution_rule))
    aggregations: dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    for optional in ("quote_volume", "trade_count"):
        if optional in execution.columns:
            aggregations[optional] = "sum"
    structure = execution.resample(
        structure_rule,
        origin="epoch",
        closed="left",
        label="right",
    ).agg(aggregations)
    source_count = execution["close"].resample(
        structure_rule,
        origin="epoch",
        closed="left",
        label="right",
    ).count()
    structure["source_bar_count"] = source_count
    incomplete = source_count.ne(expected_count)
    structure.loc[incomplete, list(aggregations)] = np.nan

    previous_close = structure["close"].shift(1)
    true_range = pd.concat(
        [
            structure["high"] - structure["low"],
            (structure["high"] - previous_close).abs(),
            (structure["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    structure["atr"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    structure["rsi"] = _rsi(structure["close"], rsi_period)
    ema12 = structure["close"].ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = structure["close"].ewm(span=26, adjust=False, min_periods=26).mean()
    structure["macd"] = ema12 - ema26
    structure["macd_signal"] = structure["macd"].ewm(
        span=9, adjust=False, min_periods=9
    ).mean()
    structure["macd_slope"] = structure["macd"].diff()
    # The current breakout volume is compared only with completed prior bars.
    structure["volume_sma20"] = structure["volume"].shift(1).rolling(20).mean()
    structure["ema50"] = structure["close"].ewm(span=50, adjust=False, min_periods=50).mean()
    structure["ema200"] = structure["close"].ewm(
        span=200, adjust=False, min_periods=200
    ).mean()
    bearish, bullish = _divergence_flags(structure, divergence_lookback)
    structure["bearish_divergence"] = bearish
    structure["bullish_divergence"] = bullish
    structure["complete"] = ~incomplete
    return structure


def _base_candidate(
    timestamp: pd.Timestamp,
    row: pd.Series,
    pattern: str,
    direction: int,
    breakout: float,
    stop: float,
    target: float,
) -> dict[str, object]:
    return {
        "signal_time": timestamp,
        "pattern": pattern,
        "direction": direction,
        "breakout": float(breakout),
        "stop": float(stop),
        "target": float(target),
        "close": float(row["close"]),
        "volume": float(row["volume"]),
        "volume_sma20": float(row["volume_sma20"]),
        "rsi": float(row["rsi"]),
        "macd": float(row["macd"]),
        "macd_signal": float(row["macd_signal"]),
        "macd_slope": float(row["macd_slope"]),
        "bearish_divergence": bool(row["bearish_divergence"]),
        "bullish_divergence": bool(row["bullish_divergence"]),
    }


def _double_reversal_candidates(
    bars: pd.DataFrame, config: StrategyConfig
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    lookback = config.pattern_lookback
    half = lookback // 2
    for position in range(lookback, len(bars)):
        row = bars.iloc[position]
        previous = bars.iloc[position - 1]
        window = bars.iloc[position - lookback : position]
        if window[["high", "low", "close", "atr"]].isna().any().any() or pd.isna(row["atr"]):
            continue

        first = window.iloc[:half]
        second = window.iloc[half:]

        low_one_time = first["low"].idxmin()
        low_two_time = second["low"].idxmin()
        low_one = float(first.loc[low_one_time, "low"])
        low_two = float(second.loc[low_two_time, "low"])
        between_lows = window.loc[low_one_time:low_two_time]
        neckline = float(between_lows["high"].max())
        bottom = (low_one + low_two) / 2.0
        tolerance = max(bottom * 0.025, float(row["atr"]))
        depth = neckline - bottom
        if (
            abs(low_one - low_two) <= tolerance
            and depth >= 2.0 * float(row["atr"])
            and float(row["close"]) > neckline
            and float(previous["close"]) <= neckline
        ):
            stop = neckline - config.stop_atr_buffer * float(row["atr"])
            candidates.append(
                _base_candidate(
                    bars.index[position],
                    row,
                    "double_bottom",
                    1,
                    neckline,
                    stop,
                    neckline + depth,
                )
            )

        high_one_time = first["high"].idxmax()
        high_two_time = second["high"].idxmax()
        high_one = float(first.loc[high_one_time, "high"])
        high_two = float(second.loc[high_two_time, "high"])
        between_highs = window.loc[high_one_time:high_two_time]
        neckline = float(between_highs["low"].min())
        top = (high_one + high_two) / 2.0
        tolerance = max(top * 0.025, float(row["atr"]))
        depth = top - neckline
        if (
            abs(high_one - high_two) <= tolerance
            and depth >= 2.0 * float(row["atr"])
            and float(row["close"]) < neckline
            and float(previous["close"]) >= neckline
        ):
            stop = neckline + config.stop_atr_buffer * float(row["atr"])
            candidates.append(
                _base_candidate(
                    bars.index[position],
                    row,
                    "double_top",
                    -1,
                    neckline,
                    stop,
                    neckline - depth,
                )
            )
    return candidates


def _normalized_slope(values: pd.Series) -> float:
    array = values.to_numpy(dtype=float)
    if np.isnan(array).any() or np.mean(array) == 0:
        return np.nan
    return float(np.polyfit(np.arange(len(array), dtype=float), array, 1)[0] / np.mean(array))


def _triangle_candidates(
    bars: pd.DataFrame, config: StrategyConfig
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    lookback = config.pattern_lookback
    recent_length = max(6, lookback // 3)
    for position in range(lookback, len(bars)):
        row = bars.iloc[position]
        previous = bars.iloc[position - 1]
        window = bars.iloc[position - lookback : position]
        if window[["high", "low", "close"]].isna().any().any() or pd.isna(row["atr"]):
            continue
        high_slope = _normalized_slope(window["high"])
        low_slope = _normalized_slope(window["low"])
        first_width = float((window["high"] - window["low"]).iloc[:recent_length].mean())
        last_width = float((window["high"] - window["low"]).iloc[-recent_length:].mean())
        contracting = last_width <= first_width * 0.90
        if not contracting:
            continue
        resistance = float(window["high"].iloc[-(lookback // 2) :].quantile(0.90))
        support = float(window["low"].iloc[-(lookback // 2) :].quantile(0.10))
        height = float(window["high"].max() - window["low"].min())

        ascending = low_slope >= 0.00025 and abs(high_slope) <= 0.00075
        if (
            ascending
            and float(row["close"]) > resistance
            and float(previous["close"]) <= resistance
        ):
            stop = resistance - config.stop_atr_buffer * float(row["atr"])
            candidates.append(
                _base_candidate(
                    bars.index[position],
                    row,
                    "ascending_triangle",
                    1,
                    resistance,
                    stop,
                    resistance + height,
                )
            )

        descending = high_slope <= -0.00025 and abs(low_slope) <= 0.00075
        if (
            descending
            and float(row["close"]) < support
            and float(previous["close"]) >= support
        ):
            stop = support + config.stop_atr_buffer * float(row["atr"])
            candidates.append(
                _base_candidate(
                    bars.index[position],
                    row,
                    "descending_triangle",
                    -1,
                    support,
                    stop,
                    support - height,
                )
            )
    return candidates


def _flag_candidates(
    bars: pd.DataFrame, config: StrategyConfig
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    impulse_bars = 7
    consolidation_bars = 9
    required = impulse_bars + consolidation_bars
    for position in range(required, len(bars)):
        row = bars.iloc[position]
        previous = bars.iloc[position - 1]
        impulse = bars.iloc[position - required : position - consolidation_bars]
        consolidation = bars.iloc[position - consolidation_bars : position]
        if (
            impulse[["high", "low", "close"]].isna().any().any()
            or consolidation[["high", "low", "close"]].isna().any().any()
            or pd.isna(row["atr"])
        ):
            continue
        impulse_move = float(impulse["close"].iloc[-1] - impulse["close"].iloc[0])
        impulse_height = abs(impulse_move)
        atr = float(row["atr"])
        if impulse_height < 3.0 * atr:
            continue
        consolidation_range = float(consolidation["high"].max() - consolidation["low"].min())
        if consolidation_range > impulse_height * 0.65:
            continue
        consolidation_slope = _normalized_slope(consolidation["close"])

        if impulse_move > 0:
            resistance = float(consolidation["high"].max())
            shallow_retracement = float(consolidation["low"].min()) >= (
                float(impulse["close"].iloc[-1]) - 0.50 * impulse_height
            )
            flag_shape = -0.0030 <= consolidation_slope <= 0.0010
            if (
                shallow_retracement
                and flag_shape
                and float(row["close"]) > resistance
                and float(previous["close"]) <= resistance
            ):
                # The broken flag boundary is the post-breakout invalidation
                # level.  Using the opposite edge of the whole flag here would
                # make the specified measured-move target structurally unable
                # to clear the mandatory 3R gate.
                stop = resistance - config.stop_atr_buffer * atr
                candidates.append(
                    _base_candidate(
                        bars.index[position],
                        row,
                        "bull_flag",
                        1,
                        resistance,
                        stop,
                        resistance + impulse_height,
                    )
                )
        else:
            support = float(consolidation["low"].min())
            shallow_retracement = float(consolidation["high"].max()) <= (
                float(impulse["close"].iloc[-1]) + 0.50 * impulse_height
            )
            flag_shape = -0.0010 <= consolidation_slope <= 0.0030
            if (
                shallow_retracement
                and flag_shape
                and float(row["close"]) < support
                and float(previous["close"]) >= support
            ):
                stop = support + config.stop_atr_buffer * atr
                candidates.append(
                    _base_candidate(
                        bars.index[position],
                        row,
                        "bear_flag",
                        -1,
                        support,
                        stop,
                        support - impulse_height,
                    )
                )
    return candidates


def _confirmation_reason(candidate: pd.Series, config: StrategyConfig) -> str:
    required = ["volume_sma20", "rsi", "macd", "macd_signal", "macd_slope"]
    if candidate[required].isna().any():
        return "indicator_warmup"
    if candidate["volume"] <= config.volume_multiplier * candidate["volume_sma20"]:
        return "volume"
    if int(candidate["direction"]) == 1:
        if not config.rsi_long_min <= candidate["rsi"] <= config.rsi_long_max:
            return "rsi"
        if bool(candidate["bearish_divergence"]):
            return "rsi_divergence"
        if not (
            candidate["macd"] > candidate["macd_signal"]
            and candidate["macd_slope"] > 0
        ):
            return "macd"
    else:
        if not config.rsi_short_min <= candidate["rsi"] <= config.rsi_short_max:
            return "rsi"
        if bool(candidate["bullish_divergence"]):
            return "rsi_divergence"
        if not (
            candidate["macd"] < candidate["macd_signal"]
            and candidate["macd_slope"] < 0
        ):
            return "macd"
    return "passed"


def build_candidates(structure: pd.DataFrame, config: StrategyConfig) -> pd.DataFrame:
    """Detect chart patterns, then annotate every momentum-gate decision."""

    builders = {
        "double_reversal": _double_reversal_candidates,
        "triangle_breakout": _triangle_candidates,
        "flag_breakout": _flag_candidates,
    }
    if config.name not in builders:
        raise ValueError(f"Unknown strategy {config.name!r}; choose from {sorted(builders)}")
    records = builders[config.name](structure, config)
    columns = [
        "signal_time",
        "pattern",
        "direction",
        "breakout",
        "stop",
        "target",
        "close",
        "volume",
        "volume_sma20",
        "rsi",
        "macd",
        "macd_signal",
        "macd_slope",
        "bearish_divergence",
        "bullish_divergence",
        "confirmation",
    ]
    if not records:
        return pd.DataFrame(columns=columns)
    candidates = pd.DataFrame.from_records(records)
    candidates["confirmation"] = candidates.apply(
        _confirmation_reason, axis=1, config=config
    )
    return candidates[columns].sort_values("signal_time", kind="stable").reset_index(drop=True)


def _adverse_price(price: float, direction: int, bps: float, entering: bool) -> float:
    buying = (direction == 1 and entering) or (direction == -1 and not entering)
    multiplier = 1.0 + bps / 10_000.0 if buying else 1.0 - bps / 10_000.0
    return price * multiplier


def _empty_result() -> BacktestResult:
    return BacktestResult(
        trades=pd.DataFrame(),
        equity=pd.DataFrame(columns=["timestamp", "equity", "cash", "drawdown"]),
        audit=pd.DataFrame(),
        rejections=pd.DataFrame(),
        killed=False,
    )


def backtest(
    execution: pd.DataFrame,
    candidates: pd.DataFrame,
    config: StrategyConfig,
    *,
    symbol: str,
    market: str,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    initial_equity: float = 100_000.0,
) -> BacktestResult:
    """Backtest one strategy with one open position and conservative fills."""

    if execution.empty:
        return _empty_result()
    bars = execution.copy()
    if start is not None:
        start_timestamp = pd.Timestamp(start)
        start_timestamp = start_timestamp.tz_localize("UTC") if start_timestamp.tz is None else start_timestamp.tz_convert("UTC")
        bars = bars.loc[bars.index >= start_timestamp]
    if end is not None:
        end_timestamp = pd.Timestamp(end)
        end_timestamp = end_timestamp.tz_localize("UTC") if end_timestamp.tz is None else end_timestamp.tz_convert("UTC")
        bars = bars.loc[bars.index < end_timestamp]
    if bars.empty:
        return _empty_result()

    eligible = candidates.loc[candidates["confirmation"].eq("passed")].copy()
    signal_groups = {
        timestamp: group.to_dict("records")
        for timestamp, group in eligible.groupby("signal_time", sort=False)
    }
    fee_rate = config.fee_bps / 10_000.0
    cash = float(initial_equity)
    peak_equity = float(initial_equity)
    position: dict[str, object] | None = None
    trades: list[dict[str, object]] = []
    audit: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    equity_records: list[dict[str, object]] = []
    killed = False
    sequence = 0
    previous_timestamp: pd.Timestamp | None = None
    expected_step = pd.Timedelta(config.execution_rule)
    period_tag = bars.index[0].strftime("%Y%m%d")
    market_tag = "SPT" if market == "spot" else "PERP"

    def audit_fill(
        timestamp: pd.Timestamp,
        reference: str,
        action: str,
        price: float,
        units: float,
        reason: str,
    ) -> None:
        audit.append(
            {
                "timestamp": timestamp,
                "order_reference": reference,
                "filled_bid_reference": reference if action == "bid" else "",
                "filled_ask_reference": reference if action == "ask" else "",
                "action": action,
                "price": price,
                "order_volume": units,
                "traded_volume": units,
                "event": "fill",
                "reason": reason,
            }
        )

    def close_position(timestamp: pd.Timestamp, raw_price: float, reason: str) -> None:
        nonlocal cash, position
        assert position is not None
        direction = int(position["direction"])
        exit_price = _adverse_price(raw_price, direction, config.slippage_bps, entering=False)
        units = float(position["units"])
        exit_fee = exit_price * units * fee_rate
        gross_pnl = direction * (exit_price - float(position["entry_price"])) * units
        net_pnl = gross_pnl - float(position["entry_fee"]) - exit_fee
        # Entry fee was already deducted; add gross PnL less only the exit fee.
        cash += gross_pnl - exit_fee
        reference = str(position["order_reference"])
        audit_fill(
            timestamp,
            f"{reference}-X",
            "ask" if direction == 1 else "bid",
            exit_price,
            units,
            reason,
        )
        initial_risk_cash = float(position["initial_risk"]) * units
        trades.append(
            {
                "strategy": config.name,
                "market": market,
                "symbol": symbol,
                "pattern": position["pattern"],
                "direction": "long" if direction == 1 else "short",
                "order_reference": reference,
                "signal_time": position["signal_time"],
                "entry_time": position["entry_time"],
                "exit_time": timestamp,
                "entry_price": position["entry_price"],
                "initial_stop": position["initial_stop"],
                "target": position["target"],
                "exit_price": exit_price,
                "units": units,
                "gross_pnl": gross_pnl,
                "fees": float(position["entry_fee"]) + exit_fee,
                "net_pnl": net_pnl,
                "r_multiple": net_pnl / initial_risk_cash if initial_risk_cash else np.nan,
                "exit_reason": reason,
                "holding_bars": position["holding_bars"],
            }
        )
        position = None

    for timestamp, bar in bars.iterrows():
        gap = previous_timestamp is not None and timestamp - previous_timestamp > expected_step * 1.5
        exited_this_bar = False
        if position is not None and gap:
            close_position(timestamp, float(bar["open"]), "data_gap_safeguard")
            exited_this_bar = True

        if position is not None:
            position["holding_bars"] = int(position["holding_bars"]) + 1
            direction = int(position["direction"])
            stop = float(position["stop"])
            target = float(position["target"])
            open_price = float(bar["open"])
            high = float(bar["high"])
            low = float(bar["low"])
            exit_price: float | None = None
            reason = ""
            if direction == 1:
                if open_price <= stop:
                    exit_price, reason = open_price, "stop_gap"
                elif open_price >= target:
                    exit_price, reason = target, "target"
                elif low <= stop:
                    exit_price, reason = stop, "stop"
                elif high >= target:
                    exit_price, reason = target, "target"
            else:
                if open_price >= stop:
                    exit_price, reason = open_price, "stop_gap"
                elif open_price <= target:
                    exit_price, reason = target, "target"
                elif high >= stop:
                    exit_price, reason = stop, "stop"
                elif low <= target:
                    exit_price, reason = target, "target"
            if exit_price is not None:
                close_position(timestamp, exit_price, reason)
                exited_this_bar = True
            elif int(position["holding_bars"]) >= config.max_holding_bars:
                close_position(timestamp, float(bar["close"]), "time_stop")
                exited_this_bar = True
            else:
                entry_price = float(position["entry_price"])
                initial_risk = float(position["initial_risk"])
                if direction == 1:
                    position["best_price"] = max(float(position["best_price"]), high)
                    gain = float(position["best_price"]) - entry_price
                    if gain >= initial_risk:
                        position["stop"] = max(float(position["stop"]), entry_price)
                    if gain >= 2.0 * initial_risk:
                        position["stop"] = max(
                            float(position["stop"]), entry_price + 0.33 * gain
                        )
                else:
                    position["best_price"] = min(float(position["best_price"]), low)
                    gain = entry_price - float(position["best_price"])
                    if gain >= initial_risk:
                        position["stop"] = min(float(position["stop"]), entry_price)
                    if gain >= 2.0 * initial_risk:
                        position["stop"] = min(
                            float(position["stop"]), entry_price - 0.33 * gain
                        )

        if position is None and not killed and not exited_this_bar and not gap:
            signals = signal_groups.get(timestamp, [])
            for signal in signals:
                direction = int(signal["direction"])
                if market == "spot" and direction == -1:
                    rejections.append(
                        {"timestamp": timestamp, "pattern": signal["pattern"], "reason": "spot_short"}
                    )
                    continue
                entry_price = _adverse_price(
                    float(bar["open"]), direction, config.slippage_bps, entering=True
                )
                stop = float(signal["stop"])
                target = float(signal["target"])
                risk = direction * (entry_price - stop)
                reward = direction * (target - entry_price)
                if risk <= 0 or reward <= 0:
                    rejections.append(
                        {"timestamp": timestamp, "pattern": signal["pattern"], "reason": "invalid_three_prices"}
                    )
                    continue
                reward_risk = reward / risk
                if reward_risk < config.min_reward_risk:
                    rejections.append(
                        {
                            "timestamp": timestamp,
                            "pattern": signal["pattern"],
                            "reason": "reward_risk",
                            "reward_risk": reward_risk,
                        }
                    )
                    continue
                risk_budget = cash * config.risk_fraction
                risk_units = risk_budget / risk
                notional_units = cash * config.max_notional_leverage / entry_price
                units = min(risk_units, notional_units)
                if units <= 0:
                    continue
                sequence += 1
                reference = (
                    f"{config.name[:4].upper()}-{market_tag}-{symbol}-{period_tag}-{sequence:05d}"
                )
                entry_fee = entry_price * units * fee_rate
                cash -= entry_fee
                position = {
                    "pattern": signal["pattern"],
                    "direction": direction,
                    "order_reference": reference,
                    "signal_time": signal["signal_time"],
                    "entry_time": timestamp,
                    "entry_price": entry_price,
                    "entry_fee": entry_fee,
                    "initial_stop": stop,
                    "stop": stop,
                    "target": target,
                    "units": units,
                    "initial_risk": risk,
                    "best_price": entry_price,
                    "holding_bars": 0,
                }
                audit_fill(
                    timestamp,
                    reference,
                    "bid" if direction == 1 else "ask",
                    entry_price,
                    units,
                    "entry",
                )
                # The order fills at this bar's open, so its subsequent range is
                # tradable.  Resolve an ambiguous stop/target collision against
                # the strategy (stop first) rather than granting perfect path
                # knowledge inside an OHLC candle.
                entry_bar_exit: float | None = None
                entry_bar_reason = ""
                if direction == 1:
                    if float(bar["low"]) <= stop:
                        entry_bar_exit, entry_bar_reason = stop, "stop"
                    elif float(bar["high"]) >= target:
                        entry_bar_exit, entry_bar_reason = target, "target"
                else:
                    if float(bar["high"]) >= stop:
                        entry_bar_exit, entry_bar_reason = stop, "stop"
                    elif float(bar["low"]) <= target:
                        entry_bar_exit, entry_bar_reason = target, "target"
                if entry_bar_exit is not None:
                    close_position(timestamp, entry_bar_exit, entry_bar_reason)
                    exited_this_bar = True
                else:
                    # Stop changes become active on the next bar.  That avoids
                    # inventing an intrabar path after observing only OHLC.
                    if direction == 1:
                        position["best_price"] = float(bar["high"])
                        gain = float(position["best_price"]) - entry_price
                        if gain >= risk:
                            position["stop"] = max(float(position["stop"]), entry_price)
                        if gain >= 2.0 * risk:
                            position["stop"] = max(
                                float(position["stop"]), entry_price + 0.33 * gain
                            )
                    else:
                        position["best_price"] = float(bar["low"])
                        gain = entry_price - float(position["best_price"])
                        if gain >= risk:
                            position["stop"] = min(float(position["stop"]), entry_price)
                        if gain >= 2.0 * risk:
                            position["stop"] = min(
                                float(position["stop"]), entry_price - 0.33 * gain
                            )
                break

        close = float(bar["close"])
        unrealized = 0.0
        if position is not None:
            unrealized = (
                int(position["direction"])
                * (close - float(position["entry_price"]))
                * float(position["units"])
            )
        marked_equity = cash + unrealized
        peak_equity = max(peak_equity, marked_equity)
        drawdown = marked_equity / peak_equity - 1.0
        if not killed and drawdown <= -config.max_drawdown:
            killed = True
            if position is not None:
                close_position(timestamp, close, "drawdown_kill_switch")
                marked_equity = cash
                drawdown = marked_equity / peak_equity - 1.0
        equity_records.append(
            {"timestamp": timestamp, "equity": marked_equity, "cash": cash, "drawdown": drawdown}
        )
        previous_timestamp = timestamp

    if position is not None:
        final_timestamp = bars.index[-1]
        close_position(final_timestamp, float(bars.iloc[-1]["close"]), "end_of_test")
        equity_records[-1]["equity"] = cash
        equity_records[-1]["cash"] = cash
        equity_records[-1]["drawdown"] = cash / peak_equity - 1.0

    return BacktestResult(
        trades=pd.DataFrame.from_records(trades),
        equity=pd.DataFrame.from_records(equity_records),
        audit=pd.DataFrame.from_records(audit),
        rejections=pd.DataFrame.from_records(rejections),
        killed=killed,
    )


def performance_metrics(
    result: BacktestResult,
    *,
    initial_equity: float = 100_000.0,
    bars_per_year: int = 24 * 365,
) -> dict[str, float | int | bool]:
    """Return compact risk/performance metrics for a completed backtest."""

    if result.equity.empty:
        return {
            "trades": 0,
            "total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "expectancy_r": 0.0,
            "killed": result.killed,
        }
    curve = result.equity.set_index("timestamp")["equity"].astype(float)
    returns = curve.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    total_return = curve.iloc[-1] / initial_equity - 1.0
    elapsed_years = max(
        (curve.index[-1] - curve.index[0]).total_seconds() / (365.25 * 24 * 3600),
        1 / 365.25,
    )
    cagr = (curve.iloc[-1] / initial_equity) ** (1 / elapsed_years) - 1.0
    rolling_peak = curve.cummax()
    max_drawdown = (curve / rolling_peak - 1.0).min()
    sharpe = 0.0
    if len(returns) > 1 and returns.std(ddof=1) > 0:
        sharpe = float(returns.mean() / returns.std(ddof=1) * sqrt(bars_per_year))
    trades = result.trades
    if trades.empty:
        win_rate = profit_factor = expectancy = 0.0
    else:
        win_rate = float(trades["net_pnl"].gt(0).mean())
        gains = float(trades.loc[trades["net_pnl"] > 0, "net_pnl"].sum())
        losses = abs(float(trades.loc[trades["net_pnl"] < 0, "net_pnl"].sum()))
        profit_factor = gains / losses if losses else (np.inf if gains else 0.0)
        expectancy = float(trades["r_multiple"].mean())
    return {
        "trades": int(len(trades)),
        "total_return_pct": round(total_return * 100, 3),
        "cagr_pct": round(cagr * 100, 3),
        "max_drawdown_pct": round(max_drawdown * 100, 3),
        "sharpe": round(sharpe, 3),
        "win_rate_pct": round(win_rate * 100, 3),
        "profit_factor": round(profit_factor, 3),
        "expectancy_r": round(expectancy, 3),
        "killed": result.killed,
    }


def validate_audit_log(result: BacktestResult) -> None:
    """Raise when simulated entry/exit fills do not reconcile with trades."""

    if result.trades.empty:
        if not result.audit.empty:
            raise ValueError("Audit log contains fills but trade ledger is empty")
        return
    if len(result.audit) != 2 * len(result.trades):
        raise ValueError("Every completed trade must have exactly two audit fills")
    for trade in result.trades.itertuples(index=False):
        entry_reference = trade.order_reference
        exit_reference = f"{entry_reference}-X"
        fills = result.audit.loc[
            result.audit["order_reference"].isin([entry_reference, exit_reference])
        ]
        if len(fills) != 2:
            raise ValueError(f"Trade {entry_reference} does not have two fills")
        if not np.allclose(fills["order_volume"], fills["traded_volume"]):
            raise ValueError(f"Trade {entry_reference} has a fill-volume mismatch")
        if not np.allclose(fills["traded_volume"], float(trade.units)):
            raise ValueError(f"Trade {entry_reference} units do not reconcile")
