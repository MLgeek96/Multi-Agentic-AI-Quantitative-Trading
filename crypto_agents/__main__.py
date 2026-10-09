"""Run one audited local cycle: python -m crypto_agents --help."""

import argparse
from dataclasses import replace
import json
from pathlib import Path

from crypto_quant.daily_portfolio import load_daily_config
from crypto_quant.data_quality import write_audit

from .config import ROOT, load_config
from .data import demo_snapshot, load_local_snapshot
from .meta import MetaAgent
from .models import Holding, PortfolioSnapshot
from .store import SQLiteStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/agents.demo.json")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "live/market_data")
    parser.add_argument("--as-of", help="UTC date labeling a completed daily candle; required for research")
    parser.add_argument("--portfolio", type=Path, help="JSON with as_of, cash_usdt, peak_equity_usdt and holdings")
    parser.add_argument("--llm-response", type=Path, help="Optional imported research reply; never changes orders")
    parser.add_argument("--scenario", choices=("normal", "reduce", "breaker", "flagged"), default="normal")
    args = parser.parse_args()
    cfg = load_config(args.config)
    daily = load_daily_config(cfg.path("daily_config_path"))
    if cfg.mode == "demo":
        cfg = replace(cfg, account_key=f"{cfg.account_key}-{args.scenario}")
        if args.scenario == "reduce":
            cfg = replace(cfg, maximum_asset_weight=0.1)
        market, audit = demo_snapshot(daily.symbols, scenario=args.scenario)
    else:
        if not args.as_of or args.scenario != "normal":
            parser.error("research requires --as-of and does not accept demo scenarios")
        required = max(daily.parameter_training_days + max(s for _, s in daily.parameter_grid) + 5,
                       daily.covariance_window_days + 5, cfg.hmm_training_days + 22 if cfg.strategy_mode == "hmm_experts" else 0)
        market, audit = load_local_snapshot(args.data_dir, daily.symbols, args.as_of, minimum_rows=required)
    cash = cfg.initial_equity_usdt * (0.6 if cfg.mode == "demo" and args.scenario == "breaker" else 1)
    portfolio = PortfolioSnapshot(market.as_of, cash, peak_equity_usdt=cfg.initial_equity_usdt)
    if args.portfolio:
        data = json.loads(args.portfolio.read_text(encoding="utf-8"))
        data["holdings"] = tuple(Holding(**h) for h in data.get("holdings", []))
        portfolio = PortfolioSnapshot(**data)
    store = SQLiteStore(cfg.path("state_path"))
    try:
        raw = args.llm_response.read_text(encoding="utf-8") if args.llm_response else None
        report = MetaAgent(cfg, store).run(market, portfolio, llm_response=raw)
    finally:
        store.close()
    destination = cfg.path("report_directory") / f"{report['cycle_id']}.json"
    write_audit(report, destination)
    write_audit(audit, destination.with_name(f"{report['cycle_id']}.quality.json"))
    print(json.dumps({"status": report["status"], "data_basis": market.basis, "report": str(destination),
                      "approved_intents": len(report["execution_receipts"]), "fills": 0, "llm_status": report["llm_research"]["status"]}, indent=2))
    return 2 if report["status"] in ("DATA_QUALITY_VETO", "BREAKER_LATCHED", "INPUT_HOLD", "RISK_VETO") else 0


if __name__ == "__main__":
    raise SystemExit(main())
