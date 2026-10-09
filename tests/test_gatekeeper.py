import unittest

import pandas as pd

from crypto_quant.gatekeeper import apply_hmm_throttle, confirm_breakout_entries


class GatekeeperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = pd.date_range("2025-01-01", periods=5, freq="1D", tz="UTC")

    def long_frame(self, values: list[float], name: str = "BTCUSDT") -> pd.DataFrame:
        return pd.DataFrame(
            {"date": self.index, "symbol": name, "strategy": "test", "signal": values}
        )

    def test_confirmation_is_only_needed_for_entry(self) -> None:
        breakout = self.long_frame([0, 1, 1, 1, 0])
        ma = self.long_frame([0, 1, -1, -1, -1])
        momentum = self.long_frame([0, 1, -1, -1, -1])
        result = confirm_breakout_entries(
            breakout, ma, momentum, confirmation="both"
        )
        self.assertEqual(result["signal"].tolist(), [0, 1, 1, 1, 0])

    def test_unconfirmed_entry_can_be_accepted_later(self) -> None:
        breakout = self.long_frame([0, 1, 1, 1, 0])
        ma = self.long_frame([0, -1, 1, 1, 0])
        momentum = self.long_frame([0, -1, 1, 1, 0])
        result = confirm_breakout_entries(
            breakout, ma, momentum, confirmation="both"
        )
        self.assertEqual(result["signal"].tolist(), [0, 0, 1, 1, 0])

    def test_hmm_changes_size_not_direction(self) -> None:
        signals = self.long_frame([1, -1, 1, -1, 0])
        regimes = pd.DataFrame(
            {
                "regime": [
                    "high_volatility",
                    "low_volatility",
                    "high_volatility",
                    "low_volatility",
                    "low_volatility",
                ],
                "high_volatility_probability": [0.9, 0.1, 0.8, 0.2, 0.1],
            },
            index=self.index,
        )
        result = apply_hmm_throttle(signals, regimes, low_volatility_scale=0.25)
        self.assertEqual(result["signal"].tolist(), [1.0, -0.25, 1.0, -0.25, 0.0])


if __name__ == "__main__":
    unittest.main()
