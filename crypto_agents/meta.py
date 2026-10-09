"""Local orchestration, probability-weighted arbitration and atomic audit trail."""

from datetime import datetime, timezone
from uuid import uuid4

from crypto_quant.daily_portfolio import load_daily_config

from . import __version__
from .execution import ExecutionAgent
from .models import fingerprint, json_value
from .position import PositionAgent
from .regime import RegimeAgent
from .research import ResearchAgent
from .risk import RiskAgent
from .signal import SignalAgent, blend


class MetaAgent:
    def __init__(self, config, store):
        self.config, self.store = config, store
        self.daily = load_daily_config(config.path("daily_config_path"))
        self.regime = RegimeAgent(config)
        self.signal = SignalAgent(self.daily)
        self.position = PositionAgent(config, self.daily)
        self.risk = RiskAgent(config)
        self.execution = ExecutionAgent(store)
        self.research = ResearchAgent()

    def run(self, market, portfolio, *, llm_response=None):
        if market.as_of != portfolio.as_of:
            raise ValueError("market and portfolio dates must match")
        if self.config.mode == "research" and market.basis == "SYNTHETIC_DEMO":
            raise ValueError("research config cannot approve synthetic fixtures")
        symbols = {d.symbol for d in market.datasets}
        if symbols != set(self.daily.symbols) or any(h.symbol not in symbols for h in portfolio.holdings):
            raise ValueError("snapshot/portfolio universe differs from daily configuration")
        cycle_id = str(uuid4())
        config_hash = fingerprint((self.config, {k: str(v) for k, v in vars(self.daily).items()}))
        events = [("meta.start", {"as_of": market.as_of, "snapshot_sha256": fingerprint(market), "config_sha256": config_hash})]
        regime, signals, blended, orders, weights = None, (), (), (), None
        warnings = []
        with self.store.transaction():
            previous = self.store.load_state(self.config.account_key)
            if market.quality_pass:
                try:
                    regime = self.regime.estimate(market)
                    events.append(("regime.estimated", regime))
                    signals = self.signal.generate(market, portfolio)
                    events.append(("signal.specialists", signals))
                    blended = blend(signals, regime)
                    events.append(("meta.arbitration", blended))
                    orders, weights = self.position.propose(blended, market, portfolio)
                    events.append(("position.proposed", {"weights": weights, "orders": orders}))
                except ValueError as exc:
                    warnings.append(f"MODEL_UNAVAILABLE: {exc}")
                    events.append(("meta.input_hold", {"reason": str(exc)}))
            decision = self.risk.review(orders, market, portfolio, previous, cycle_id)
            self.store.save_decision(decision)
            events.append(("risk.reviewed", decision))
            if decision.alerts:
                for module in ("meta", "regime", "signal", "position", "execution", "research"):
                    events.append((f"notify.{module}", {"alerts": decision.alerts}))
            receipts = self.execution.record(decision)
            events.append(("execution.record_only", receipts))
            status = "DATA_QUALITY_VETO" if not market.quality_pass else (
                "BREAKER_LATCHED" if decision.state.breaker_latched else (
                    "INTENTS_RECORDED" if receipts else (
                        "RISK_VETO" if decision.reviews else ("INPUT_HOLD" if weights is None else "NO_ACTION"))))
            facts = json_value({"as_of": market.as_of, "data_basis": market.basis, "status": status,
                                "metrics": {"marked_equity_usdt": decision.marked_equity_usdt,
                                            "approved_intents": len(receipts), "filled_orders": 0,
                                            "realized_pnl": None}, "proposed_weights": weights,
                                "risk_alerts": decision.alerts, "portfolio": portfolio,
                                "limitation": "Record-only intentions; no post-trade P&L or fills"})
            research = self.research.review(facts, llm_response)
            research["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
            events.append(("research.reviewed", research))
            report = json_value({"cycle_id": cycle_id, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                                 "architecture_version": __version__, "as_of": market.as_of, "mode": self.config.mode,
                                 "execution_mode": "record_only", "status": status,
                                 "data_basis": market.basis, "data_quality_pass": market.quality_pass,
                                 "audit_sha256": market.audit_sha256, "snapshot_sha256": fingerprint(market),
                                 "config": self.config, "config_sha256": config_hash,
                                 "regime": regime, "specialist_signals": signals, "blended_signals": blended,
                                 "proposed_weights": weights, "proposed_orders": orders, "risk_decision": decision,
                                 "execution_receipts": receipts, "portfolio_before": portfolio, "portfolio_after": portfolio,
                                 "llm_research": research, "warnings": warnings,
                                 "events": [{"stage": stage, "payload": payload} for stage, payload in events],
                                 "notice": "Local Spot research; record-only execution. No orders, fills or portfolio changes. "
                                           "LLM output is advisory. Data PASS is structural quality only."})
            self.store.save_state(self.config.account_key, decision.state)
            self.store.save_cycle(cycle_id, self.config.account_key, report, events)
        return report
