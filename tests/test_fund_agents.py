from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import sys

import pandas as pd

from fund_agents.evidence import fingerprint
from fund_agents.__main__ import demo_pairs, load_config, load_pairs_prices, ROOT
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
        cls.as_of = "2025-03-10"
        cls.prices, cls.source = demo_pairs(cls.cfg, cls.as_of)

    def setUp(self):
        self.snapshot = FundSnapshot.initial(self.cfg, self.as_of)
        self.store = FundStore(":memory:")
        self.coordinator = FundCoordinator(self.cfg, self.store)

    def tearDown(self):
        self.store.close()

    def run_cycle(self, **kwargs):
        return self.coordinator.run(self.prices, self.snapshot, pairs_source_sha256=self.source, input_basis="SYNTHETIC_DEMO", **kwargs)

    def proposals(self, pair_gross=1_200_000., beta=1.):
        first = pair_gross / (1 + abs(beta))
        pair = TargetGroup("pairs", "V~MA", self.snapshot.as_of, self.snapshot.as_of,
                           (TargetLeg("V", first / 100., 100.), TargetLeg("MA", -beta * first / 100., 100.)),
                           "fixture", beta)
        return (PMProposal("pairs", "READY", (pair,), {}, fingerprint({})),)

    def test_pairs_only_cycle_tools_and_no_fills(self):
        report = self.run_cycle()
        self.assertEqual(report["pm_proposals"]["pairs"]["status"], "READY")
        self.assertEqual(set(report["pm_proposals"]), {"pairs"})
        self.assertNotIn("crypto", json.dumps(report).lower())
        self.assertEqual(set(self.store.state(self.cfg.account_key)), {"fund"})
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
        report = self.coordinator.run(prices, self.snapshot, pairs_source_sha256="missing", input_basis="SYNTHETIC_DEMO")
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
            for snapshot in (replace(self.snapshot, central_cash_usd=500_000., pairs_cash_usd=500_000.), self.snapshot):
                store = FundStore(path)
                try:
                    report = FundCoordinator(self.cfg, store).run(
                        self.prices, snapshot, pairs_source_sha256=self.source, input_basis="SYNTHETIC_DEMO")
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
            FundCoordinator(replace(self.cfg, mode="research"), self.store).run(self.prices, self.snapshot,
                                                                                  pairs_source_sha256=self.source, input_basis="SYNTHETIC_DEMO")
        self.run_cycle()
        earlier = replace(self.snapshot, as_of="2025-03-09")
        with self.assertRaises(ValueError):
            self.coordinator.run(self.prices, earlier, pairs_source_sha256=self.source, input_basis="SYNTHETIC_DEMO")

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

    def test_overlapping_pairs_count_gross_before_netting(self):
        proposals = self.proposals()
        pair = TargetGroup("pairs", "V~OTHER", self.as_of, self.as_of,
                           (TargetLeg("V", -6000., 100.), TargetLeg("OTHER", 6000., 100.)), "overlap", 1.)
        proposals = (replace(proposals[0], groups=proposals[0].groups + (pair,)),)
        cfg = replace(self.cfg, maximum_name_gross=.10)
        decision = FundRisk(cfg).review(proposals, self.snapshot)
        name_gross = sum(abs(l["units"] * l["price_usd"]) for g in decision["approved_groups"]
                         for l in g["legs"] if l["symbol"] == "V")
        self.assertLessEqual(name_gross, 500_000. + 1e-6)
        self.assertTrue(any("V gross" in reason for r in decision["reviews"] for reason in r["reasons"]))

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
        self.assertEqual(observed, [1, 1])
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
        cfg = replace(self.cfg, pairs_budget_usd=3_000_000., maximum_name_gross=.50,
                      maximum_fund_gross=0.80, soft_drawdown=0.10, soft_drawdown_scale=0.50)
        # Supplied cash gives NAV 4.2M, 16% below the 5M peak.
        throttled_snapshot = replace(self.snapshot, pairs_cash_usd=2_200_000.0, central_cash_usd=500_000.0)
        proposals = self.proposals(pair_gross=2_000_000.0)
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
                "observations": ["Verified the Pairs PM against risk limits"],
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

    def test_half_life_time_stop_is_frozen_at_confirmed_entry_session(self):
        snapshot = replace(self.snapshot, holdings=(Holding("pairs", "V~MA", "V", 10., 100., "2025-03-05"),
                                                    Holding("pairs", "V~MA", "MA", -10., 100., "2025-03-05")))
        pm = PairsPM(self.cfg)
        real = pm.engine.update_pair_state_and_forecast
        def entry_half_life(*args, **kwargs):
            result = real(*args, **kwargs)
            # Current half-life grows, but cannot extend the entry time stop.
            result.update(target_position=1, ou_theta=.2,
                          ou_half_life=1. if str(args[0].index[-1].date()) == "2025-03-05" else 90.)
            return result
        with patch.object(pm.engine, "update_pair_state_and_forecast", side_effect=entry_half_life):
            proposal = pm.propose(self.prices, snapshot, source_sha256=self.source)
        self.assertEqual(proposal.status, "READY")
        self.assertEqual(proposal.diagnostics["pairs"][0]["holding_limit_sessions"], 3)
        self.assertEqual(proposal.groups[0].gross_usd, 0.)

    def test_unqualified_formation_blocks_new_entry_without_fallback(self):
        pm = PairsPM(replace(self.cfg, require_formation_qualification=True))
        with patch("fund_agents.pairs.PairSelector.evaluate_pair", return_value={"qualified": False}):
            proposal = pm.propose(self.prices, self.snapshot, source_sha256=self.source)
        self.assertEqual(proposal.status, "READY")
        self.assertEqual(proposal.groups[0].gross_usd, 0.)
        self.assertIn("formation", proposal.groups[0].reason)

    def test_source_drift_holds_fund_without_intents(self):
        with patch("fund_agents.strategy.hashlib.sha256") as sha:
            sha.return_value.hexdigest.return_value = "unexpected-source"
            report = self.run_cycle()
        self.assertEqual(report["status"], "INPUT_HOLD")
        self.assertEqual(report["execution_receipts"], [])
        self.assertIn("differs", report["pm_proposals"]["pairs"]["diagnostics"]["error"])
        self.assertNotIn("throttled_gross_usd", report["committee_chair"]["input_facts"]["metrics"])

    def test_duplicate_raw_price_header_is_not_silently_renamed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "prices.csv"
            path.write_text("Date,V,V\n2025-03-10,100,200\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique"):
                load_pairs_prices(path)

    def test_legacy_pm_and_config_are_rejected_and_default_cash_reconciles(self):
        cfg = load_config(ROOT / "config/fund_agents.demo.json")
        self.assertEqual(cfg.initial_nav_usd, 5_000_000.)
        self.assertEqual(cfg.central_cash_usd, 2_000_000.)
        with self.assertRaises(ValueError):
            Holding("crypto", "spot:BTCUSDT", "BTCUSDT", 1., 100.)
        with self.assertRaises(ValueError):
            self.run_cycle(pm_responses={"crypto": {}})
        self.store.save_state(self.cfg.account_key, {"crypto": {}})
        with self.assertRaisesRegex(ValueError, "legacy"):
            self.run_cycle()

    def test_fund_runs_without_importing_crypto_packages(self):
        result = subprocess.run([sys.executable, "-c",
            "import sys; from fund_agents.__main__ import FundCoordinator; "
            "assert not any(n.split('.')[0] in ('crypto_agents','crypto_quant') for n in sys.modules)"],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

