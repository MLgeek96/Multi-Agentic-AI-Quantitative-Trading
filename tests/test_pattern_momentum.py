from dataclasses import replace
import unittest

import numpy as np
import pandas as pd

from crypto_quant.pattern_momentum import (
    DEFAULT_CONFIGS,
    backtest,
    build_structure_bars,
    validate_audit_log,
)


def hourly_bars(periods: int = 16, start: str = "2024-01-01") -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="1h", tz="UTC")
    close = np.arange(100.0, 100.0 + periods)
    return pd.DataFrame(
        {
            "open": close - 0.25,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(periods, 10.0),
        },
        index=index,
    )


class StructureTests(unittest.TestCase):
    def test_four_hour_bar_is_stamped_after_all_source_bars(self) -> None:
        structure = build_structure_bars(hourly_bars(), divergence_lookback=4)
        first = structure.loc[pd.Timestamp("2024-01-01 04:00", tz="UTC")]
        self.assertEqual(first["open"], 99.75)
        self.assertEqual(first["close"], 103.0)
        self.assertEqual(first["source_bar_count"], 4)

    def test_incomplete_structure_bar_is_not_forward_filled(self) -> None:
        bars = hourly_bars().drop(pd.Timestamp("2024-01-01 02:00", tz="UTC"))
        structure = build_structure_bars(bars, divergence_lookback=4)
        first = structure.loc[pd.Timestamp("2024-01-01 04:00", tz="UTC")]
        self.assertFalse(first["complete"])
        self.assertTrue(pd.isna(first["close"]))


class BacktestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = replace(
            DEFAULT_CONFIGS["flag_breakout"],
            fee_bps=0.0,
            slippage_bps=0.0,
            max_holding_bars=100,
        )

    def candidate(self, stop: float, target: float) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "signal_time": pd.Timestamp("2024-01-01 04:00", tz="UTC"),
                    "pattern": "bull_flag",
                    "direction": 1,
                    "stop": stop,
                    "target": target,
                    "confirmation": "passed",
                }
            ]
        )

    def test_minimum_reward_risk_is_enforced_at_actual_fill(self) -> None:
        result = backtest(
            hourly_bars(),
            self.candidate(stop=102.0, target=108.0),
            self.config,
            symbol="BTCUSDT",
            market="usdt_futures",
            initial_equity=10_000,
        )
        self.assertTrue(result.trades.empty)
        self.assertEqual(result.rejections.iloc[0]["reason"], "reward_risk")

    def test_same_bar_stop_wins_over_target_and_audit_reconciles(self) -> None:
        bars = hourly_bars()
        timestamp = pd.Timestamp("2024-01-01 04:00", tz="UTC")
        bars.loc[timestamp, ["open", "high", "low", "close"]] = [104.0, 120.0, 95.0, 105.0]
        result = backtest(
            bars,
            self.candidate(stop=100.0, target=116.0),
            self.config,
            symbol="BTCUSDT",
            market="usdt_futures",
            initial_equity=10_000,
        )
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades.iloc[0]["exit_reason"], "stop")
        validate_audit_log(result)

    def test_one_percent_risk_position_size(self) -> None:
        bars = hourly_bars()
        timestamp = pd.Timestamp("2024-01-01 04:00", tz="UTC")
        bars.loc[timestamp, ["open", "high", "low", "close"]] = [104.0, 105.0, 103.0, 104.0]
        result = backtest(
            bars,
            self.candidate(stop=100.0, target=116.0),
            self.config,
            symbol="BTCUSDT",
            market="usdt_futures",
            initial_equity=10_000,
        )
        # Risk budget is $100 and initial per-unit risk is $4.
        self.assertAlmostEqual(result.trades.iloc[0]["units"], 25.0)

    def test_one_r_moves_stop_to_break_even_for_next_bar(self) -> None:
        bars = hourly_bars()
        entry_time = pd.Timestamp("2024-01-01 04:00", tz="UTC")
        next_time = pd.Timestamp("2024-01-01 05:00", tz="UTC")
        bars.loc[entry_time, ["open", "high", "low", "close"]] = [104.0, 109.0, 103.0, 108.0]
        bars.loc[next_time, ["open", "high", "low", "close"]] = [108.0, 109.0, 103.0, 104.0]
        result = backtest(
            bars,
            self.candidate(stop=100.0, target=116.0),
            self.config,
            symbol="BTCUSDT",
            market="usdt_futures",
            initial_equity=10_000,
        )
        self.assertEqual(result.trades.iloc[0]["exit_reason"], "stop")
        self.assertEqual(result.trades.iloc[0]["exit_price"], 104.0)


if __name__ == "__main__":
    unittest.main()
