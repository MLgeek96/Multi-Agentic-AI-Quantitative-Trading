#!/usr/bin/env python3
"""Download official 2026 Binance futures archives and FRED macro CSVs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BINANCE_ROOT = PROJECT_ROOT / "datasets" / "usdt_futures"
FRED_ROOT = PROJECT_ROOT / "datasets" / "external" / "fred"
USER_AGENT = "crypto-quant-research/1.0"


def download(url: str, output: Path) -> None:
    if output.exists():
        print(f"exists {output.relative_to(PROJECT_ROOT)}")
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


def download_binance() -> None:
    base = "https://data.binance.vision/data/futures/um"
    for symbol in ("BTCUSDT", "ETHUSDT"):
        for month in range(1, 9):
            filename = f"{symbol}-1d-2026-{month:02d}.zip"
            relative = Path("data") / "futures" / "um" / "monthly" / "klines" / symbol / "1d"
            url = f"{base}/monthly/klines/{symbol}/1d/{filename}"
            archive = BINANCE_ROOT / relative / filename
            download(url, archive)
            download(f"{url}.CHECKSUM", Path(f"{archive}.CHECKSUM"))
            verify_checksum(archive)
        daily_root = BINANCE_ROOT / "data" / "futures" / "um" / "daily" / "klines" / symbol / "1d"
        for day in range(1, 17):
            archive = daily_root / f"{symbol}-1d-2026-09-{day:02d}.zip"
            if archive.exists():
                verify_checksum(archive)


def download_fred() -> None:
    FRED_ROOT.mkdir(parents=True, exist_ok=True)
    for series in ("SP500", "NASDAQCOM", "VIXCLS", "DGS10", "DFF"):
        url = (
            "https://fred.stlouisfed.org/graph/fredgraph.csv"
            f"?id={series}&cosd=2019-01-01&coed=2026-09-16"
        )
        download(url, FRED_ROOT / f"{series}.csv")


def main() -> None:
    download_binance()
    download_fred()


if __name__ == "__main__":
    main()
