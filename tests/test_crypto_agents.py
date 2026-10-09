from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from crypto_agents.config import AgentConfig
from crypto_agents.data import demo_snapshot, load_local_snapshot
from crypto_agents.execution import ExecutionAgent
from crypto_agents.meta import MetaAgent
from crypto_agents.models import (BlendedSignal, ExpertSignal, Holding, OrderIntent, PortfolioSnapshot,
                                 RegimeEstimate, fingerprint)
from crypto_agents.regime import RegimeAgent
from crypto_agents.research import ResearchAgent
from crypto_agents.risk import RiskAgent
from crypto_agents.signal import blend
from crypto_agents.store import SQLiteStore
from crypto_quant.daily_portfolio import compute_daily_decision
from test_daily_portfolio import FakeClient


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.cfg = AgentConfig(mode="demo", account_key="test")
        self.market, _ = demo_snapshot(("BTCUSDT", "ETHUSDT"))
        self.portfolio = PortfolioSnapshot(self.market.as_of, 100_000.)
        self.store = SQLiteStore(":memory:")
        self.meta = MetaAgent(self.cfg, self.store)

    def tearDown(self):
        self.store.close()

    def test_agent_baseline_preserves_existing_target_weights(self):
        import pandas as pd
        _, expected = compute_daily_decision(self.market.closes(), pd.Timestamp(self.market.as_of, tz="UTC"), self.meta.daily)
        report = self.meta.run(self.market, self.portfolio)
        for symbol in expected:
            self.assertAlmostEqual(report["proposed_weights"][symbol], expected[symbol], places=12)
        self.assertEqual(report["portfolio_before"], report["portfolio_after"])
        self.assertTrue(report["execution_receipts"])
        self.assertTrue(all(r["filled_units"] == 0 for r in report["execution_receipts"]))

    def test_idempotent_approved_intents_and_account_isolation(self):
        first = self.meta.run(self.market, self.portfolio)
        second = self.meta.run(self.market, self.portfolio)
        self.assertEqual([r["intent_id"] for r in first["execution_receipts"]], [r["intent_id"] for r in second["execution_receipts"]])
        self.assertTrue(all(r["status"] == "ALREADY_RECORDED_NOT_EXECUTED" for r in second["execution_receipts"]))
        other = MetaAgent(replace(self.cfg, account_key="other"), self.store).run(self.market, self.portfolio)
        self.assertTrue(all(r["status"] == "RECORDED_NOT_EXECUTED" for r in other["execution_receipts"]))

    def test_quality_veto(self):
        flagged, _ = demo_snapshot(("BTCUSDT", "ETHUSDT"), scenario="flagged")
        result = self.meta.run(flagged, self.portfolio)
        self.assertEqual(result["status"], "DATA_QUALITY_VETO")
        self.assertEqual(result["execution_receipts"], [])

    def test_risk_reduces_name_exposure(self):
        result = MetaAgent(replace(self.cfg, maximum_asset_weight=.1), self.store).run(self.market, self.portfolio)
        self.assertTrue(any(r["outcome"] == "REDUCE" for r in result["risk_decision"]["reviews"]))
        for review in result["risk_decision"]["reviews"]:
            if review["approved"]:
                approved = review["approved"]
                self.assertLessEqual(approved["units"] * approved["reference_price"], 10_000.000001)

    def test_liquidity_limit_uses_only_prior_bars(self):
        datasets = tuple(replace(d, bars=tuple(replace(b, quote_volume=1000.) for b in d.bars[:-1]) + (replace(d.bars[-1], quote_volume=1e15),)) for d in self.market.datasets)
        market = replace(self.market, datasets=datasets)
        result = self.meta.run(market, self.portfolio)
        for review in result["risk_decision"]["reviews"]:
            if review["approved"]:
                approved = review["approved"]
                self.assertLessEqual(approved["units"] * approved["reference_price"], 1.000001)

    def test_breaker_survives_restart_and_no_auto_reset(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.sqlite"
            store = SQLiteStore(path)
            first = MetaAgent(self.cfg, store).run(self.market, replace(self.portfolio, cash_usdt=60_000.))
            store.close()
            store = SQLiteStore(path)
            try:
                second = MetaAgent(self.cfg, store).run(self.market, self.portfolio)
            finally:
                store.close()
        self.assertTrue(first["risk_decision"]["state"]["breaker_latched"])
        self.assertTrue(second["risk_decision"]["state"]["breaker_latched"])
        self.assertFalse(any(r["approved"] and r["approved"]["side"] == "BUY" for r in second["risk_decision"]["reviews"]))

    def test_stop_generates_request_without_a_fill(self):
        price = self.market.dataset("BTCUSDT").bars[-1].close
        portfolio = replace(self.portfolio, cash_usdt=80_000., holdings=(Holding("BTCUSDT", 50., price / .8),))
        result = self.meta.run(self.market, portfolio)
        self.assertTrue(any("stop-loss" in a for a in result["risk_decision"]["alerts"]))
        self.assertEqual(result["portfolio_before"], result["portfolio_after"])

    def test_execution_rejects_unpersisted_and_changed_approval(self):
        intent = OrderIntent.create(self.market.as_of, "BTCUSDT", "BUY", 1, self.market.dataset("BTCUSDT").bars[-1].close, "test", "test")
        decision = RiskAgent(self.cfg).review((intent,), self.market, self.portfolio, None, "one")
        execution = ExecutionAgent(self.store)
        with self.assertRaises(ValueError):
            execution.record(decision)
        self.store.save_decision(decision)
        with self.assertRaises(ValueError):
            execution.record(replace(decision, account_key="altered"))
        with self.assertRaises(ValueError):
            execution.record((intent,))

    def test_append_only_events(self):
        self.meta.run(self.market, self.portfolio)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute("DELETE FROM events")

    def test_transaction_rolls_back_on_failure(self):
        def broken(*args, **kwargs):
            raise RuntimeError("injected failure")
        self.meta.execution.record = broken
        with self.assertRaises(RuntimeError):
            self.meta.run(self.market, self.portfolio)
        self.assertEqual(self.store.connection.execute("SELECT count(*) FROM decisions").fetchone()[0], 0)
        self.assertIsNone(self.store.load_state(self.cfg.account_key))

    def test_unknown_expert_is_hold_and_not_sell(self):
        regime = RegimeEstimate(self.market.as_of, (("trend", .5), ("mean_revert", .5), ("crisis", 0.)), "test")
        signals = tuple(ExpertSignal("BTCUSDT", name, value, .5, "test") for name, value in (("trend", 1.), ("mean_revert", None), ("crisis", 0.)))
        mixed = blend(signals, regime)
        self.assertIsNone(mixed[0].exposure)
        orders, weights = self.meta.position.propose(mixed, self.market, self.portfolio)
        self.assertEqual(orders, ())
        self.assertIsNone(weights)

    def test_hmm_training_precedes_inference(self):
        estimate = RegimeAgent(replace(self.cfg, strategy_mode="hmm_experts", hmm_training_days=60)).estimate(self.market)
        self.assertLess(estimate.trained_through, self.market.as_of)
        self.assertAlmostEqual(sum(dict(estimate.routing).values()), 1.)
        self.assertEqual(dict(estimate.routing)["crisis"], 0.)
        self.assertTrue(estimate.model_sha256)

    def test_research_mode_rejects_synthetic(self):
        with self.assertRaises(ValueError):
            MetaAgent(replace(self.cfg, mode="research"), self.store).run(self.market, self.portfolio)

    def test_llm_output_cannot_change_quantitative_decisions(self):
        first = self.meta.run(self.market, self.portfolio)
        reply = json.dumps({"model": "test-fixture", "input_sha256": first["llm_research"]["input_sha256"],
                            "output": {"summary": "Research only", "observations": [], "risk_flags": [],
                                       "suggested_research": ["Evaluate later"], "metric_claims": [{"name": "filled_orders", "value": 0}]}})
        second = self.meta.run(self.market, self.portfolio, llm_response=reply)
        self.assertEqual(second["llm_research"]["status"], "STRUCTURED_CLAIMS_VALIDATED")
        self.assertEqual(second["proposed_weights"], first["proposed_weights"])
        payload = json.loads(reply)
        payload["output"]["orders"] = [{"side": "BUY"}]
        third = self.meta.run(self.market, self.portfolio, llm_response=json.dumps(payload))
        self.assertEqual(third["llm_research"]["status"], "REJECTED")
        self.assertEqual(third["proposed_weights"], first["proposed_weights"])

    def test_llm_claim_and_digest_mismatch_rejected(self):
        facts = {"metrics": {"return": 0.1}}
        base = {"model": "fixture", "input_sha256": fingerprint(facts), "output": {"summary": "text", "observations": [],
                "risk_flags": [], "suggested_research": [], "metric_claims": [{"name": "return", "value": 1.0}]}}
        self.assertEqual(ResearchAgent().review(facts, json.dumps(base))["status"], "REJECTED")
        base["input_sha256"] = "wrong"
        self.assertEqual(ResearchAgent().review(facts, json.dumps(base))["status"], "REJECTED")

    def test_local_snapshot_is_causal_and_detects_byte_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            client = FakeClient()
            for symbol in ("BTCUSDT", "ETHUSDT"):
                client.fetch_klines(symbol).to_csv(directory / f"{symbol}_1d.csv", index=False)
            first, _ = load_local_snapshot(directory, ("BTCUSDT", "ETHUSDT"), "2024-10-01")
            path = directory / "BTCUSDT_1d.csv"
            import pandas as pd
            table = pd.read_csv(path)
            table.loc[len(table) - 1, ["open", "high", "low", "close"]] *= 2
            table.to_csv(path, index=False)
            second, _ = load_local_snapshot(directory, ("BTCUSDT", "ETHUSDT"), "2024-10-01")
            pd.testing.assert_frame_equal(first.closes(), second.closes())
            self.assertNotEqual(first.datasets[0].source_sha256, second.datasets[0].source_sha256)
            stale, audit = load_local_snapshot(directory, ("BTCUSDT", "ETHUSDT"), "2024-10-05")
            self.assertFalse(stale.quality_pass)
            self.assertEqual(audit["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
