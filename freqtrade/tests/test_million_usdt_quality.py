from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
SCRIPT_DIRECTORY = PROJECT_DIRECTORY / "user_data" / "scripts"
sys.path.insert(0, str(SCRIPT_DIRECTORY))

from build_million_usdt_quality_report import (  # noqa: E402
    block_bootstrap_indices,
    square_root_impact_rate,
)


class MillionUsdtQualityTests(unittest.TestCase):
    def test_square_root_market_impact_formula(self) -> None:
        order = pd.Series({"BTC": 100_000.0})
        adv = pd.Series({"BTC": 100_000_000.0})
        volatility = pd.Series({"BTC": 0.04})

        rate, participation = square_root_impact_rate(order, adv, volatility, 1.0)

        self.assertAlmostEqual(participation["BTC"], 0.001)
        self.assertAlmostEqual(rate["BTC"], 0.04 * np.sqrt(0.001))

    def test_zero_order_has_zero_impact(self) -> None:
        order = pd.Series({"BTC": 0.0})
        adv = pd.Series({"BTC": np.nan})
        volatility = pd.Series({"BTC": np.nan})

        rate, participation = square_root_impact_rate(order, adv, volatility, 1.0)

        self.assertEqual(rate["BTC"], 0.0)
        self.assertEqual(participation["BTC"], 0.0)

    def test_block_bootstrap_preserves_requested_length(self) -> None:
        rng = np.random.default_rng(42)
        sampled = block_bootstrap_indices(17, 5, rng)

        self.assertEqual(len(sampled), 17)
        self.assertTrue(((sampled >= 0) & (sampled < 17)).all())


if __name__ == "__main__":
    unittest.main()
