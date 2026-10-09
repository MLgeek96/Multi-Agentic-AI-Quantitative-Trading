"""Fail-closed OHLCV validation shared by research agents and daily ingestion.

Checks preserve evidence: no sorting, deduplication, imputation, or repair here.
A structural PASS certifies this input window, not a profitable strategy or an
independently verified exchange feed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


SCHEMA_VERSION = "ohlcv-quality-v1"
PRICE_COLUMNS = ("open", "high", "low", "close")
VOLUME_COLUMNS = ("volume", "quote_volume", "taker_buy_base_volume", "taker_buy_quote_volume")
REQUIRED_COLUMNS = ("open_time", "close_time", *PRICE_COLUMNS, *VOLUME_COLUMNS, "trade_count")


def utc(value) -> pd.Timestamp:
    result = pd.Timestamp(value)
    if pd.isna(result):
        raise ValueError("timestamp cannot be missing")
    return result.tz_localize("UTC") if result.tz is None else result.tz_convert("UTC")


def frame_sha256(frame: pd.DataFrame) -> str:
    """Fingerprint the exact supplied table, including row order and metadata."""
    return hashlib.sha256(frame.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()


def audit_ohlcv(
    frame: pd.DataFrame,
    *,
    symbol: str,
    interval: str = "1d",
    market: str = "spot",
    closed_at=None,
    expected_first=None,
    expected_last=None,
    minimum_rows: int = 1,
) -> dict:
    """Return machine-readable checks and window lineage; never mutate input."""
    step = pd.Timedelta(interval[:-1] + "D" if interval.endswith("d") else interval)
    if step <= pd.Timedelta(0) or minimum_rows < 1:
        raise ValueError("interval and minimum_rows must be positive")
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str, severity: str = "ERROR"):
        checks.append({"name": name, "passed": bool(passed), "severity": severity, "detail": detail})

    report = {"schema_version": SCHEMA_VERSION, "symbol": symbol, "market": market,
              "interval": interval, "rows": len(frame), "frame_sha256": frame_sha256(frame),
              "checks": checks, "first_open_time": None, "last_open_time": None,
              "missing_bars": None, "source_authenticity": "Not independently verified"}
    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    check("schema", not missing, f"Missing required columns: {missing}")
    check("history_length", len(frame) >= minimum_rows, f"{len(frame)} rows; minimum {minimum_rows}")
    if missing or frame.empty:
        report["status"] = "FAIL"
        return report
    if "symbol" in frame:
        check("symbol_identity", frame["symbol"].eq(symbol).all(), "Every row must match the requested symbol")
    else:
        check("symbol_identity", False, "Symbol identity is declared by filename only", "WARNING")
    if "market" in frame:
        check("market_identity", frame["market"].eq(market).all(), "Spot and futures must not be mixed")

    times = {}
    for column in ("open_time", "close_time"):
        labels = frame[column].astype(str)
        explicit_timezone = labels.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True).all()
        check(f"{column}_timezone", explicit_timezone, "Source timestamps must carry an explicit UTC offset")
        times[column] = pd.to_datetime(frame[column], utc=True, errors="coerce", format="mixed")
        check(f"{column}_valid", times[column].notna().all(), "Unparseable timestamps are rejected")
    opened, closed = times["open_time"], times["close_time"]
    if opened.notna().all() and closed.notna().all():
        report["first_open_time"] = opened.iloc[0].isoformat()
        report["last_open_time"] = opened.iloc[-1].isoformat()
        duplicate_count = int(opened.duplicated(keep=False).sum())
        report["duplicate_rows"] = duplicate_count
        check("unique_timestamps", duplicate_count == 0, f"{duplicate_count} rows have duplicate timestamps; identical copies also rejected")
        check("ordered_timestamps", opened.is_monotonic_increasing, "Rows must already be in chronological order")
        differences = opened.diff().dropna()
        check("continuity", differences.eq(step).all(), "24/7 bars must have exactly one interval between observations")
        check("interval_alignment", opened.eq(opened.dt.floor(step)).all(), "Open timestamps must align to UTC bar boundaries")
        duration = closed - opened
        valid_boundary = (duration >= step - pd.Timedelta(milliseconds=1)) & (duration < step)
        report["invalid_close_boundaries"] = int((~valid_boundary).sum())
        report["invalid_close_boundary_examples"] = opened.loc[~valid_boundary].head(5).map(lambda x: x.isoformat()).tolist()
        check("close_boundary", valid_boundary.all(),
              f"{report['invalid_close_boundaries']} invalid close timestamps; require the last millisecond of the bar")
        report["missing_bars"] = int(sum(max(int(delta // step) - 1, 0) for delta in differences))
        if closed_at is not None:
            check("closed_bars_only", (closed < utc(closed_at)).all(), "Unclosed and future candles cannot be used")
        if expected_first is not None:
            check("start_coverage", opened.iloc[0] <= utc(expected_first), f"Required history begins by {utc(expected_first).isoformat()}")
        if expected_last is not None:
            check("freshness", opened.iloc[-1] == utc(expected_last), f"Expected latest completed bar: {utc(expected_last).isoformat()}")

    numbers = frame[[*PRICE_COLUMNS, *VOLUME_COLUMNS, "trade_count"]].apply(pd.to_numeric, errors="coerce")
    finite = np.isfinite(numbers.to_numpy(dtype=float)).all()
    check("finite_numbers", finite, "NaN, infinity, and nonnumeric values are rejected")
    if finite:
        check("positive_prices", numbers[list(PRICE_COLUMNS)].gt(0).all().all(), "OHLC must be strictly positive")
        check("ohlc_consistency", (numbers["high"] >= numbers[["open", "low", "close"]].max(axis=1)).all()
              and (numbers["low"] <= numbers[["open", "high", "close"]].min(axis=1)).all(), "Low <= open/close <= high")
        check("nonnegative_volume", numbers[list(VOLUME_COLUMNS)].ge(0).all().all(), "Volume fields cannot be negative")
        trades = numbers["trade_count"]
        check("integer_trade_count", (trades.ge(0) & trades.eq(np.floor(trades))).all(), "Trade counts must be nonnegative integers")
        tolerance = 1e-8
        check("taker_volume_bounds", (numbers["taker_buy_base_volume"] <= numbers["volume"] * (1 + tolerance) + tolerance).all()
              and (numbers["taker_buy_quote_volume"] <= numbers["quote_volume"] * (1 + tolerance) + tolerance).all(),
              "Taker-buy volume cannot exceed total volume")
        check("latest_bar_liquid", numbers["volume"].iloc[-1] > 0 and numbers["quote_volume"].iloc[-1] > 0 and numbers["trade_count"].iloc[-1] > 0,
              "Latest decision bar must have positive base/quote volume and trades")
        check("historical_zero_volume", numbers["volume"].gt(0).all(), "Zero-volume historical bars are retained and flagged", "WARNING")
        jumps = numbers["close"].pct_change(fill_method=None).abs().gt(0.5).sum()
        check("large_price_moves", jumps == 0, f"{int(jumps)} close-to-close moves over 50%; inspect, do not automatically repair", "WARNING")
    report["status"] = "FAIL" if any(not c["passed"] and c["severity"] == "ERROR" for c in checks) else "PASS"
    return report


def require_quality(report: dict) -> None:
    if report["status"] != "PASS":
        failures = [item["name"] for item in report["checks"] if not item["passed"] and item["severity"] == "ERROR"]
        raise ValueError(f"{report['symbol']} data quality FAIL: {', '.join(failures)}")


def write_audit(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)
