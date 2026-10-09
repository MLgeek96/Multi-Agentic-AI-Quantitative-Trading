"""Helpers for applying frozen research signals across Spot and futures data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


DAILY_AGGREGATIONS = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
    "quote_volume": "sum",
    "trade_count": "sum",
    "taker_buy_base_volume": "sum",
    "taker_buy_quote_volume": "sum",
}


def load_complete_daily_market(path: str | Path) -> pd.DataFrame:
    """Aggregate normalized hourly candles into complete UTC daily bars.

    The same loader is used for Spot and USD-M futures so that the validation
    comparison does not change its bar-completeness or aggregation rules.
    """

    path = Path(path)
    frame = pd.read_csv(path, parse_dates=["open_time"])
    required = {"open_time", *DAILY_AGGREGATIONS}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True)
    frame = (
        frame.sort_values("open_time", kind="stable")
        .drop_duplicates("open_time")
        .set_index("open_time")
    )
    numeric = list(DAILY_AGGREGATIONS)
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    daily = frame.resample("1D", closed="left", label="left").agg(
        DAILY_AGGREGATIONS
    )
    daily["source_bar_count"] = frame["close"].resample(
        "1D", closed="left", label="left"
    ).count()
    daily.loc[daily["source_bar_count"].ne(24), numeric] = pd.NA
    return daily.dropna(subset=["close"])


def load_daily_market(path: str | Path) -> pd.DataFrame:
    """Load an already-daily Binance candle file with macro-required fields."""

    path = Path(path)
    frame = pd.read_csv(path, parse_dates=["open_time"])
    required = {"open_time", *DAILY_AGGREGATIONS}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True)
    frame = (
        frame.sort_values("open_time", kind="stable")
        .drop_duplicates("open_time")
        .set_index("open_time")
    )
    numeric = list(DAILY_AGGREGATIONS)
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    if not frame.index.normalize().equals(frame.index):
        raise ValueError(f"{path} contains non-midnight daily timestamps")
    return frame[numeric].dropna(subset=["close"])


def enforce_execution_mode(signals: pd.DataFrame, *, allow_short: bool) -> pd.DataFrame:
    """Return a copy of signals compatible with the selected market account.

    Ordinary Spot is long/cash, while perpetual futures may retain signed
    positions. Fractional positive signals (for example an HMM throttle) are
    preserved.
    """

    if "signal" not in signals:
        raise ValueError("signals must contain a signal column")
    output = signals.copy()
    output["signal"] = pd.to_numeric(output["signal"], errors="raise")
    if not allow_short:
        output["signal"] = output["signal"].clip(lower=0.0)
    return output
