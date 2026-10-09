#!/usr/bin/env python3
"""Download checked Binance hourly archives for a 2026 OOS extension."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT")
USER_AGENT = "crypto-quant-research/1.0"


def download(url: str, output: Path) -> None:
    if output.exists():
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(output)
    print(f"downloaded {output.relative_to(PROJECT_ROOT)}")


def verify_checksum(archive: Path) -> None:
    checksum = Path(f"{archive}.CHECKSUM")
    expected = checksum.read_text(encoding="utf-8").split()[0].lower()
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"Checksum mismatch for {archive}")


def download_checked(url: str, output: Path) -> None:
    download(url, output)
    download(f"{url}.CHECKSUM", Path(f"{output}.CHECKSUM"))
    verify_checksum(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument(
        "--market",
        choices=("usdt_futures", "spot"),
        default="usdt_futures",
        help="Binance Data Vision market tree to download.",
    )
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument(
        "--end",
        default="2026-09-18",
        help="Exclusive UTC date; every completed day before it is required",
    )
    args = parser.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")
    if end <= start:
        raise ValueError("--end must be after --start")
    if start.year != end.year:
        raise ValueError("This focused downloader expects one calendar year")

    if args.market == "usdt_futures":
        data_root = PROJECT_ROOT / "datasets" / "usdt_futures"
        base = "https://data.binance.vision/data/futures/um"
        tree = Path("data") / "futures" / "um"
    else:
        data_root = PROJECT_ROOT / "datasets" / "spot"
        base = "https://data.binance.vision/data/spot"
        tree = Path("data") / "spot"
    final_complete_month = (end - pd.Timedelta(days=1)).tz_localize(None).to_period("M")
    for symbol_value in args.symbols:
        symbol = symbol_value.upper()
        month = start.tz_localize(None).to_period("M")
        while month < final_complete_month:
            filename = f"{symbol}-1h-{month}.zip"
            relative = tree / "monthly" / "klines" / symbol / "1h"
            url = f"{base}/monthly/klines/{symbol}/1h/{filename}"
            download_checked(url, data_root / relative / filename)
            month += 1

        first_daily = max(start, final_complete_month.to_timestamp().tz_localize("UTC"))
        for day in pd.date_range(first_daily, end - pd.Timedelta(days=1), freq="1D"):
            filename = f"{symbol}-1h-{day.date().isoformat()}.zip"
            relative = tree / "daily" / "klines" / symbol / "1h"
            url = f"{base}/daily/klines/{symbol}/1h/{filename}"
            try:
                download_checked(url, data_root / relative / filename)
            except HTTPError as error:
                raise RuntimeError(
                    f"Required completed-day archive is unavailable: {url} ({error.code})"
                ) from error

    print(f"Hourly archives verified through {(end - pd.Timedelta(days=1)).date()}")


if __name__ == "__main__":
    main()
