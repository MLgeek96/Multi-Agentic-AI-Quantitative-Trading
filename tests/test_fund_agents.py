from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from crypto_agents.config import ROOT
from crypto_agents.data import demo_snapshot
from crypto_agents.models import fingerprint
from fund_agents.__main__ import demo_pairs
from fund_agents.coordinator import FundCoordinator
from fund_agents.models import FundConfig, FundSnapshot, Holding, PMProposal, TargetGroup, TargetLeg
from fund_agents.pairs import PairsPM
from fund_agents.representative import PMRepresentative
from fund_agents.risk import FundRisk
from fund_agents.store import FundStore


class FundAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = FundConfig(require_formation_qualification=False)
        cls.market, _ = demo_snapshot(("BTCUSDT", "ETHUSDT"))
        cls.prices, cls.source = demo_pairs(cls.cfg, cls.market.as_of)

    def setUp(self):
        self.snapshot = FundSnapshot.initial(self.cfg, self.market.as_of)
        self.store = FundStore(":memory:")
        self.coordinator = FundCoordinator(self.cfg, self.store, ROOT / self.cfg.crypto_config_path)

    def tearDown(self):
        self.store.close()

    def run_cycle(self, **kwargs):
        return self.coordinator.run(self.market, self.prices, self.snapshot, pairs_source_sha256=self.source, **kwargs)

    def proposals(self, pair_gross=1_200_000., crypto_gross=0., beta=1.):
        first = pair_gross / (1 + abs(beta))
        pair = TargetGroup("pairs", "V~MA", self.snapshot.as_of, self.snapshot.as_of,
                           (TargetLeg("V", first / 100., 100.), TargetLeg("MA", -beta * first / 100., 100.)),
                           "fixture", beta)
        crypto = TargetGroup("crypto", "spot:BTCUSDT", self.snapshot.as_of, self.snapshot.as_of,
                             (TargetLeg("BTCUSDT", crypto_gross / 100., 100.),), "fixture")
        return (PMProposal("crypto", "READY", (crypto,), {}, fingerprint({})),
                PMProposal("pairs", "READY", (pair,), {}, fingerprint({})))

    def test_full_two_pm_cycle_tools_and_no_fills(self):
        report = self.run_cycle()
        self.assertEqual(report["pm_proposals"]["pairs"]["status"], "READY")
        self.assertEqual(report["pm_proposals"]["crypto"]["status"], "READY")
        self.assertEqual(report["portfolio_before"], report["portfolio_after"])
        self.assertEqual(report["fund_risk"]["metrics"]["marked_nav_usd"], 5_000_000.)
        for memo in report["pm_representatives"].values():
            self.assertEqual(len(memo["tool_calls"]), 3)
            self.assertEqual(memo["status"], "NOT_REQUESTED")
        self.assertTrue(report["execution_receipts"])
        self.assertTrue(all(r["filled_units"] == 0 for r in report["execution_receipts"]))
        self.assertTrue(any(r["pm"] == "pairs" and len(r["intent"]["legs"]) == 2 for r in report["execution_receipts"]))

    def test_repeat_does_not_duplicate_group_intents(self):
        first, second = self.run_cycle(), self.run_cycle()
        self.assertEqual([r["intent_id"] for r in first["execution_receipts"]], [r["intent_id"] for r in second["execution_receipts"]])
        self.assertTrue(all(r["status"] == "ALREADY_RECORDED_NOT_EXECUTED" for r in second["execution_receipts"]))
        self.assertEqual(self.store.connection.execute("SELECT count(*) FROM fund_intents").fetchone()[0], len(first["execution_receipts"]))

    def test_pair_resizing_keeps_both_hedge_legs(self):
        cfg = replace(self.cfg, maximum_name_gross=.05)
        decision = FundRisk(cfg).review(self.proposals(beta=2.), self.snapshot)
        approved = next(g for g in decision["approved_groups"] if g["pm"] == "pairs")
        first, second = [l["units"] * l["price_usd"] for l in approved["legs"]]
        self.assertAlmostEqual(second / first, -2.)
        self.assertLessEqual(abs(second), .05 * 5_000_000. + 1e-6)
        self.assertTrue(any(r["outcome"] == "REDUCE" for r in decision["reviews"]))

    def test_negative_beta_preserves_signed_hedge(self):
        decision = FundRisk(self.cfg).review(self.proposals(beta=-.5), self.snapshot)
        group = next(g for g in decision["approved_groups"] if g["pm"] == "pairs")
        self.assertGreater(group["legs"][1]["units"], 0)
        first, second = [l["units"] * l["price_usd"] for l in group["legs"]]
        self.assertAlmostEqual(second / first, .5)

    def test_future_prices_cannot_change_a_prior_signal(self):
        pm = PairsPM(self.cfg)
        before = pm.propose(self.prices, self.snapshot, source_sha256=self.source)
        later = pd.DataFrame({"V": [1e9], "MA": [1.]}, index=[pd.Timestamp(self.snapshot.as_of) + pd.Timedelta(days=1)])
        after = pm.propose(pd.concat([self.prices, later]), self.snapshot, source_sha256="new-future-source")
        self.assertEqual(before.groups, after.groups)
        self.assertEqual(before.diagnostics["pairs"], after.diagnostics["pairs"])

    def test_missing_equity_session_holds_whole_fund(self):
        prices = self.prices.drop(self.prices.index[-1])
        report = self.coordinator.run(self.market, prices, self.snapshot, pairs_source_sha256="missing")
        self.assertEqual(report["status"], "INPUT_HOLD")
        self.assertEqual(report["execution_receipts"], [])
        self.assertIn("missing", report["pm_proposals"]["pairs"]["diagnostics"]["error"])

    def test_closed_equity_market_retains_actual_positions_without_a_new_order(self):
        as_of = "2025-03-15"  # Saturday: latest eligible US session is Friday.
        cfg = replace(self.cfg)
        prices, source = demo_pairs(cfg, "2025-03-14")
        snapshot = replace(self.snapshot, as_of=as_of,
                           holdings=(Holding("pairs", "V~MA", "V", 10., 100., "2025-03-13"),
                                     Holding("pairs", "V~MA", "MA", -9., 100., "2025-03-13")))
        proposal = PairsPM(cfg).propose(prices, snapshot, source_sha256=source)
        self.assertEqual(proposal.status, "READY")
        self.assertFalse(proposal.groups[0].actionable)
        self.assertEqual(proposal.groups[0].signal_session, "2025-03-14")
        self.assertEqual([l.units for l in proposal.groups[0].legs], [10., -9.])

    def test_extreme_divergence_blocks_new_entry(self):
        pm = PairsPM(self.cfg)
        real = pm.engine.update_pair_state_and_forecast
        def extreme(*args, **kwargs):
            result = real(*args, **kwargs)
            result.update(z_score=8., target_position=-1)
            return result
        with patch.object(pm.engine, "update_pair_state_and_forecast", side_effect=extreme):
            result = pm.propose(self.prices, self.snapshot, source_sha256=self.source)
        self.assertEqual(result.status, "READY")
        self.assertEqual(result.groups[0].gross_usd, 0.)

    def test_invalid_ou_blocks_new_entry_and_serializes_as_null(self):
        pm = PairsPM(self.cfg)
        real = pm.engine.update_pair_state_and_forecast
        def invalid(*args, **kwargs):
            result = real(*args, **kwargs)
            result.update(ou_theta=0., ou_half_life=float("inf"), target_position=-1)
            return result
        with patch.object(pm.engine, "update_pair_state_and_forecast", side_effect=invalid):
            result = pm.propose(self.prices, self.snapshot, source_sha256=self.source)
        self.assertEqual(result.status, "READY")
        self.assertEqual(result.groups[0].gross_usd, 0.)
        self.assertIsNone(result.diagnostics["pairs"][0]["ou_half_life"])
        self.assertEqual(result.diagnostics["pairs"][0]["forecasts"], [])

    def test_execution_requires_persisted_risk_and_the_same_snapshot(self):
        decision = FundRisk(self.cfg).review(self.proposals(), self.snapshot)
        with self.assertRaises(ValueError):
            self.store.record(decision, self.snapshot)
        self.store.save_decision(decision)
        modified = dict(decision, status="fake approval")
        with self.assertRaises(ValueError):
            self.store.record(modified, self.snapshot)
        with self.assertRaises(ValueError):
            self.store.record(decision, replace(self.snapshot, pairs_cash_usd=1.))
        self.assertTrue(self.store.record(decision, self.snapshot))

    def test_breaker_is_latched_across_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fund.sqlite"
            for snapshot in (replace(self.snapshot, crypto_cash_usd=500_000., pairs_cash_usd=500_000.), self.snapshot):
                store = FundStore(path)
                try:
                    report = FundCoordinator(self.cfg, store, ROOT / self.cfg.crypto_config_path).run(
                        self.market, self.prices, snapshot, pairs_source_sha256=self.source)
                finally:
                    store.close()
                self.assertTrue(report["fund_risk"]["state"]["breaker_latched"])
                self.assertFalse(any(l["units"] for g in report["fund_risk"]["approved_groups"] if g["actionable"] for l in g["legs"]))

    def test_llm_memo_cannot_change_the_quantitative_groups(self):
        before = self.run_cycle()
        memo = before["pm_representatives"]["pairs"]
        reply = {"model": "test-model", "input_sha256": memo["input_sha256"],
                 "output": {"summary": "Pair diagnosis", "observations": [], "risk_flags": [], "suggested_research": [],
                            "metric_claims": [{"name": "filled_orders", "value": 0}]}}
        envelope = {"pairs": {"tool_names": [c["tool"] for c in memo["tool_calls"]], "reply": reply}}
        after = self.run_cycle(pm_responses=envelope)
        self.assertEqual(after["pm_representatives"]["pairs"]["status"], "STRUCTURED_CLAIMS_VALIDATED")
        self.assertEqual(before["fund_risk"]["approved_groups"], after["fund_risk"]["approved_groups"])
        reply["output"]["metric_claims"][0]["value"] = 99
        rejected = self.run_cycle(pm_responses=envelope)
        self.assertEqual(rejected["pm_representatives"]["pairs"]["status"], "REJECTED")
        self.assertEqual(before["fund_risk"]["approved_groups"], rejected["fund_risk"]["approved_groups"])

    def test_ai_cannot_select_an_execution_tool(self):
        report = self.run_cycle(pm_responses={"pairs": {"tool_names": ["place_order"], "reply": None}})
        self.assertEqual(report["pm_representatives"]["pairs"]["status"], "REJECTED")
        self.assertTrue(report["execution_receipts"])
        self.assertEqual(report["portfolio_before"], report["portfolio_after"])

    def test_atomic_rollback_and_append_only_audit(self):
        with patch.object(self.store, "record", side_effect=RuntimeError("injected execution failure")):
            with self.assertRaises(RuntimeError):
                self.run_cycle()
        self.assertEqual(self.store.connection.execute("SELECT count(*) FROM fund_decisions").fetchone()[0], 0)
        self.assertIsNone(self.store.state(self.cfg.account_key))
        self.run_cycle()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute("DELETE FROM fund_decisions")

    def test_research_rejects_synthetic_and_replay_cannot_go_backwards(self):
        with self.assertRaises(ValueError):
            FundCoordinator(replace(self.cfg, mode="research", crypto_config_path="config/agents.research.json"),
                            self.store, ROOT / "config/agents.research.json").run(self.market, self.prices, self.snapshot,
                                                                                  pairs_source_sha256=self.source)
        self.run_cycle()
        earlier = replace(self.snapshot, as_of="2025-03-09")
        with self.assertRaises(ValueError):
            self.coordinator.run(replace(self.market, as_of=earlier.as_of), self.prices, earlier, pairs_source_sha256=self.source)

    def test_forecast_z_uses_the_spread_once(self):
        result = PairsPM(self.cfg).propose(self.prices, self.snapshot, source_sha256=self.source)
        update = result.diagnostics["pairs"][0]
        self.assertTrue(update["forecasts"])
        for forecast in update["forecasts"]:
            self.assertAlmostEqual(forecast["expected_z"], forecast["expected_spread"] / update["spread_std"])

    def test_pair_targets_reject_a_broken_hedge(self):
        with self.assertRaises(ValueError):
            TargetGroup("pairs", "V~MA", self.snapshot.as_of, self.snapshot.as_of,
                        (TargetLeg("V", 10., 100.), TargetLeg("MA", -10., 100.)), "broken", hedge_beta=2.)

    def test_overlapping_sleeves_count_gross_before_netting(self):
        proposals = self.proposals(pair_gross=1_200_000., crypto_gross=1_200_000.)
        pair = replace(proposals[1].groups[0], legs=(TargetLeg("BTCUSDT", -6000., 100.), TargetLeg("MA", 6000., 100.)))
        proposals = (proposals[0], replace(proposals[1], groups=(pair,)))
        cfg = replace(self.cfg, maximum_name_gross=.10)
        decision = FundRisk(cfg).review(proposals, self.snapshot)
        btc_gross = sum(abs(l["units"] * l["price_usd"]) for g in decision["approved_groups"] for l in g["legs"] if l["symbol"] == "BTCUSDT")
        self.assertLessEqual(btc_gross, 500_000. + 1e-6)
        self.assertTrue(any("BTCUSDT gross" in reason for r in decision["reviews"] for reason in r["reasons"]))

    def test_time_stop_uses_confirmed_pair_position(self):
        snapshot = replace(self.snapshot, holdings=(Holding("pairs", "V~MA", "V", 10., 100., "2025-03-07"),
                                                    Holding("pairs", "V~MA", "MA", -10., 100., "2025-03-07")))
        pm = PairsPM(replace(self.cfg, max_holding_sessions=1))
        real = pm.engine.update_pair_state_and_forecast
        observed = []
        def holding(*args, **kwargs):
            observed.append(kwargs["current_position"])
            result = real(*args, **kwargs)
            result["target_position"] = 1
            return result
        with patch.object(pm.engine, "update_pair_state_and_forecast", side_effect=holding):
            proposal = pm.propose(self.prices, snapshot, source_sha256=self.source)
        self.assertEqual(observed, [1])
        self.assertEqual(proposal.groups[0].gross_usd, 0.)
        self.assertIn("Maximum holding", proposal.groups[0].reason)

    def test_pair_adapter_retains_negative_beta_in_both_targets(self):
        pm = PairsPM(self.cfg)
        real = pm.engine.update_pair_state_and_forecast
        def negative(*args, **kwargs):
            result = real(*args, **kwargs)
            result.update(beta_kalman=-.5, z_score=-2., target_position=1)
            return result
        with patch.object(pm.engine, "update_pair_state_and_forecast", side_effect=negative):
            proposal = pm.propose(self.prices, self.snapshot, source_sha256=self.source)
        first, second = proposal.groups[0].legs
        self.assertGreater(first.units, 0)
        self.assertGreater(second.units, 0)
        self.assertAlmostEqual(second.units * second.price_usd / (first.units * first.price_usd), .5)

    def test_non_usd_pair_requires_a_dated_explicit_fx_quote(self):
        cfg = replace(self.cfg, pairs=(replace(self.cfg.pairs[0], currency="EUR"),))
        without_fx = PairsPM(cfg).propose(self.prices, self.snapshot, source_sha256=self.source)
        self.assertEqual(without_fx.status, "INPUT_HOLD")
        snapshot = replace(self.snapshot, fx_to_usd=(("USD", 1.), ("EUR", 1.1)), fx_as_of=self.snapshot.as_of)
        with_fx = PairsPM(cfg).propose(self.prices, snapshot, source_sha256=self.source)
        self.assertEqual(with_fx.status, "READY")
        self.assertAlmostEqual(with_fx.groups[0].gross_usd, self.cfg.pairs_budget_usd * self.cfg.pairs_gross_fraction)

    def test_invalid_ai_tool_arguments_cannot_undo_a_saved_risk_verdict(self):
        before = self.run_cycle()
        after = self.run_cycle(pm_responses={"pairs": {"tool_names": ["inspect_positions"], "reply": {"order": "BUY"}}})
        self.assertEqual(after["pm_representatives"]["pairs"]["status"], "REJECTED")
        self.assertEqual(before["fund_risk"]["approved_groups"], after["fund_risk"]["approved_groups"])

    def test_soft_drawdown_throttle_scales_exposure_and_records_phantom_book(self) -> None:
        cfg = replace(self.cfg, maximum_fund_gross=0.80, soft_drawdown=0.10, soft_drawdown_scale=0.50)
        # Drop NAV from 5.0M peak to 4.2M (16% drawdown: above 10% soft_drawdown, below 25% maximum_drawdown)
        throttled_snapshot = replace(self.snapshot, crypto_cash_usd=1_100_000.0, pairs_cash_usd=1_100_000.0)
        proposals = self.proposals(pair_gross=1_000_000.0, crypto_gross=1_000_000.0)
        decision = FundRisk(cfg).review(proposals, throttled_snapshot)
        self.assertEqual(decision["status"], "REVIEWED")
        self.assertFalse(decision["state"]["breaker_latched"])
        self.assertIn("SOFT_DRAWDOWN_THROTTLE", decision["alerts"])
        phantom = decision["phantom_book"]
        self.assertTrue(phantom["soft_throttle_active"])
        self.assertAlmostEqual(phantom["proposed_gross_usd"], 2_000_000.0)
        # Effective fund gross cap is 0.80 * 0.50 * 4_200_000 = 1_680_000 USD
        self.assertAlmostEqual(phantom["approved_gross_usd"], 1_680_000.0)
        self.assertAlmostEqual(phantom["throttled_gross_usd"], 320_000.0)

    def test_committee_chair_agent_validates_cross_sleeve_and_phantom_claims(self) -> None:
        before = self.run_cycle()
        chair = before["committee_chair"]
        self.assertEqual(len(chair["tool_calls"]), 3)
        self.assertEqual(chair["status"], "NOT_REQUESTED")
        throttled = before["fund_risk"]["phantom_book"]["throttled_gross_usd"]
        reply = {
            "model": "test-chair-model",
            "input_sha256": chair["input_sha256"],
            "output": {
                "summary": "Committee Chair cross-sleeve synthesis",
                "observations": ["Verified both PM sleeves against risk limits"],
                "risk_flags": [],
                "suggested_research": [],
                "metric_claims": [{"name": "throttled_gross_usd", "value": throttled}],
            },
        }
        envelope = {"chair": {"tool_names": [c["tool"] for c in chair["tool_calls"]], "reply": reply}}
        validated = self.run_cycle(pm_responses=envelope)
        self.assertEqual(validated["committee_chair"]["status"], "STRUCTURED_CLAIMS_VALIDATED")
        reply["output"]["metric_claims"][0]["value"] = throttled + 500_000.0
        rejected = self.run_cycle(pm_responses=envelope)
        self.assertEqual(rejected["committee_chair"]["status"], "REJECTED")


if __name__ == "__main__":
    unittest.main()

