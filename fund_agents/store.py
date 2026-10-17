"""Atomic append-only fund decisions, grouped intentions and PM tool records."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from .evidence import canonical_json, fingerprint


class FundStore:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), isolation_level=None)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS fund_cycles (cycle_id TEXT PRIMARY KEY, account_key TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS fund_decisions (decision_id TEXT PRIMARY KEY, account_key TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS fund_intents (intent_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL REFERENCES fund_decisions(decision_id), payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS fund_states (account_key TEXT PRIMARY KEY, payload TEXT NOT NULL);
        """)
        for table in ("fund_cycles", "fund_decisions", "fund_intents"):
            for action in ("UPDATE", "DELETE"):
                self.connection.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'fund audit is append-only'); END")

    @contextmanager
    def transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def state(self, account):
        row = self.connection.execute("SELECT payload FROM fund_states WHERE account_key=?", (account,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_state(self, account, state):
        self.connection.execute("INSERT INTO fund_states VALUES (?,?) ON CONFLICT(account_key) DO UPDATE SET payload=excluded.payload", (account, canonical_json(state)))

    def save_decision(self, decision):
        row = self.connection.execute("SELECT payload FROM fund_decisions WHERE decision_id=?", (decision["decision_id"],)).fetchone()
        if row:
            if row[0] != canonical_json(decision):
                raise ValueError("fund decision ID collision")
        else:
            self.connection.execute("INSERT INTO fund_decisions VALUES (?,?,?)", (decision["decision_id"], decision["account_key"], canonical_json(decision)))

    def record(self, decision, snapshot):
        row = self.connection.execute("SELECT payload FROM fund_decisions WHERE decision_id=?", (decision["decision_id"],)).fetchone()
        if row is None or row[0] != canonical_json(decision):
            raise ValueError("Execution needs the exact persisted fund risk approval")
        # A changed dict with the same ID also fails the content hash check.
        payload = {k: v for k, v in decision.items() if k != "decision_id"}
        if fingerprint(payload) != decision["decision_id"]:
            raise ValueError("Risk decision contents do not match their identity")
        if fingerprint(snapshot) != decision["snapshot_sha256"]:
            raise ValueError("Execution snapshot differs from the one Risk reviewed")
        receipts = []
        for group in decision["approved_groups"]:
            if not group["actionable"]:
                continue
            legs = []
            for leg in group["legs"]:
                current = snapshot.units(group["pm"], group["group"], leg["symbol"])
                delta = leg["units"] - current
                legs.append(dict(leg, current_units=current, delta_units=delta,
                                 side="BUY" if delta > 0 else "SELL" if delta < 0 else "UNCHANGED"))
            if not any(abs(l["delta_units"] * l["price_usd"]) > 1e-6 for l in legs):
                continue
            intent = {"account_key": decision["account_key"], "as_of": snapshot.as_of,
                      "pm": group["pm"], "group": group["group"], "legs": legs,
                      "hedge_beta": group["hedge_beta"], "execution_condition": "LINKED_GROUP_RECORD_ONLY",
                      "timing": "After completed signal session; a future fill adapter must use the next eligible session"}
            intent_id = fingerprint(intent)
            existing = self.connection.execute("SELECT payload FROM fund_intents WHERE intent_id=?", (intent_id,)).fetchone()
            if existing and existing[0] != canonical_json(intent):
                raise ValueError("fund intent ID collision")
            if not existing:
                self.connection.execute("INSERT INTO fund_intents VALUES (?,?,?)", (intent_id, decision["decision_id"], canonical_json(intent)))
            receipts.append({"intent_id": intent_id, "pm": group["pm"], "group": group["group"],
                             "status": "ALREADY_RECORDED_NOT_EXECUTED" if existing else "RECORDED_NOT_EXECUTED",
                             "filled_units": 0, "intent": intent})
        return receipts

    def save_cycle(self, cycle_id, account, report):
        self.connection.execute("INSERT INTO fund_cycles VALUES (?,?,?)", (cycle_id, account, canonical_json(report)))

    def close(self):
        self.connection.close()
