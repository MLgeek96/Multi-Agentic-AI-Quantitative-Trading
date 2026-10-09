import unittest

import numpy as np
import pandas as pd

from crypto_quant.hmm_regime import (
    GaussianHMM2,
    HMMRegimeConfig,
    backtest_regime_strategy,
    build_strategy_signals,
    build_target_weights,
    walk_forward_regime_probabilities,
)


class HMMTests(unittest.TestCase):
    def test_two_state_model_identifies_higher_variance_block(self) -> None:
        random = np.random.default_rng(11)
        low = random.normal(0.0, 0.4, (400, 2))
        high = random.normal(0.0, 2.5, (400, 2))
        values = np.vstack([low, high])
        model = GaussianHMM2.fit(values, volatility_dimensions=[0, 1])
        probability = model.filter_probabilities(values)[:, model.high_volatility_state]
        self.assertLess(float(probability[100:350].mean()), 0.25)
        self.assertGreater(float(probability[500:750].mean()), 0.75)

    def test_future_observations_do_not_change_past_regime_probability(self) -> None:
        random = np.random.default_rng(5)
        index = pd.date_range("2020-01-01", periods=180, freq="1D", tz="UTC")
        features = pd.DataFrame(
            random.normal(size=(len(index), 4)),
            index=index,
            columns=["return_A", "return_B", "log_vol_A", "log_vol_B"],
        )
        config = HMMRegimeConfig(
            symbols=("A", "B"),
            hmm_training_days=90,
            hmm_minimum_training_days=60,
            hmm_retrain_days=15,
            hmm_iterations=30,
        )
        original, _ = walk_forward_regime_probabilities(features, config)
        changed = features.copy()
        changed.iloc[140:] *= 100.0
        revised, _ = walk_forward_regime_probabilities(changed, config)
        pd.testing.assert_series_equal(
            original.loc[: index[139], "high_volatility_probability"],
            revised.loc[: index[139], "high_volatility_probability"],
        )


class SignalTests(unittest.TestCase):
    def config(self) -> HMMRegimeConfig:
        return HMMRegimeConfig(
            hmm_training_days=120,
            hmm_minimum_training_days=60,
            sma_fast=5,
            sma_slow=20,
            bollinger_window=20,
            risk_volatility_window=10,
            covariance_window=20,
            target_annual_volatility=10.0,
            fee_bps=0.0,
        )

    def test_high_volatility_can_long_and_short_at_the_same_time(self) -> None:
        index = pd.date_range("2024-01-01", periods=180, freq="1D", tz="UTC")
        closes = pd.DataFrame(
            {
                "BTCUSDT": np.linspace(100.0, 250.0, len(index)),
                "ETHUSDT": np.linspace(250.0, 100.0, len(index)),
            },
            index=index,
        )
        regimes = pd.DataFrame(
            {
                "high_volatility_probability": 0.9,
                "regime": "high_volatility",
                "model_refit": False,
            },
            index=index,
        )
        config = self.config()
        signals = build_strategy_signals(closes, regimes, config)
        latest = signals.loc[signals["date"].eq(index[-1])].set_index("symbol")
        self.assertEqual(latest.at["BTCUSDT", "signal"], 1)
        self.assertEqual(latest.at["ETHUSDT", "signal"], -1)
        weights = build_target_weights(closes, signals, config)
        self.assertGreater(weights.at[index[-1], "BTCUSDT"], 0)
        self.assertLess(weights.at[index[-1], "ETHUSDT"], 0)
        self.assertLessEqual(float(weights.loc[index[-1]].abs().sum()), 1.0 + 1e-12)

    def test_close_signal_is_applied_to_next_day_return(self) -> None:
        index = pd.date_range("2024-01-01", periods=80, freq="1D", tz="UTC")
        btc = np.linspace(100.0, 120.0, len(index))
        eth = np.linspace(100.0, 110.0, len(index))
        btc[-2] *= 2.0
        closes = pd.DataFrame({"BTCUSDT": btc, "ETHUSDT": eth}, index=index)
        records = []
        for date in index:
            for symbol in ("BTCUSDT", "ETHUSDT"):
                records.append(
                    {
                        "date": date,
                        "symbol": symbol,
                        "signal": int(date == index[-2] and symbol == "BTCUSDT"),
                    }
                )
        config = self.config()
        portfolio = backtest_regime_strategy(closes, pd.DataFrame(records), config)
        self.assertEqual(portfolio.at[index[-2], "applied_weight_BTCUSDT"], 0.0)
        self.assertGreater(portfolio.at[index[-1], "applied_weight_BTCUSDT"], 0.0)


if __name__ == "__main__":
    unittest.main()
