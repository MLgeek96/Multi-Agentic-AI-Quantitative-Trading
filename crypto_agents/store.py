"""SQLite audit records and persistent circuit breaker, in one trusted process."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from .models import RiskDecision, RiskState, canonical_json


class SQLiteStore:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), isolation_level=None)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS cycles (cycle_id TEXT PRIMARY KEY, account_key TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (cycle_id TEXT NOT NULL REFERENCES cycles(cycle_id), sequence INTEGER NOT NULL,
                stage TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(cycle_id, sequence));
            CREATE TABLE IF NOT EXISTS decisions (decision_id TEXT PRIMARY KEY, account_key TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS intents (account_key TEXT NOT NULL, intent_id TEXT NOT NULL,
                decision_id TEXT NOT NULL REFERENCES decisions(decision_id), payload TEXT NOT NULL, PRIMARY KEY(account_key, intent_id));
            CREATE TABLE IF NOT EXISTS states (account_key TEXT PRIMARY KEY, payload TEXT NOT NULL);
        """)
        for table in ("cycles", "events", "decisions", "intents"):
            for operation in ("UPDATE", "DELETE"):
                self.connection.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} BEFORE {operation} ON {table} "
                                        "BEGIN SELECT RAISE(ABORT, 'audit records are append-only'); END")

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

    def load_state(self, account):
        row = self.connection.execute("SELECT payload FROM states WHERE account_key=?", (account,)).fetchone()
        return RiskState(**json.loads(row[0])) if row else None

    def save_state(self, account, state):
        self.connection.execute("INSERT INTO states VALUES (?,?) ON CONFLICT(account_key) DO UPDATE SET payload=excluded.payload",
                                (account, canonical_json(state)))

    def save_decision(self, decision):
        self.connection.execute("INSERT INTO decisions VALUES (?,?,?)",
                                (decision.decision_id, decision.account_key, canonical_json(decision)))

    def verify_decision(self, decision):
        if not isinstance(decision, RiskDecision):
            raise ValueError("Execution accepts a persisted RiskDecision, not raw orders")
        row = self.connection.execute("SELECT account_key,payload FROM decisions WHERE decision_id=?", (decision.decision_id,)).fetchone()
        if row is None or row != (decision.account_key, canonical_json(decision)):
            raise ValueError("Risk decision must match the exact persisted approval")

    def record_intent(self, decision, intent):
        self.verify_decision(decision)
        if intent not in decision.approved:
            raise ValueError("intent is not approved")
        row = self.connection.execute("SELECT payload FROM intents WHERE account_key=? AND intent_id=?",
                                      (decision.account_key, intent.intent_id)).fetchone()
        payload = canonical_json(intent)
        if row:
            if row[0] != payload:
                raise ValueError("intent ID collision")
            return False
        self.connection.execute("INSERT INTO intents VALUES (?,?,?,?)",
                                (decision.account_key, intent.intent_id, decision.decision_id, payload))
        return True

    def save_cycle(self, cycle_id, account, report, events):
        self.connection.execute("INSERT INTO cycles VALUES (?,?,?)", (cycle_id, account, canonical_json(report)))
        self.connection.executemany("INSERT INTO events VALUES (?,?,?,?)",
                                    [(cycle_id, n, stage, canonical_json(payload)) for n, (stage, payload) in enumerate(events, 1)])

    def close(self):
        self.connection.close()
