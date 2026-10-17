"""Run the Crypto PM and teammate Pairs PM under one fund coordinator."""

import argparse
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from crypto_agents.config import ROOT, load_config as load_crypto_config
from crypto_agents.data import demo_snapshot, load_local_snapshot
from crypto_agents.models import fingerprint
from crypto_quant.daily_portfolio import load_daily_config
from crypto_quant.data_quality import write_audit

from .coordinator import FundCoordinator
from .models import FundConfig, FundSnapshot, Holding, PairSpec, date
from .store import FundStore


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
        values["fx_to_usd"] = tuple(values["fx_to_usd"].items()) if isinstance(values["fx_to_usd"], dict) else tuple(tuple(v) for v in values["fx_to_usd"])
    return FundSnapshot(**values)


def load_pairs_prices(path):
    raw = Path(path).read_bytes()
    prices = pd.read_csv(BytesIO(raw), index_col=0)
    prices.index = pd.to_datetime(prices.index, errors="raise")
    if prices.columns.has_duplicates:
        raise ValueError("pairs price columns must be unique")
    return prices, hashlib.sha256(raw).hexdigest()


def demo_pairs(config, as_of):
    frames = []
    for i, spec in enumerate(config.pairs):
        calendar = xcals.get_calendar(spec.calendar, start="2021-12-01", end="2026-01-01")
        sessions = calendar.sessions_in_range("2022-01-01", as_of)
        rng = np.random.default_rng(42 + i)
        x = np.log(100.) + np.arange(len(sessions)) * .0004 + np.cumsum(rng.normal(0, .006, len(sessions)))
        spread = np.zeros(len(sessions))
        for t in range(1, len(sessions)):
            spread[t] = .94 * spread[t - 1] + rng.normal(0, .007)
        # A known synthetic divergence exercises the two-leg entry path.
        spread[-1] += .10
        y = .3 + .9 * x + spread
        frames.append(pd.DataFrame({spec.asset1: np.exp(y), spec.asset2: np.exp(x)}, index=sessions))
    prices = pd.concat(frames, axis=1)
    prices = prices.loc[:, ~prices.columns.duplicated()]
    return prices, fingerprint({"basis": "SYNTHETIC_DEMO", "seed": 42, "shock": .10, "as_of": as_of})


def export_reports(report, directory, crypto_market):
    destination = directory / (report["cycle_id"] + ".json")
    write_audit(report, destination)
    rows = []
    if crypto_market.quality_pass:
        for dataset in crypto_market.datasets:
            rows.append({"fund_as_of": report["as_of"], "pm": "crypto", "group": "spot:" + dataset.symbol,
                         "symbol": dataset.symbol, "price_usd": dataset.bars[-1].close * report["portfolio_before"]["usdt_to_usd"],
                         "price_session": dataset.bars[-1].date, "market_closed": False})
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
    parser.add_argument("--as-of", help="Completed UTC crypto daily candle label; also the fund valuation date")
    parser.add_argument("--pairs-prices", type=Path, help="Local Date-indexed equity close matrix; no network downloads")
    parser.add_argument("--crypto-data-dir", type=Path, default=ROOT / "live/market_data")
    parser.add_argument("--portfolio", type=Path, help="Confirmed fund snapshot with signed pair holdings, cash and dated FX")
    parser.add_argument("--pm-responses", type=Path, help="Optional imported crypto/pairs diagnostic selections and LLM replies")
    args = parser.parse_args()
    try:
        cfg = load_config(args.config)
        crypto_cfg = load_crypto_config(rooted(cfg.crypto_config_path))
        daily = load_daily_config(crypto_cfg.path("daily_config_path"))
        if cfg.mode == "demo":
            if args.as_of or args.pairs_prices or args.portfolio:
                parser.error("demo generates synthetic inputs; use research mode for supplied inputs")
            market, crypto_audit = demo_snapshot(daily.symbols)
            prices, source = demo_pairs(cfg, market.as_of)
        else:
            if not args.as_of or not args.pairs_prices:
                parser.error("research requires --as-of and --pairs-prices")
            decision_date = date(args.as_of)
            if decision_date.tz_localize("UTC") + pd.Timedelta(days=1) > pd.Timestamp(datetime.now(timezone.utc)):
                parser.error("as_of must identify a completed UTC daily candle")
            required = max(daily.parameter_training_days + max(s for _, s in daily.parameter_grid) + 5,
                           daily.covariance_window_days + 5,
                           crypto_cfg.hmm_training_days + 22 if crypto_cfg.strategy_mode == "hmm_experts" else 0)
            market, crypto_audit = load_local_snapshot(args.crypto_data_dir, daily.symbols, args.as_of, minimum_rows=required)
            prices, source = load_pairs_prices(args.pairs_prices)
        snapshot = load_portfolio(args.portfolio) if args.portfolio else FundSnapshot.initial(cfg, market.as_of)
        responses = json.loads(args.pm_responses.read_text(encoding="utf-8")) if args.pm_responses else None
        store = FundStore(rooted(cfg.state_path))
        try:
            report = FundCoordinator(cfg, store, rooted(cfg.crypto_config_path)).run(market, prices, snapshot,
                                                                                  pairs_source_sha256=source, pm_responses=responses)
        finally:
            store.close()
        destination = export_reports(report, rooted(cfg.report_directory), market)
        write_audit(crypto_audit, destination.with_suffix(".crypto_quality.json"))
        print(json.dumps({"status": report["status"], "mode": cfg.mode, "report": str(destination),
                          "pm_status": {k: v["status"] for k, v in report["pm_proposals"].items()},
                          "marked_nav_usd": report["fund_risk"]["metrics"].get("marked_nav_usd"),
                          "linked_intent_groups": len(report["execution_receipts"]), "fills": 0,
                          "ai_status": {k: v["status"] for k, v in report["pm_representatives"].items()}}, indent=2))
        return 2 if report["status"] in ("INPUT_HOLD", "RISK_VETO", "BREAKER_LATCHED") else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "INPUT_HOLD", "error": str(exc), "fills": 0}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
