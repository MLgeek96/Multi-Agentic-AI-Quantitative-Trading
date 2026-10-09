import unittest

from pathlib import Path
import tempfile

import pandas as pd

from crypto_quant.cross_market import enforce_execution_mode, load_daily_market


class ExecutionModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.signals = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=4, tz="UTC"),
                "symbol": ["BTCUSDT"] * 4,
                "signal": [-1.0, 0.0, 0.5, 1.0],
            }
        )

    def test_spot_removes_short_signals_but_preserves_fractional_longs(self) -> None:
        result = enforce_execution_mode(self.signals, allow_short=False)
        self.assertEqual(result["signal"].tolist(), [0.0, 0.0, 0.5, 1.0])

    def test_futures_preserves_signed_signals(self) -> None:
        result = enforce_execution_mode(self.signals, allow_short=True)
        self.assertEqual(result["signal"].tolist(), [-1.0, 0.0, 0.5, 1.0])

    def test_daily_loader_preserves_order_flow_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily.csv"
            pd.DataFrame(
                {
                    "open_time": ["2026-01-01T00:00:00Z"],
                    "open": [100.0],
                    "high": [110.0],
                    "low": [90.0],
                    "close": [105.0],
                    "volume": [10.0],
                    "quote_volume": [1000.0],
                    "trade_count": [20],
                    "taker_buy_base_volume": [6.0],
                    "taker_buy_quote_volume": [600.0],
                }
            ).to_csv(path, index=False)
            result = load_daily_market(path)
            self.assertEqual(float(result.iloc[0]["taker_buy_base_volume"]), 6.0)
            self.assertEqual(str(result.index.tz), "UTC")


if __name__ == "__main__":
    unittest.main()
