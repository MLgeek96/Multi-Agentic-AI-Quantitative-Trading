import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from crypto_quant.daily_portfolio import (
    DailyConfig,
    capped_inverse_volatility_weights,
    fit_adaptive_trend,
    run_daily_pipeline,
    update_paper_state,
)


def config(output: Path) -> DailyConfig:
    return DailyConfig(
        symbols=("BTCUSDT", "ETHUSDT"),
        api_base_url="https://example.invalid",
        eligibility_cutoff=pd.Timestamp("2023-08-01", tz="UTC"),
        test_start=pd.Timestamp("2024-10-02", tz="UTC"),
        test_end=pd.Timestamp("2024-10-05", tz="UTC"),
        initial_equity=100_000.0,
        history_days=900,
        parameter_training_days=60,
        volatility_window_days=20,
        covariance_window_days=30,
        target_annual_volatility=0.20,
        minimum_training_sharpe=0.0,
        signal_model="trend_bb_rsi",
        bollinger_window=20,
        bollinger_standard_deviations=2.0,
        rsi_period=14,
        rsi_long_minimum=45.0,
        rsi_long_maximum=70.0,
        max_asset_weight=0.60,
        fee_bps=10.0,
        parameter_grid=((5, 20), (10, 40)),
        output_directory=output,
    )


class FakeClient:
    def __init__(self) -> None:
        self.now = pd.Timestamp("2024-10-05 12:00", tz="UTC")
        self.index = pd.date_range("2023-01-01", "2024-10-04", freq="1D", tz="UTC")

    def server_time(self) -> pd.Timestamp:
        return self.now

    def listing_time(self, symbol: str) -> pd.Timestamp:
        return pd.Timestamp("2020-01-01", tz="UTC")

    def fetch_klines(self, symbol: str, **_: object) -> pd.DataFrame:
        offset = 0.0 if symbol == "BTCUSDT" else 0.8
        trend = np.linspace(100.0 + offset, 180.0 + offset, len(self.index))
        close = trend + np.sin(np.arange(len(self.index)) / 7.0) * (1.0 + offset)
        return pd.DataFrame(
            {
                "symbol": symbol,
                "open_time": self.index,
                "open": close - 0.2,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000.0,
                "close_time": self.index + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1),
                "quote_volume": close * 1000.0,
                "trade_count": 100,
                "taker_buy_base_volume": 500.0,
                "taker_buy_quote_volume": close * 500.0,
                "ignore": 0,
            }
        )


class ModelTests(unittest.TestCase):
    def test_adaptive_model_produces_next_day_signal(self) -> None:
        index = pd.date_range("2023-01-01", periods=600, freq="1D", tz="UTC")
        close = pd.Series(np.linspace(100, 200, len(index)) + np.sin(np.arange(len(index))), index=index)
        model = fit_adaptive_trend(
            close,
            [(5, 20), (10, 50)],
            training_days=120,
            fee_bps=10,
            volatility_window=30,
        )
        self.assertEqual(model["signal"], 1)
        self.assertIn((model["fast_window"], model["slow_window"]), [(5, 20), (10, 50)])

    def test_bollinger_rsi_filter_rejects_overheated_trend(self) -> None:
        index = pd.date_range("2023-01-01", periods=600, freq="1D", tz="UTC")
        close = pd.Series(np.linspace(100.0, 300.0, len(index)), index=index)
        model = fit_adaptive_trend(
            close,
            [(5, 20), (10, 50)],
            training_days=120,
            fee_bps=10,
            volatility_window=30,
            minimum_training_sharpe=-100.0,
            signal_model="trend_bb_rsi",
            rsi_long_minimum=45.0,
            rsi_long_maximum=70.0,
        )
        self.assertEqual(model["trend_signal"], 1)
        self.assertEqual(model["indicator_confirmation"], 0)
        self.assertEqual(model["signal"], 0)

    def test_weight_caps_and_volatility_scaling_never_leverage(self) -> None:
        models = {
            symbol: {"signal": 1, "annualized_volatility": volatility}
            for symbol, volatility in zip(("A", "B", "C"), (0.2, 0.3, 0.4))
        }
        index = pd.date_range("2024-01-01", periods=100, freq="1D")
        returns = pd.DataFrame(
            np.random.default_rng(7).normal(0, 0.01, (100, 3)),
            index=index,
            columns=list(models),
        )
        weights = capped_inverse_volatility_weights(
            models,
            returns,
            max_asset_weight=0.40,
            target_annual_volatility=0.20,
            covariance_window=60,
        )
        self.assertLessEqual(sum(weights.values()), 1.0 + 1e-12)
        self.assertLessEqual(max(weights.values()), 0.40 + 1e-12)

    def test_paper_account_charges_first_day_turnover(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cfg = config(Path(temporary))
            state, record, orders, trades = update_paper_state(
                None,
                date=cfg.test_start,
                prices={"BTCUSDT": 100.0, "ETHUSDT": 50.0},
                weights={"BTCUSDT": 0.5, "ETHUSDT": 0.5},
                config=cfg,
            )
            self.assertAlmostEqual(record["transaction_cost"], 99.9000999001)
            self.assertAlmostEqual(state["equity"], 99_900.0999000999)
            self.assertEqual(len(orders), 2)
            self.assertEqual(trades, [])


class PipelineTests(unittest.TestCase):
    def test_pipeline_backfills_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            cfg = config(output)
            client = FakeClient()
            first = run_daily_pipeline(cfg, client=client)
            self.assertEqual(first["status"], "active")
            self.assertEqual(
                first["processed_dates_this_run"],
                ["2024-10-02", "2024-10-03", "2024-10-04"],
            )
            second = run_daily_pipeline(cfg, client=client)
            self.assertEqual(second["processed_dates_this_run"], [])
            portfolio = pd.read_csv(output / "portfolio_daily.csv")
            signals = pd.read_csv(output / "daily_signals.csv")
            prices = pd.read_csv(output / "portfolio_closing_prices.csv")
            self.assertEqual(len(portfolio), 3)
            self.assertEqual(len(signals), 6)
            self.assertEqual(len(prices), 3)
            manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["orders_enabled"])


if __name__ == "__main__":
    unittest.main()
