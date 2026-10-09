import unittest

import numpy as np
import pandas as pd

from crypto_quant.strategy_selection import (
    build_linear_regression_signals,
    build_rule_signals,
)


class RuleSignalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = pd.date_range("2020-01-01", periods=220, freq="1D", tz="UTC")

    def test_ma_crossover_matches_up_and_down_trends(self) -> None:
        closes = pd.DataFrame(
            {
                "BTCUSDT": np.linspace(100.0, 250.0, len(self.index)),
                "ETHUSDT": np.linspace(250.0, 100.0, len(self.index)),
            },
            index=self.index,
        )
        signals = build_rule_signals(
            closes,
            family="ma_crossover",
            parameters={"fast": 5, "slow": 20, "filter": "none"},
        )
        latest = signals.loc[signals["date"].eq(self.index[-1])].set_index("symbol")
        self.assertEqual(latest.at["BTCUSDT", "signal"], 1.0)
        self.assertEqual(latest.at["ETHUSDT", "signal"], -1.0)

    def test_bollinger_breakout_buys_upper_band_break(self) -> None:
        close = np.full(len(self.index), 100.0)
        close[-1] = 130.0
        closes = pd.DataFrame({"BTCUSDT": close}, index=self.index)
        signals = build_rule_signals(
            closes,
            family="bollinger_breakout",
            parameters={"window": 20, "width": 2.0, "exit_z": 0.0},
        )
        self.assertEqual(signals.iloc[-1]["signal"], 1.0)

    def test_grid_uses_fractional_staged_exposure(self) -> None:
        close = np.full(len(self.index), 100.0)
        close[-1] = 96.0
        closes = pd.DataFrame({"BTCUSDT": close}, index=self.index)
        signals = build_rule_signals(
            closes,
            family="dynamic_grid",
            parameters={
                "center_window": 20,
                "grid_step": 0.01,
                "levels": 4,
                "trend_threshold": 1.0,
                "trend_fast": 20,
                "trend_slow": 100,
            },
        )
        self.assertGreater(signals.iloc[-1]["signal"], 0.0)
        self.assertLessEqual(signals.iloc[-1]["signal"], 1.0)


class RegressionTests(unittest.TestCase):
    def test_future_price_change_does_not_alter_past_forecasts(self) -> None:
        random = np.random.default_rng(19)
        index = pd.date_range("2020-01-01", periods=620, freq="1D", tz="UTC")
        returns = random.normal(0.0002, 0.015, (len(index), 2))
        closes = pd.DataFrame(
            100.0 * np.exp(np.cumsum(returns, axis=0)),
            index=index,
            columns=["BTCUSDT", "ETHUSDT"],
        )
        arguments = {
            "training_days": 200,
            "retrain_days": 30,
            "ridge_penalty": 10.0,
            "volatility_threshold": 0.05,
        }
        original, _ = build_linear_regression_signals(closes, **arguments)
        changed = closes.copy()
        changed.loc[index[560]:] *= 4.0
        revised, _ = build_linear_regression_signals(changed, **arguments)
        cutoff = index[559]
        columns = ["date", "symbol", "forecast_next_log_return", "signal"]
        pd.testing.assert_frame_equal(
            original.loc[original["date"].le(cutoff), columns].reset_index(drop=True),
            revised.loc[revised["date"].le(cutoff), columns].reset_index(drop=True),
        )


if __name__ == "__main__":
    unittest.main()
