from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal


PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
STRATEGY_DIRECTORY = PROJECT_DIRECTORY / "user_data" / "strategies"
sys.path.insert(0, str(STRATEGY_DIRECTORY))

from regime_hmm import (
    FEATURE_NAMES,
    apply_defensive_router,
    build_regime_features,
    causal_filter,
)


class RegimeHMMTests(unittest.TestCase):
    @staticmethod
    def _candles(rows: int = 500) -> pd.DataFrame:
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0001, 0.008, rows)
        close = 20_000 * np.exp(np.cumsum(returns))
        return pd.DataFrame(
            {
                "open": close * (1 + rng.normal(0, 0.001, rows)),
                "high": close * 1.004,
                "low": close * 0.996,
                "close": close,
                "volume": rng.lognormal(8, 0.5, rows),
            },
            index=pd.date_range("2024-01-01", periods=rows, freq="h", tz="UTC"),
        )

    def test_features_do_not_change_when_future_candles_change(self) -> None:
        candles = self._candles()
        cutoff = 350
        baseline = build_regime_features(candles)

        changed = candles.copy()
        changed.iloc[cutoff:, changed.columns.get_loc("close")] *= 1.8
        changed.iloc[cutoff:, changed.columns.get_loc("volume")] *= 5
        changed_features = build_regime_features(changed)

        assert_frame_equal(
            baseline.iloc[:cutoff],
            changed_features.iloc[:cutoff],
            check_exact=True,
        )

    def test_forward_filter_does_not_change_past_probabilities(self) -> None:
        parameters = {
            "scaler_mean": [0.0] * len(FEATURE_NAMES),
            "scaler_scale": [1.0] * len(FEATURE_NAMES),
            "startprob": [0.6, 0.3, 0.1],
            "transmat": [
                [0.90, 0.08, 0.02],
                [0.08, 0.88, 0.04],
                [0.03, 0.07, 0.90],
            ],
            "means": [
                [1.0] * len(FEATURE_NAMES),
                [0.0] * len(FEATURE_NAMES),
                [-1.0] * len(FEATURE_NAMES),
            ],
            "variances": [[1.0] * len(FEATURE_NAMES)] * 3,
            "state_labels": {"0": "trend", "1": "sideways", "2": "crisis"},
        }
        rng = np.random.default_rng(7)
        features = pd.DataFrame(
            rng.normal(size=(100, len(FEATURE_NAMES))), columns=FEATURE_NAMES
        )
        baseline = causal_filter(features, parameters)

        changed = features.copy()
        changed.iloc[-1] = 100.0
        changed_result = causal_filter(changed, parameters)
        assert_frame_equal(
            baseline.iloc[:-1],
            changed_result.iloc[:-1],
            check_exact=True,
        )

    def test_frozen_pair_models_have_one_of_each_semantic_state(self) -> None:
        model_directory = PROJECT_DIRECTORY / "user_data" / "regime_models"
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"):
            with self.subTest(symbol=symbol):
                payload = json.loads(
                    (model_directory / f"{symbol}_3state_hmm.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(
                    set(payload["state_labels"].values()),
                    {"trend", "sideways", "crisis"},
                )
                self.assertEqual(
                    payload["development_period"]["end"],
                    "2024-12-31 23:00:00",
                )

    def test_defensive_router_confirms_normal_states_but_enters_crisis_immediately(self) -> None:
        index = pd.date_range("2026-01-01", periods=8, freq="h", tz="UTC")
        filtered = pd.DataFrame(
            {
                "regime": [
                    "trend",
                    "trend",
                    "trend",
                    "sideways",
                    "sideways",
                    "crisis",
                    "sideways",
                    "sideways",
                ],
                "regime_confidence": [0.8, 0.8, 0.8, 0.7, 0.7, 0.5, 0.8, 0.8],
                "regime_crisis_prob": [0.05, 0.05, 0.05, 0.1, 0.1, 0.5, 0.1, 0.1],
            },
            index=index,
        )
        routed = apply_defensive_router(filtered, confirmation_candles=3)
        self.assertEqual(
            routed["regime"].tolist(),
            [
                "uncertain",
                "uncertain",
                "trend",
                "uncertain",
                "uncertain",
                "crisis",
                "uncertain",
                "uncertain",
            ],
        )
        self.assertTrue(bool(routed.loc[index[0], "regime_transition_pending"]))
        self.assertFalse(bool(routed.loc[index[5], "regime_transition_pending"]))

    def test_defensive_router_is_causal(self) -> None:
        index = pd.date_range("2026-01-01", periods=10, freq="h", tz="UTC")
        filtered = pd.DataFrame(
            {
                "regime": ["trend"] * 10,
                "regime_confidence": [0.8] * 10,
                "regime_crisis_prob": [0.05] * 10,
            },
            index=index,
        )
        baseline = apply_defensive_router(filtered, confirmation_candles=3)
        changed = filtered.copy()
        changed.loc[index[7]:, "regime"] = "crisis"
        changed.loc[index[7]:, "regime_crisis_prob"] = 0.8
        revised = apply_defensive_router(changed, confirmation_candles=3)
        assert_frame_equal(baseline.iloc[:7], revised.iloc[:7], check_exact=True)


if __name__ == "__main__":
    unittest.main()
