from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from crypto_quant.data_quality import audit_ohlcv, require_quality
from crypto_quant.daily_portfolio import run_daily_pipeline
from test_daily_portfolio import FakeClient, config


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.frame = self.client.fetch_klines("BTCUSDT")

    def audit(self, frame):
        return audit_ohlcv(frame, symbol="BTCUSDT", closed_at=self.client.now, expected_last=self.client.index[-1])

    def test_valid_window_and_nonmutation(self):
        before = self.frame.copy(deep=True)
        report = self.audit(self.frame)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["missing_bars"], 0)
        pd.testing.assert_frame_equal(before, self.frame)

    def test_reject_corrupt_stale_and_incomplete_windows(self):
        cases = {}
        cases["duplicate"] = pd.concat([self.frame, self.frame.iloc[[-1]]])
        cases["gap"] = self.frame.drop(index=100)
        cases["stale"] = self.frame.iloc[:-1]
        cases["order"] = self.frame.iloc[::-1]
        cases["schema"] = self.frame.drop(columns="low")
        for name, column, value in (("nan", "close", np.nan), ("infinite", "close", np.inf),
                                    ("price", "low", -1), ("ohlc", "high", 0.1), ("volume", "volume", -1),
                                    ("trades", "trade_count", 1.5), ("taker", "taker_buy_base_volume", 2000),
                                    ("identity", "symbol", "ETHUSDT")):
            frame = self.frame.copy()
            if column == "trade_count":
                frame[column] = frame[column].astype(float)
            frame.loc[frame.index[-1], column] = value
            cases[name] = frame
        naive = self.frame.copy()
        naive["open_time"] = naive["open_time"].dt.tz_localize(None)
        cases["naive"] = naive
        unclosed = self.frame.copy()
        unclosed.loc[unclosed.index[-1], "close_time"] = self.client.now + pd.Timedelta(days=1)
        cases["future"] = unclosed
        for name, frame in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    require_quality(self.audit(frame))

    def test_daily_gate_does_not_mutate_ledger_on_quality_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = config(Path(temp))
            run_daily_pipeline(cfg, client=self.client)
            saved = {p.name: p.read_bytes() for p in Path(temp).glob("*") if p.is_file() and p.name != "data_quality.json"}
            original = self.client.fetch_klines
            self.client.fetch_klines = lambda *a, **k: original(*a, **k).iloc[:-1]
            with self.assertRaisesRegex(ValueError, "freshness"):
                run_daily_pipeline(cfg, client=self.client)
            for name, raw in saved.items():
                self.assertEqual((Path(temp) / name).read_bytes(), raw)

    def test_interval_and_close_boundary_anomalies_are_preserved(self):
        shifted = self.frame.copy()
        shifted["open_time"] += pd.Timedelta(minutes=1)
        report = self.audit(shifted)
        self.assertTrue(any(c["name"] == "interval_alignment" and not c["passed"] for c in report["checks"]))
        short = self.frame.copy()
        short.loc[0, "close_time"] = short.loc[0, "open_time"] - pd.Timedelta(minutes=1)
        report = self.audit(short)
        self.assertEqual(report["invalid_close_boundaries"], 1)
        self.assertEqual(short.loc[0, "close_time"], short.loc[0, "open_time"] - pd.Timedelta(minutes=1))


if __name__ == "__main__":
    unittest.main()
