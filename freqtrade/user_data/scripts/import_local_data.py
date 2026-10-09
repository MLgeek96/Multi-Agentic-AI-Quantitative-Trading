from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT")


def convert_file(source: Path, destination: Path) -> tuple[int, str, str]:
    frame = pd.read_csv(source, compression="gzip")
    required = ["open_time", "open", "high", "low", "close", "volume"]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"{source} is missing columns: {missing}")

    output = frame[required].rename(columns={"open_time": "date"}).copy()
    output["date"] = pd.to_datetime(output["date"], utc=True)
    output = output.sort_values("date").drop_duplicates("date", keep="last")
    output = output[["date", "open", "high", "low", "close", "volume"]]

    destination.parent.mkdir(parents=True, exist_ok=True)
    output.reset_index(drop=True).to_feather(destination)
    return len(output), output["date"].iloc[0].isoformat(), output["date"].iloc[-1].isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import this repository's prepared Binance data.")
    parser.add_argument(
        "--market",
        choices=("usdt_futures", "spot"),
        default="usdt_futures",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=None,
    )
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    args = parser.parse_args()

    source_root = args.source or Path(f"processed/{args.market}")
    if args.destination is not None:
        destination_root = args.destination
    elif args.market == "spot":
        destination_root = Path("freqtrade/user_data/data/binance")
    else:
        destination_root = Path("freqtrade/user_data/data/binanceusdm/futures")

    for symbol in (value.upper() for value in args.symbols):
        source = source_root / f"{symbol}_1h.csv.gz"
        if not source.is_file():
            raise FileNotFoundError(f"Missing prepared {args.market} data: {source}")
        base = symbol.removesuffix("USDT")
        if args.market == "spot":
            destination = destination_root / f"{base}_USDT-1h.feather"
        else:
            destination = destination_root / f"{base}_USDT_USDT-1h-futures.feather"
        rows, first, last = convert_file(source, destination)
        print(f"{symbol}: {rows:,} rows, {first} through {last} -> {destination}")


if __name__ == "__main__":
    main()
