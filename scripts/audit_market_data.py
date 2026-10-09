#!/usr/bin/env python3
"""Audit local daily/hourly OHLCV files without changing their contents."""

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crypto_quant.data_quality import audit_ohlcv, write_audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--market", choices=("spot", "usdt_futures"), default="spot")
    parser.add_argument("--closed-at", required=True, help="UTC timestamp of data availability cutoff")
    parser.add_argument("--expected-last", help="Required last candle open time")
    parser.add_argument("--minimum-rows", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("runs/quality/audit.json"))
    args = parser.parse_args()
    reports = []
    for path in args.files:
        raw = path.read_bytes()
        frame = pd.read_csv(BytesIO(raw), compression="gzip" if path.name.endswith(".gz") else None)
        symbol = path.name.split("_")[0]
        report = audit_ohlcv(frame, symbol=symbol, interval=args.interval, market=args.market,
                             closed_at=args.closed_at, expected_last=args.expected_last, minimum_rows=args.minimum_rows)
        report.update(file=path.name, file_sha256=hashlib.sha256(raw).hexdigest())
        reports.append(report)
    bundle = {"status": "PASS" if all(r["status"] == "PASS" for r in reports) else "FAIL", "datasets": reports}
    write_audit(bundle, args.output)
    print(json.dumps({"status": bundle["status"], "output": str(args.output),
                      "datasets": [{"symbol": r["symbol"], "status": r["status"], "rows": r["rows"],
                                    "last_open_time": r["last_open_time"], "failed_checks": [c["name"] for c in r["checks"] if not c["passed"] and c["severity"] == "ERROR"]}
                                   for r in reports]}, indent=2))
    return 0 if bundle["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
