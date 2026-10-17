"""Run the teammate's Pairs PM under independent fund risk and evidence review."""

import argparse
import csv
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
from io import BytesIO, StringIO
import json
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from .coordinator import FundCoordinator
from .evidence import fingerprint
from .models import FundConfig, FundSnapshot, Holding, PairSpec, date
from .store import FundStore

ROOT = Path(__file__).resolve().parents[1]
DEMO_AS_OF = "2025-03-10"


def load_config(path):
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    unknown = set(values) - {f.name for f in fields(FundConfig)}
    if unknown:
        raise ValueError("unknown fund config fields: " + str(sorted(unknown)))
    if "pairs" in values:
        values["pairs"] = tuple(PairSpec(**p) for p in values["pairs"])
    return FundConfig(**values)


def rooted(path):
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def load_portfolio(path):
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    values["holdings"] = tuple(Holding(**h) for h in values.get("holdings", []))
    if "fx_to_usd" in values:
        quotes = values["fx_to_usd"]
        values["fx_to_usd"] = tuple(quotes.items()) if isinstance(quotes, dict) else tuple(tuple(v) for v in quotes)
    return FundSnapshot(**values)


def load_pairs_prices(path):
    raw = Path(path).read_bytes()
    # Check the raw header before pandas can rename duplicate columns.
    header = next(csv.reader(StringIO(raw.decode("utf-8-sig"))))
    if len(header) != len(set(header)):
        raise ValueError("pairs price columns must be unique")
    prices = pd.read_csv(BytesIO(raw), index_col=0)
    prices.index = pd.to_datetime(prices.index, errors="raise")
    return prices, hashlib.sha256(raw).hexdigest()


def demo_pairs(config, as_of):
    frames = []
    used = set()
    for i, spec in enumerate(config.pairs):
        if used.intersection((spec.asset1, spec.asset2)):
            raise ValueError("synthetic demo requires disjoint pair symbols; use research mode for shared assets")
        used.update((spec.asset1, spec.asset2))
        calendar = xcals.get_calendar(spec.calendar, start="2021-12-01", end=str((date(as_of) + pd.Timedelta(days=32)).date()))
        sessions = calendar.sessions_in_range("2022-01-01", as_of)
        rng = np.random.default_rng(42 + i)
        x = np.log(100.) + np.arange(len(sessions)) * .0004 + np.cumsum(rng.normal(0, .006, len(sessions)))
        spread = np.zeros(len(sessions))
        for t in range(1, len(sessions)):
            spread[t] = .94 * spread[t - 1] + rng.normal(0, .007)
        spread[-1] += .10
        y = .3 + .9 * x + spread
        frames.append(pd.DataFrame({spec.asset1: np.exp(y), spec.asset2: np.exp(x)}, index=sessions))
    prices = pd.concat(frames, axis=1)
    return prices, fingerprint({"basis": "SYNTHETIC_DEMO", "prices": prices.to_json(date_format="iso")})


def export_reports(report, directory):
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (report["cycle_id"] + ".json")
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    rows = []
    for group in report["pm_proposals"]["pairs"]["groups"]:
        for leg in group["legs"]:
            rows.append({"fund_as_of": report["as_of"], "pm": "pairs", "group": group["group"],
                         "symbol": leg["symbol"], "price_usd": leg["price_usd"],
                         "price_session": group["signal_session"], "market_closed": not group["actionable"]})
    pd.DataFrame(rows, columns=["fund_as_of", "pm", "group", "symbol", "price_usd", "price_session", "market_closed"]).to_csv(destination.with_suffix(".closing_prices.csv"), index=False)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/fund_agents.demo.json")
    parser.add_argument("--as-of", help="Fund valuation date (YYYY-MM-DD); exchange sessions must have closed")
    parser.add_argument("--pairs-prices", type=Path, help="Local Date-indexed equity close matrix; no network downloads")
    parser.add_argument("--portfolio", type=Path, help="Confirmed pairs-only snapshot with signed holdings, cash and dated FX")
    parser.add_argument("--pm-responses", type=Path, help="Optional imported Pairs PM and Chair diagnostic selections and LLM replies")
    args = parser.parse_args()
    try:
        cfg = load_config(args.config)
        if cfg.mode == "demo":
            if args.as_of or args.pairs_prices or args.portfolio:
                parser.error("demo generates synthetic inputs; use research mode for supplied inputs")
            as_of = DEMO_AS_OF
            prices, source = demo_pairs(cfg, as_of)
            basis = "SYNTHETIC_DEMO"
        else:
            if not args.as_of or not args.pairs_prices:
                parser.error("research requires --as-of and --pairs-prices")
            as_of = args.as_of
            decision_date = date(as_of)
            now = pd.Timestamp(datetime.now(timezone.utc))
            if decision_date.date() > now.date():
                parser.error("as_of cannot be a future date")
            for spec in cfg.pairs:
                calendar = xcals.get_calendar(spec.calendar, start=str((decision_date - pd.Timedelta(days=14)).date()),
                                              end=str((decision_date + pd.Timedelta(days=32)).date()))
                session = calendar.date_to_session(decision_date, direction="previous")
                if calendar.session_close(session).tz_convert("UTC") > now:
                    parser.error("all required exchange sessions must have closed before inference")
            prices, source = load_pairs_prices(args.pairs_prices)
            basis = "HISTORICAL_RESEARCH"
        snapshot = load_portfolio(args.portfolio) if args.portfolio else FundSnapshot.initial(cfg, as_of)
        if snapshot.as_of != as_of:
            raise ValueError("portfolio date must match --as-of")
        responses = json.loads(args.pm_responses.read_text(encoding="utf-8")) if args.pm_responses else None
        store = FundStore(rooted(cfg.state_path))
        try:
            report = FundCoordinator(cfg, store).run(prices, snapshot, pairs_source_sha256=source,
                                                     input_basis=basis, pm_responses=responses)
        finally:
            store.close()
        destination = export_reports(report, rooted(cfg.report_directory))
        print(json.dumps({"status": report["status"], "mode": cfg.mode, "report": str(destination),
                          "pm_status": {k: v["status"] for k, v in report["pm_proposals"].items()},
                          "marked_nav_usd": report["fund_risk"]["metrics"].get("marked_nav_usd"),
                          "linked_intent_groups": len(report["execution_receipts"]), "fills": 0,
                          "ai_status": {k: v["status"] for k, v in report["pm_representatives"].items()}}, indent=2))
        return 2 if report["status"] in ("INPUT_HOLD", "RISK_VETO", "BREAKER_LATCHED") else 0
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as exc:
        print(json.dumps({"status": "INPUT_HOLD", "error": str(exc), "fills": 0}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
