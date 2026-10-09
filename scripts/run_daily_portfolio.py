#!/usr/bin/env python3
"""Run the public-data daily signal and paper-portfolio pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crypto_quant.daily_portfolio import load_daily_config, run_daily_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "daily_portfolio.json",
    )
    parser.add_argument(
        "--as-of",
        help="UTC timestamp override for reproducible tests; production should use exchange time",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_daily_config(args.config)
    now = pd.Timestamp(args.as_of) if args.as_of else None
    manifest = run_daily_pipeline(config, now=now)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
