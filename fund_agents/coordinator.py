"""Coordinate the connected PMs, final risk, execution records and AI evidence."""

from datetime import datetime, timezone
from uuid import uuid4

from crypto_agents.models import RiskState, fingerprint, json_value

from . import __version__
from .crypto import CryptoPM
from .pairs import PairsPM
from .representative import CommitteeChairAgent, PMRepresentative
from .risk import FundRisk


class FundCoordinator:
    def __init__(self, config, store, crypto_config_path):
        self.config, self.store = config, store
        self.crypto = CryptoPM(config, crypto_config_path)
        self.pairs = PairsPM(config)
        self.risk = FundRisk(config)

    def run(self, crypto_market, pairs_prices, snapshot, *, pairs_source_sha256, pm_responses=None):
        if self.config.mode == "research" and crypto_market.basis == "SYNTHETIC_DEMO":
            raise ValueError("research fund cannot use synthetic Crypto PM inputs")
        if crypto_market.as_of != snapshot.as_of:
            raise ValueError("fund and crypto dates must match")
        if pm_responses is not None and (not isinstance(pm_responses, dict) or set(pm_responses) - {"crypto", "pairs", "chair"}):
            raise ValueError("PM responses can contain only crypto, pairs and chair envelopes")
        cycle_id = str(uuid4())
        with self.store.transaction():
            context = self.store.state(self.config.account_key) or {}
            previous = context.get("fund")
            if previous and previous["last_session"] > snapshot.as_of:
                raise ValueError("fund dates cannot run backwards; use a different replay account")
            crypto_state = RiskState(**context["crypto"]) if context.get("crypto") else None
            crypto = self.crypto.propose(crypto_market, snapshot, crypto_state)
            pairs = self.pairs.propose(pairs_prices, snapshot, source_sha256=pairs_source_sha256)
            proposals = (crypto, pairs)
            decision = self.risk.review(proposals, snapshot, previous)
            self.store.save_decision(decision)
            receipts = self.store.record(decision, snapshot)
            responses = pm_responses or {}
            representatives = {p.pm: PMRepresentative(p, decision).memo(responses.get(p.pm)) for p in proposals}
            chair = CommitteeChairAgent(proposals, decision, representatives).memo(responses.get("chair"))
            state = {"fund": decision["state"], "crypto": crypto.diagnostics.get("risk_state", context.get("crypto"))}
            self.store.save_state(self.config.account_key, state)
            status = decision["status"]
            if status == "REVIEWED":
                status = "INTENTS_RECORDED" if receipts else "NO_ACTION"
            report = json_value({
                "schema_version": "two-pm-fund-v1", "architecture_version": __version__, "cycle_id": cycle_id,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(), "as_of": snapshot.as_of,
                "mode": self.config.mode, "execution_mode": "record_only", "status": status,
                "config": self.config, "config_sha256": fingerprint(self.config),
                "portfolio_before": snapshot, "portfolio_after": snapshot,
                "pm_proposals": {p.pm: p for p in proposals}, "fund_risk": decision,
                "execution_receipts": receipts, "pm_representatives": representatives,
                "committee_chair": chair,
                "momentum_pm": {"status": "NOT_CONNECTED", "reserved_cash_usd": snapshot.momentum_cash_usd},
                "limitations": [
                    "Execution records linked intentions only. No orders, fills, fees charged or changed holdings.",
                    "AI supports imported, digest-checked replies and diagnostic tool selections; no automatic LLM provider calls.",
                    "Signed pair targets are research quantities; executable quotes, board lots, borrow availability and margin require a future fill adapter.",
                    "Supplied snapshots carry confirmed positions. Recorded intents never become next-day holdings.",
                ],
            })
            self.store.save_cycle(cycle_id, self.config.account_key, report)
        return report
