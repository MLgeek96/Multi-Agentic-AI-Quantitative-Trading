#!/usr/bin/env python3
"""Verify and normalize Binance monthly kline archives for research."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from crypto_quant.data_quality import audit_ohlcv, write_audit
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"]
KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]
MARKET_PATHS = {
    "spot": PROJECT_ROOT / "datasets" / "spot" / "data" / "spot" / "monthly" / "klines",
    "usdt_futures": (
        PROJECT_ROOT
        / "datasets"
        / "usdt_futures"
        / "data"
        / "futures"
        / "um"
        / "monthly"
        / "klines"
    ),
}


def archive_paths(market: str, symbol: str, interval: str) -> list[Path]:
    """Return monthly archives plus any checked daily extension archives."""
    monthly_source = MARKET_PATHS[market] / symbol / interval
    archives = list(monthly_source.glob(f"{symbol}-{interval}-*.zip"))
    if market == "usdt_futures":
        daily_source = (
            PROJECT_ROOT
            / "datasets"
            / "usdt_futures"
            / "data"
            / "futures"
            / "um"
            / "daily"
            / "klines"
            / symbol
            / interval
        )
    else:
        daily_source = (
            PROJECT_ROOT
            / "datasets"
            / "spot"
            / "data"
            / "spot"
            / "daily"
            / "klines"
            / symbol
            / interval
        )
    archives.extend(daily_source.glob(f"{symbol}-{interval}-*.zip"))
    return sorted(archives, key=lambda path: (path.name, str(path.parent)))


@dataclass(frozen=True)
class DatasetSummary:
    market: str
    symbol: str
    interval: str
    archives: int
    rows: int
    expected_rows: int
    completeness_pct: float
    first_open_time: str
    last_open_time: str
    duplicate_timestamps: int
    gap_events: int
    missing_bars: int
    gaps: list[dict[str, str | int]]
    output: str
    output_sha256: str
    quality_status: str
    quality_file: str
    checksums_verified: bool
    source_archives: list[dict[str, str | bool]]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_archive(path: Path) -> None:
    checksum_path = Path(f"{path}.CHECKSUM")
    if not checksum_path.is_file():
        raise FileNotFoundError(f"Missing checksum for {path}")
    expected = checksum_path.read_text(encoding="utf-8").split()[0].lower()
    actual = sha256(path)
    if expected != actual:
        raise ValueError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")


def timestamp_unit(values: pd.Series) -> str:
    """Binance spot uses microseconds from 2025; older files use milliseconds."""
    return "us" if values.abs().median() >= 100_000_000_000_000 else "ms"


def read_archive(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"Expected one CSV in {path}, found {len(members)}")
        with archive.open(members[0]) as csv_file:
            frame = pd.read_csv(
                csv_file,
                header=None,
                names=KLINE_COLUMNS,
                dtype=str,
                low_memory=False,
            )

    # Some futures archives include a header while older archives and spot do not.
    frame = frame.loc[frame["open_time"].str.lower() != "open_time"].copy()
    if frame.empty:
        raise ValueError(f"No kline rows found in {path}")

    for column in KLINE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    invalid = frame[KLINE_COLUMNS].isna().any(axis=1)
    if invalid.any():
        raise ValueError(f"Found {int(invalid.sum())} malformed rows in {path}")

    open_raw = frame["open_time"].astype("int64")
    close_raw = frame["close_time"].astype("int64")
    frame["open_time"] = pd.to_datetime(open_raw, unit=timestamp_unit(open_raw), utc=True)
    frame["close_time"] = pd.to_datetime(close_raw, unit=timestamp_unit(close_raw), utc=True)
    frame["trade_count"] = frame["trade_count"].astype("int64")
    return frame


def prepare_dataset(
    market: str,
    symbol: str,
    interval: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    output_root: Path,
    verify: bool,
) -> DatasetSummary:
    source = MARKET_PATHS[market] / symbol / interval
    archives = archive_paths(market, symbol, interval)
    if not archives:
        raise FileNotFoundError(f"No archives found in {source}")

    frames: list[pd.DataFrame] = []
    source_records: list[dict[str, str | bool]] = []
    for archive in archives:
        if verify:
            verify_archive(archive)
        frames.append(read_archive(archive))
        source_records.append({"file": str(archive.relative_to(PROJECT_ROOT)), "sha256": sha256(archive), "checksum_verified": verify})

    frame = pd.concat(frames, ignore_index=True)
    frame = frame.loc[(frame["open_time"] >= start) & (frame["open_time"] < end)].copy()
    frame = frame.sort_values("open_time", kind="stable").reset_index(drop=True)
    if frame.empty:
        raise ValueError(f"{market}/{symbol} has no rows in the requested time range")

    duplicate_count = int(frame["open_time"].duplicated(keep=False).sum())
    if duplicate_count:
        value_columns = [column for column in KLINE_COLUMNS if column != "open_time"]
        conflicts = []
        for timestamp, group in frame.loc[frame["open_time"].duplicated(keep=False)].groupby(
            "open_time"
        ):
            if len(group[value_columns].drop_duplicates()) != 1:
                conflicts.append(timestamp)
        if conflicts:
            raise ValueError(
                f"{market}/{symbol} has conflicting duplicate timestamps: {conflicts[:5]}"
            )
        frame = frame.drop_duplicates("open_time", keep="last").reset_index(drop=True)

    expected_step = pd.Timedelta(interval)
    differences = frame["open_time"].diff()
    irregular = differences.dropna().loc[lambda values: values != expected_step]
    backwards = irregular[irregular <= pd.Timedelta(0)]
    if not backwards.empty:
        raise ValueError(f"{market}/{symbol} contains non-increasing timestamps")
    gap_differences = irregular[irregular > expected_step]
    missing_bars = int(sum((difference // expected_step) - 1 for difference in gap_differences))
    gaps = [
        {
            "after": frame.loc[index - 1, "open_time"].isoformat(),
            "before": frame.loc[index, "open_time"].isoformat(),
            "missing_bars": int((difference // expected_step) - 1),
        }
        for index, difference in gap_differences.items()
    ]
    expected_rows = int((end - start) // expected_step)

    frame.insert(0, "market", market)
    frame.insert(1, "symbol", symbol)
    output_dir = output_root / market
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{symbol}_{interval}.csv.gz"
    frame.to_csv(output_path, index=False, compression="gzip", date_format="%Y-%m-%dT%H:%M:%S.%f%z")
    quality = audit_ohlcv(frame, symbol=symbol, market=market, interval=interval,
                         closed_at=end, expected_last=end - expected_step)
    quality.update(output_sha256=sha256(output_path), checksums_verified=verify,
                   source_archives=source_records,
                   note="Gaps remain visible. Listing-dependent start dates need independent eligibility review.")
    quality_path = output_path.with_name(f"{symbol}_{interval}.quality.json")
    write_audit(quality, quality_path)

    return DatasetSummary(
        market=market,
        symbol=symbol,
        interval=interval,
        archives=len(archives),
        rows=len(frame),
        expected_rows=expected_rows,
        completeness_pct=round(100 * len(frame) / expected_rows, 6),
        first_open_time=frame["open_time"].iloc[0].isoformat(),
        last_open_time=frame["open_time"].iloc[-1].isoformat(),
        duplicate_timestamps=duplicate_count,
        gap_events=len(gap_differences),
        missing_bars=missing_bars,
        gaps=gaps,
        output=str(output_path.relative_to(PROJECT_ROOT)),
        output_sha256=quality["output_sha256"],
        quality_status=quality["status"],
        quality_file=str(quality_path.relative_to(PROJECT_ROOT)),
        checksums_verified=verify,
        source_archives=source_records,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--markets", nargs="+", choices=sorted(MARKET_PATHS), default=sorted(MARKET_PATHS))
    parser.add_argument("--interval", default="1h", help="Pandas-compatible interval; default: 1h")
    parser.add_argument("--start", default="2020-01-01", help="Inclusive UTC date")
    parser.add_argument("--end", default="2026-01-01", help="Exclusive UTC date")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "processed")
    parser.add_argument("--skip-checksums", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")
    if end <= start:
        raise ValueError("--end must be later than --start")

    output_root = args.output.resolve()
    summaries = [
        prepare_dataset(
            market=market,
            symbol=symbol.upper(),
            interval=args.interval,
            start=start,
            end=end,
            output_root=output_root,
            verify=not args.skip_checksums,
        )
        for market in args.markets
        for symbol in args.symbols
    ]

    manifest_path = output_root / "manifest.json"
    current_records = [asdict(summary) for summary in summaries]
    records_by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    if manifest_path.exists():
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for record in existing_manifest.get("datasets", []):
            key = (str(record["market"]), str(record["symbol"]), str(record["interval"]))
            records_by_key[key] = record
    for record in current_records:
        key = (str(record["market"]), str(record["symbol"]), str(record["interval"]))
        records_by_key[key] = record

    manifest = {
        "range": {"start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()},
        "last_run_markets": list(args.markets),
        "last_run_symbols": [symbol.upper() for symbol in args.symbols],
        "checksums_verified": not args.skip_checksums,
        "datasets": list(records_by_key.values()),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    for summary in summaries:
        print(
            f"{summary.market:13} {summary.symbol:7} "
            f"rows={summary.rows:,} gaps={summary.gap_events} "
            f"missing_bars={summary.missing_bars} -> {summary.output}"
        )
    print(f"Manifest -> {manifest_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
