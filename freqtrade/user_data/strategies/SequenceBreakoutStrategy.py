from __future__ import annotations

import numpy as np
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class SequenceBreakoutStrategy(IStrategy):
    """Bollinger breakout whose new entries require a FreqAI sequence forecast.

    RNN, GRU, LSTM, and Transformer runs all use this exact strategy.  Only
    the sequence model changes, which makes their results directly comparable.
    """

    INTERFACE_VERSION = 3

    can_short = True
    timeframe = "1h"
    process_only_new_candles = True
    startup_candle_count = 1000

    minimal_roi = {"0": 100.0}
    stoploss = -0.25
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False

    bollinger_window = 40 * 24
    bollinger_width = 1.5
    prediction_threshold = 0.002

    @staticmethod
    def _rsi(close, period: int = 14):
        change = close.diff()
        gain = change.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
        loss = (-change.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
        relative_strength = gain / loss.replace(0, np.nan)
        return 100 - 100 / (1 + relative_strength)

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        # Deliberately unused.  The recurrent model receives one compact feature
        # vector per hourly candle instead of automatically duplicated periods.
        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        return dataframe

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        close = dataframe["close"]
        log_close = np.log(close.replace(0, np.nan))
        log_volume = np.log1p(dataframe["volume"])

        dataframe["%-return_1h"] = log_close.diff()
        dataframe["%-return_6h"] = log_close.diff(6)
        dataframe["%-return_24h"] = log_close.diff(24)
        dataframe["%-range"] = (dataframe["high"] - dataframe["low"]) / close
        dataframe["%-body"] = (dataframe["close"] - dataframe["open"]) / dataframe["open"]
        dataframe["%-volume_change"] = log_volume.diff()

        for window in (6, 24, 168):
            dataframe[f"%-volatility_{window}"] = dataframe["%-return_1h"].rolling(window).std(
                ddof=0
            )

        for window in (24, 120, self.bollinger_window):
            moving_average = close.rolling(window).mean()
            dataframe[f"%-ma_ratio_{window}"] = close / moving_average - 1

        volume_mean = log_volume.rolling(168).mean()
        volume_std = log_volume.rolling(168).std(ddof=0).replace(0, np.nan)
        dataframe["%-volume_z_168"] = (log_volume - volume_mean) / volume_std
        dataframe["%-rsi_14"] = self._rsi(close) / 100.0

        hour = dataframe["date"].dt.hour
        weekday = dataframe["date"].dt.dayofweek
        dataframe["%-hour_sin"] = np.sin(2 * np.pi * hour / 24)
        dataframe["%-hour_cos"] = np.cos(2 * np.pi * hour / 24)
        dataframe["%-weekday_sin"] = np.sin(2 * np.pi * weekday / 7)
        dataframe["%-weekday_cos"] = np.cos(2 * np.pi * weekday / 7)
        return dataframe

    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        horizon = int(self.freqai_info["feature_parameters"]["label_period_candles"])
        dataframe["&-future_return"] = np.log(
            dataframe["close"].shift(-horizon) / dataframe["close"]
        )
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.freqai.start(dataframe, metadata, self)

        middle = dataframe["close"].rolling(self.bollinger_window).mean()
        deviation = dataframe["close"].rolling(self.bollinger_window).std(ddof=0)
        dataframe["bb_middle"] = middle
        dataframe["bb_upper"] = middle + self.bollinger_width * deviation
        dataframe["bb_lower"] = middle - self.bollinger_width * deviation
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        forecast_ok = dataframe["do_predict"] == 1
        long_cross = (dataframe["close"] > dataframe["bb_upper"]) & (
            dataframe["close"].shift(1) <= dataframe["bb_upper"].shift(1)
        )
        short_cross = (dataframe["close"] < dataframe["bb_lower"]) & (
            dataframe["close"].shift(1) >= dataframe["bb_lower"].shift(1)
        )

        dataframe.loc[
            long_cross
            & forecast_ok
            & (dataframe["&-future_return"] > self.prediction_threshold)
            & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "bb40d_plus_sequence_long")
        dataframe.loc[
            short_cross
            & forecast_ok
            & (dataframe["&-future_return"] < -self.prediction_threshold)
            & (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"],
        ] = (1, "bb40d_plus_sequence_short")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] <= dataframe["bb_middle"]) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "middle_band")
        dataframe.loc[
            (dataframe["close"] >= dataframe["bb_middle"]) & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"],
        ] = (1, "middle_band")
        return dataframe

    def leverage(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        return 1.0
