import unittest

import numpy as np
import pandas as pd

from crypto_quant.macro_regime import (
    build_macro_volume_features,
    combine_regime_signals,
    walk_forward_macro_forecasts,
)


class MacroFeatureTests(unittest.TestCase):
    def test_relationship_sign_is_measured_not_hard_coded(self) -> None:
        index = pd.date_range("2020-01-01", periods=180, freq="1D", tz="UTC")
        equity_return = np.sin(np.arange(len(index)) / 8.0) * 0.01
        btc = 100.0 * np.exp(np.cumsum(equity_return))
        eth = 100.0 * np.exp(np.cumsum(-equity_return))
        markets = {}
        for symbol, close in (("BTCUSDT", btc), ("ETHUSDT", eth)):
            volume = np.full(len(index), 1000.0)
            markets[symbol] = pd.DataFrame(
                {
                    "close": close,
                    "volume": volume,
                    "taker_buy_base_volume": volume / 2.0,
                },
                index=index,
            )
        sp500 = 4000.0 * np.exp(np.cumsum(equity_return))
        macro = pd.DataFrame(
            {
                "SP500": sp500,
                "NASDAQCOM": sp500,
                "VIXCLS": 20.0,
                "DGS10": 4.0,
                "DFF": 3.0,
            },
            index=index,
        )
        features = build_macro_volume_features(
            markets, macro, macro_lag_days=1, relationship_window=40
        )
        self.assertGreater(features["BTCUSDT_corr_sp500"].dropna().median(), 0.9)
        self.assertLess(features["ETHUSDT_corr_sp500"].dropna().median(), -0.9)

    def test_regime_router_can_require_forecast_agreement(self) -> None:
        date = pd.Timestamp("2025-01-01", tz="UTC")
        regimes = pd.DataFrame(
            {"regime": ["high_volatility"], "high_volatility_probability": [0.9]},
            index=[date],
        )
        high = pd.DataFrame(
            {"date": [date, date], "symbol": ["BTCUSDT", "ETHUSDT"], "signal": [1, -1]}
        )
        forecasts = pd.DataFrame(
            {
                "date": [date, date],
                "symbol": ["BTCUSDT", "ETHUSDT"],
                "forecast_signal": [1, 1],
            }
        )
        combined = combine_regime_signals(
            regimes, high, None, forecasts, confirmation="agreement"
        ).set_index("symbol")
        self.assertEqual(combined.at["BTCUSDT", "signal"], 1)
        self.assertEqual(combined.at["ETHUSDT", "signal"], 0)


class MacroRegressionTests(unittest.TestCase):
    def test_future_values_do_not_change_past_forecasts(self) -> None:
        random = np.random.default_rng(31)
        index = pd.date_range("2020-01-01", periods=520, freq="1D", tz="UTC")
        closes = pd.DataFrame(
            100.0 * np.exp(np.cumsum(random.normal(0, 0.01, (len(index), 2)), axis=0)),
            index=index,
            columns=["BTCUSDT", "ETHUSDT"],
        )
        features = pd.DataFrame(
            random.normal(size=(len(index), 6)),
            index=index,
            columns=list("abcdef"),
        )
        arguments = dict(
            training_days=200,
            retrain_days=30,
            ridge_penalty=10.0,
            volatility_threshold=0.05,
        )
        original, _ = walk_forward_macro_forecasts(closes, features, **arguments)
        changed = features.copy()
        changed.loc[index[470]:] *= 100.0
        revised, _ = walk_forward_macro_forecasts(closes, changed, **arguments)
        columns = ["date", "symbol", "forecast", "forecast_signal"]
        pd.testing.assert_frame_equal(
            original.loc[original["date"].lt(index[470]), columns].reset_index(drop=True),
            revised.loc[revised["date"].lt(index[470]), columns].reset_index(drop=True),
        )


if __name__ == "__main__":
    unittest.main()
