"""Use the existing Crypto Meta/Regime/Signal/Position/Risk implementation."""

from dataclasses import replace

from crypto_agents.config import load_config
from crypto_agents.meta import MetaAgent
from crypto_agents.models import Holding, PortfolioSnapshot, fingerprint
from crypto_agents.store import SQLiteStore

from .models import PMProposal, TargetGroup, TargetLeg


class CryptoPM:
    def __init__(self, fund_config, crypto_config_path):
        self.fund = fund_config
        cfg = load_config(crypto_config_path)
        if cfg.mode != fund_config.mode:
            raise ValueError("Crypto PM and fund mode must match")
        self.config = replace(cfg, account_key=fund_config.account_key + ":crypto",
                              initial_equity_usdt=fund_config.crypto_budget_usd)

    def propose(self, market, snapshot, previous_risk_state=None):
        fx = snapshot.usdt_to_usd
        try:
            if market.as_of != snapshot.as_of:
                raise ValueError("Crypto PM and fund dates differ")
            holdings = tuple(Holding(h.symbol, h.units, h.entry_price_usd / fx)
                             for h in snapshot.holdings if h.pm == "crypto")
            if any(h.group != "spot:" + h.symbol for h in snapshot.holdings if h.pm == "crypto"):
                raise ValueError("crypto holdings need spot:SYMBOL group identities")
            cfg = replace(self.config, initial_equity_usdt=self.fund.crypto_budget_usd / fx)
            portfolio = PortfolioSnapshot(snapshot.as_of, snapshot.crypto_cash_usd / fx, holdings,
                                          peak_equity_usdt=cfg.initial_equity_usdt)
            store = SQLiteStore(":memory:")
            try:
                if previous_risk_state is not None:
                    store.save_state(cfg.account_key, previous_risk_state)
                report = MetaAgent(cfg, store).run(market, portfolio)
            finally:
                store.close()
            if report["status"] in ("DATA_QUALITY_VETO", "INPUT_HOLD"):
                raise ValueError("Crypto PM status: " + report["status"])
            quantities = {d.symbol: portfolio.units(d.symbol) for d in market.datasets}
            for review in report["risk_decision"]["reviews"]:
                approved = review["approved"]
                if approved:
                    quantities[approved["symbol"]] += approved["units"] * (1 if approved["side"] == "BUY" else -1)
            groups = tuple(TargetGroup("crypto", "spot:" + symbol, snapshot.as_of, snapshot.as_of,
                                       (TargetLeg(symbol, max(0., units), market.dataset(symbol).bars[-1].close * fx),),
                                       "Existing Crypto PM target after its local Risk veto")
                           for symbol, units in sorted(quantities.items()))
            diagnostics = {"engine": "crypto_agents.MetaAgent", "data_basis": market.basis,
                           "status": report["status"], "proposed_weights": report["proposed_weights"],
                           "regime": report["regime"], "specialist_signals": report["specialist_signals"],
                           "risk_alerts": report["risk_decision"]["alerts"],
                           "risk_state": report["risk_decision"]["state"],
                           "risk_reviews": report["risk_decision"]["reviews"],
                           "snapshot_sha256": report["snapshot_sha256"], "usdt_to_usd": fx,
                           "valuation_note": snapshot.valuation_note}
            return PMProposal("crypto", "READY", groups, diagnostics, fingerprint(diagnostics))
        except (ValueError, KeyError) as exc:
            diagnostics = {"error": str(exc)}
            return PMProposal("crypto", "INPUT_HOLD", (), diagnostics, fingerprint(diagnostics))
