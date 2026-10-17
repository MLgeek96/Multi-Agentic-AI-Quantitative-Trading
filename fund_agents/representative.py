"""PM diagnostic tools and the existing advisory LLM reply boundary."""

import json

from crypto_agents.models import fingerprint, json_value
from crypto_agents.research import ResearchAgent


class PMRepresentative:
    def __init__(self, proposal, risk_decision):
        self.proposal = proposal
        self.risk = risk_decision
        self.calls = []
        self.tools = {
            "inspect_signals": self.inspect_signals,
            "inspect_model_health": self.inspect_model_health,
            "inspect_positions": self.inspect_positions,
        }

    def inspect_signals(self):
        return {"status": self.proposal.status, "groups": json_value(self.proposal.groups)}

    def inspect_model_health(self):
        return self.proposal.diagnostics

    def inspect_positions(self):
        return {"pm_reviews": [r for r in self.risk["reviews"] if r["proposed"]["pm"] == self.proposal.pm],
                "fund_risk_status": self.risk["status"], "fund_risk_alerts": self.risk["alerts"],
                "execution_mode": "record_only", "filled_orders": 0}

    def call_tool(self, name):
        if name not in self.tools:
            raise ValueError("Unknown PM diagnostic tool: " + str(name))
        result = self.tools[name]()
        record = {"pm": self.proposal.pm, "tool": name, "result": result, "result_sha256": fingerprint(result)}
        self.calls.append(record)
        return result

    def memo(self, envelope=None):
        """Optional {tool_names, reply} envelope; imported AI never reaches risk."""
        selection_error = None
        reply = None
        names = list(self.tools)
        if envelope is not None:
            try:
                if not isinstance(envelope, dict) or set(envelope) != {"tool_names", "reply"}:
                    raise ValueError("PM envelope needs tool_names and reply only")
                names = envelope["tool_names"]
                if not isinstance(names, list) or not names or len(names) != len(set(names)) or any(not isinstance(n, str) or n not in self.tools for n in names):
                    raise ValueError("tool_names must be a unique nonempty list of allowed tools")
                reply = json.dumps(envelope["reply"], allow_nan=False) if envelope["reply"] is not None else None
            except (ValueError, TypeError) as exc:
                names, selection_error = list(self.tools), str(exc)
        evidence = {name: self.call_tool(name) for name in names}
        facts = {"pm": self.proposal.pm, "as_of": self.risk["as_of"],
                 "evidence_sha256": self.proposal.evidence_sha256, "tool_results": evidence,
                 "metrics": dict(self.risk["metrics"]), "risk_status": self.risk["status"]}
        audit = ResearchAgent().review(facts, reply)
        audit["system_prompt"] = audit["system_prompt"].replace("crypto research analyst", self.proposal.pm + " PM analyst")
        audit["prompt_version"] = "fund-pm-v1"
        audit["available_tools"] = {name: {"arguments": {}, "read_only": True} for name in self.tools}
        audit["tool_calls"] = self.calls
        audit["tool_selection_source"] = "imported request" if envelope is not None and selection_error is None else "deterministic default diagnostics"
        audit["computed_memo"] = {"summary": f"{self.proposal.pm.title()} PM {self.proposal.status}; fund risk {self.risk['status']}.",
                                  "evidence_sha256": fingerprint(facts), "execution": "Intent records only; zero fills"}
        if selection_error:
            audit.update(status="REJECTED", rejection_reason=selection_error)
        return audit


