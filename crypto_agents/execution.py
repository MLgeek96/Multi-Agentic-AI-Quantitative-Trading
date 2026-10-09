"""Only record approved intents. No broker, network, fills or portfolio mutation."""

from .models import ExecutionReceipt


class ExecutionAgent:
    def __init__(self, store):
        self.store = store

    def record(self, decision):
        self.store.verify_decision(decision)
        return tuple(ExecutionReceipt(i.intent_id,
                                      "RECORDED_NOT_EXECUTED" if self.store.record_intent(decision, i) else "ALREADY_RECORDED_NOT_EXECUTED")
                     for i in decision.approved)
