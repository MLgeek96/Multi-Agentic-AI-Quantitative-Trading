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