class CommitteeChairAgent:
    """AI Investment Committee Chair synthesizing PM memos, cross-sleeve risk, and phantom book."""

    def __init__(
        self,
        proposals: tuple[ object, ...],
        risk_decision: dict[str, object],
        pm_memos: dict[str, dict[str, object]],
    ) -> None:
        self.proposals = proposals
        self.risk = risk_decision
        self.pm_memos = pm_memos
        self.calls: list[dict[str, object]] = []
        self.tools = {
            "inspect_cross_sleeve_exposure": self.inspect_cross_sleeve_exposure,
            "inspect_phantom_book": self.inspect_phantom_book,
            "inspect_pm_memos": self.inspect_pm_memos,
        }

    def inspect_cross_sleeve_exposure(self) -> dict[str, object]:
        """Inspect symbol gross overlap and approved exposure across all PM sleeves."""
        symbol_gross: dict[str, float] = {}
        for group in self.risk.get("approved_groups", []):
            for leg in group.get("legs", []):
                sym = str(leg["symbol"])
                symbol_gross[sym] = symbol_gross.get(sym, 0.0) + abs(float(leg["units"]) * float(leg["price_usd"]))
        return {
            "fund_risk_status": self.risk["status"],
            "fund_risk_alerts": self.risk["alerts"],
            "symbol_gross_usd": symbol_gross,
            "metrics": dict(self.risk["metrics"]),
        }

    def inspect_phantom_book(self) -> dict[str, object]:
        """Inspect shadow accounting of proposed vs. risk-approved gross exposure."""
        return dict(self.risk.get("phantom_book", {}))

    def inspect_pm_memos(self) -> dict[str, object]:
        """Inspect computed and validated status across connected PM representatives."""
        return {
            pm: {
                "status": memo.get("status"),
                "computed_summary": memo.get("computed_memo", {}).get("summary"),
                "evidence_sha256": memo.get("computed_memo", {}).get("evidence_sha256"),
            }
            for pm, memo in self.pm_memos.items()
        }

    def call_tool(self, name: str) -> dict[str, object]:
        """Invoke a read-only committee chair tool and record its SHA-256 digest."""
        if name not in self.tools:
            raise ValueError("Unknown Committee Chair diagnostic tool: " + str(name))
        result = self.tools[name]()
        record = {"role": "chair", "tool": name, "result": result, "result_sha256": fingerprint(result)}
        self.calls.append(record)
        return result

    def memo(self, envelope: dict[str, object] | None = None) -> dict[str, object]:
        """Generate or fact-check the Investment Committee Chair brief."""
        selection_error: str | None = None
        reply: str | None = None
        names = list(self.tools)
        if envelope is not None:
            try:
                if not isinstance(envelope, dict) or set(envelope) != {"tool_names", "reply"}:
                    raise ValueError("Chair envelope needs tool_names and reply only")
                raw_names = envelope["tool_names"]
                if (
                    not isinstance(raw_names, list)
                    or not raw_names
                    or len(raw_names) != len(set(raw_names))
                    or any(not isinstance(n, str) or n not in self.tools for n in raw_names)
                ):
                    raise ValueError("tool_names must be a unique nonempty list of allowed chair tools")
                names = raw_names
                reply = json.dumps(envelope["reply"], allow_nan=False) if envelope["reply"] is not None else None
            except (ValueError, TypeError) as exc:
                names, selection_error = list(self.tools), str(exc)
        evidence = {name: self.call_tool(name) for name in names}
        phantom = self.risk.get("phantom_book", {})
        throttled_usd = float(phantom.get("throttled_gross_usd", 0.0)) if isinstance(phantom, dict) else 0.0
        metrics = dict(self.risk["metrics"])
        metrics["throttled_gross_usd"] = throttled_usd
        facts = {
            "role": "committee_chair",
            "as_of": self.risk["as_of"],
            "tool_results": evidence,
            "metrics": metrics,
            "risk_status": self.risk["status"],
        }
        audit = ResearchAgent().review(facts, reply)
        audit["system_prompt"] = audit["system_prompt"].replace(
            "crypto research analyst", "Investment Committee Chair"
        )
        audit["prompt_version"] = "fund-chair-v1"
        audit["available_tools"] = {name: {"arguments": {}, "read_only": True} for name in self.tools}
        audit["tool_calls"] = self.calls
        audit["tool_selection_source"] = (
            "imported request" if envelope is not None and selection_error is None else "deterministic default diagnostics"
        )
        audit["computed_memo"] = {
            "summary": (
                f"Committee Chair reviewed {len(self.pm_memos)} PM sleeves; "
                f"fund risk {self.risk['status']}; throttled gross USD {throttled_usd:,.2f}."
            ),
            "evidence_sha256": fingerprint(facts),
            "execution": "Advisory only; zero trading authority",
        }
        if selection_error:
            audit.update(status="REJECTED", rejection_reason=selection_error)
        return audit

