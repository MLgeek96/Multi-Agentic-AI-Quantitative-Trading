from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from crypto_quant.market_cycle_hmm import (  # noqa: E402
    FEATURE_NAMES,
    assign_state_seasons,
    build_bucket_weights,
    build_cycle_features,
    causal_cycle_filter,
)


class MarketCycleHMMTests(unittest.TestCase):
    @staticmethod
    def _closes(rows: int = 200) -> pd.DataFrame:
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0002, 0.02, (rows, 6))
        prices = 100 * np.exp(np.cumsum(returns, axis=0))
        return pd.DataFrame(
            prices,
            index=pd.date_range("2024-01-01", periods=rows, freq="D", tz="UTC"),
            columns=["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"],
        )

    def test_cycle_features_are_causal(self) -> None:
        closes = self._closes()
        cutoff = 150
        baseline = build_cycle_features(closes)
        changed = closes.copy()
        changed.iloc[cutoff:] *= np.array([1.2, 0.8, 1.5, 0.7, 1.3, 0.6])
        changed_features = build_cycle_features(changed)
        assert_frame_equal(
            baseline.iloc[:cutoff],
            changed_features.iloc[:cutoff],
            check_exact=True,
        )
        self.assertEqual(list(baseline.columns), list(FEATURE_NAMES))

    def test_state_assignment_is_unique(self) -> None:
        statistics = pd.DataFrame(
            {
                "bitcoin_relative_momentum_30d": [0.3, -0.1, -0.1],
                "ethereum_relative_momentum_30d": [-0.1, 0.4, -0.1],
                "altcoin_relative_momentum_30d": [-0.2, -0.3, 0.5],
            },
            index=[0, 1, 2],
        )
        labels = assign_state_seasons(statistics)
        self.assertEqual(labels[0], "bitcoin_season")
        self.assertEqual(labels[1], "ethereum_season")
        self.assertEqual(labels[2], "altcoin_season")
        self.assertEqual(len(set(labels.values())), 3)

    def test_equal_bucket_weights_split_altcoin_sleeve(self) -> None:
        date = pd.Timestamp("2026-01-01", tz="UTC")
        directions = pd.DataFrame(
            [[1, -1, 1, 1, 0, 0]],
            index=[date],
            columns=["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"],
        )
        weights = build_bucket_weights(directions)
        self.assertAlmostEqual(weights.at[date, "BTC"], 1 / 3)
        self.assertAlmostEqual(weights.at[date, "ETH"], -1 / 3)
        self.assertAlmostEqual(weights.at[date, "SOL"], 1 / 6)
        self.assertAlmostEqual(weights.at[date, "XRP"], 1 / 6)
        self.assertAlmostEqual(weights.loc[date].abs().sum(), 1.0)

    def test_cycle_filter_does_not_change_past_probabilities(self) -> None:
        rng = np.random.default_rng(7)
        features = pd.DataFrame(
            rng.normal(size=(100, len(FEATURE_NAMES))),
            columns=FEATURE_NAMES,
            index=pd.date_range("2025-01-01", periods=100, freq="D", tz="UTC"),
        )
        parameters = {
            "feature_names": list(FEATURE_NAMES),
            "scaler_mean": [0.0] * len(FEATURE_NAMES),
            "scaler_scale": [1.0] * len(FEATURE_NAMES),
            "startprob": [0.5, 0.3, 0.2],
            "transmat": [
                [0.90, 0.07, 0.03],
                [0.05, 0.90, 0.05],
                [0.04, 0.06, 0.90],
            ],
            "means": [
                [1.0] * len(FEATURE_NAMES),
                [0.0] * len(FEATURE_NAMES),
                [-1.0] * len(FEATURE_NAMES),
            ],
            "variances": [[1.0] * len(FEATURE_NAMES)] * 3,
            "state_labels": {
                "0": "bitcoin_season",
                "1": "ethereum_season",
                "2": "altcoin_season",
            },
        }
        baseline = causal_cycle_filter(features, parameters)
        changed = features.copy()
        changed.iloc[70:] += 20
        changed_result = causal_cycle_filter(changed, parameters)
        assert_frame_equal(baseline.iloc[:70], changed_result.iloc[:70], check_exact=True)

    def test_cycle_tilt_preserves_total_bucket_budget(self) -> None:
        date = pd.Timestamp("2026-01-01", tz="UTC")
        directions = pd.DataFrame(
            [[1, 1, 1, 1, 1, 1]],
            index=[date],
            columns=["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"],
        )
        cycles = pd.Series(["altcoin_season"], index=[date])
        weights = build_bucket_weights(directions, cycles)
        self.assertAlmostEqual(weights.at[date, "BTC"], 0.25)
        self.assertAlmostEqual(weights.at[date, "ETH"], 0.25)
        self.assertAlmostEqual(weights.loc[date, list(("SOL", "XRP", "BNB", "DOGE"))].sum(), 0.50)
        self.assertAlmostEqual(weights.loc[date].abs().sum(), 1.0)


if __name__ == "__main__":
    unittest.main()
