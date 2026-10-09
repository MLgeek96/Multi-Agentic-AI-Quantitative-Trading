from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
from pandas import DataFrame, Series

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


_STRATEGY_DIRECTORY = str(Path(__file__).resolve().parent)
if _STRATEGY_DIRECTORY not in sys.path:
    sys.path.insert(0, _STRATEGY_DIRECTORY)

from regime_hmm import (
    apply_defensive_router,
    build_regime_features,
    causal_filter,
    load_hmm_parameters,
)


class HMMRegimeStrategyBase(IStrategy):
    """Three-sleeve regime strategy with an optional FreqAI forecast gate."""

    INTERFACE_VERSION = 3

    can_short = True
    timeframe = "1h"
    process_only_new_candles = True
    startup_candle_count = 1000

    minimal_roi = {"0": 100.0}
    stoploss = -0.15
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False

    use_sequence_filter = False
    enable_trend_sleeve = True
    enable_mean_reversion_sleeve = True
    use_defensive_router = False
    exit_on_uncertain = False
    regime_confidence_threshold = 0.55
    crisis_probability_threshold = 0.45
    regime_confirmation_candles = 3
    trend_prediction_threshold = 0.002

    trend_window = 20 * 24
    trend_band_width = 1.5
    mean_reversion_window = 7 * 24
    mean_reversion_band_width = 2.0

    _regime_model_cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _rsi(close: Series, period: int = 14) -> Series:
        change = close.diff()
        gain = change.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
        loss = (-change.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
        relative_strength = gain / loss.replace(0, np.nan)
        return 100 - 100 / (1 + relative_strength)

    @staticmethod
    def _cross_above(value: Series, level: Series) -> Series:
        return (value > level) & (value.shift(1) <= level.shift(1))

    @staticmethod
    def _cross_below(value: Series, level: Series) -> Series:
        return (value < level) & (value.shift(1) >= level.shift(1))

    def _model_parameters(self, pair: str) -> dict[str, Any]:
        base = pair.split("/")[0]
        symbol = f"{base}USDT"
        trading_mode = str(self.config.get("trading_mode", "futures"))
        default_directory = (
            "regime_models_spot" if trading_mode == "spot" else "regime_models"
        )
        model_directory = str(
            self.config.get("hmm_model_directory", default_directory)
        )
        cache_key = f"{model_directory}:{symbol}"
        if cache_key not in self._regime_model_cache:
            model_path = (
                Path(__file__).resolve().parents[1]
                / model_directory
                / f"{symbol}_3state_hmm.json"
            )
            self._regime_model_cache[cache_key] = load_hmm_parameters(model_path)
        return self._regime_model_cache[cache_key]

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
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
            dataframe[f"%-volatility_{window}"] = dataframe["%-return_1h"].rolling(
                window
            ).std(ddof=0)

        for window in (24, 120, 40 * 24):
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
        if self.use_sequence_filter:
            dataframe = self.freqai.start(dataframe, metadata, self)

        close = dataframe["close"]
        trend_middle = close.rolling(self.trend_window).mean()
        trend_deviation = close.rolling(self.trend_window).std(ddof=0)
        dataframe["trend_middle"] = trend_middle
        dataframe["trend_upper"] = trend_middle + self.trend_band_width * trend_deviation
        dataframe["trend_lower"] = trend_middle - self.trend_band_width * trend_deviation

        mean_reversion_middle = close.rolling(self.mean_reversion_window).mean()
        mean_reversion_deviation = close.rolling(self.mean_reversion_window).std(ddof=0)
        dataframe["mean_reversion_middle"] = mean_reversion_middle
        dataframe["mean_reversion_upper"] = (
            mean_reversion_middle + self.mean_reversion_band_width * mean_reversion_deviation
        )
        dataframe["mean_reversion_lower"] = (
            mean_reversion_middle - self.mean_reversion_band_width * mean_reversion_deviation
        )

        dataframe["ema_fast"] = close.ewm(span=24, adjust=False).mean()
        dataframe["ema_slow"] = close.ewm(span=120, adjust=False).mean()
        macd = close.ewm(span=12, adjust=False).mean() - close.ewm(
            span=26, adjust=False
        ).mean()
        dataframe["macd_histogram"] = macd - macd.ewm(span=9, adjust=False).mean()
        dataframe["rsi_14"] = self._rsi(close)

        regime_features = build_regime_features(dataframe)
        regime = causal_filter(regime_features, self._model_parameters(metadata["pair"]))
        if self.use_defensive_router:
            regime = apply_defensive_router(
                regime,
                confidence_threshold=self.regime_confidence_threshold,
                crisis_probability_threshold=self.crisis_probability_threshold,
                confirmation_candles=self.regime_confirmation_candles,
            )
        for column in regime.columns:
            dataframe[column] = regime[column]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        confidence_ok = dataframe["regime_confidence"] >= self.regime_confidence_threshold
        risk_on = dataframe["regime_crisis_prob"] < self.crisis_probability_threshold
        trend_regime = (
            (dataframe["regime"] == "trend")
            & confidence_ok
            & risk_on
            & self.enable_trend_sleeve
        )
        sideways_regime = (
            (dataframe["regime"] == "sideways")
            & confidence_ok
            & risk_on
            & self.enable_mean_reversion_sleeve
        )

        trend_long = (
            trend_regime
            & self._cross_above(dataframe["close"], dataframe["trend_upper"])
            & (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["macd_histogram"] > 0)
            & (dataframe["rsi_14"] > 55)
        )
        trend_short = (
            trend_regime
            & self._cross_below(dataframe["close"], dataframe["trend_lower"])
            & (dataframe["ema_fast"] < dataframe["ema_slow"])
            & (dataframe["macd_histogram"] < 0)
            & (dataframe["rsi_14"] < 45)
        )
        mean_reversion_long = (
            sideways_regime
            & self._cross_below(dataframe["close"], dataframe["mean_reversion_lower"])
            & (dataframe["rsi_14"] < 35)
        )
        mean_reversion_short = (
            sideways_regime
            & self._cross_above(dataframe["close"], dataframe["mean_reversion_upper"])
            & (dataframe["rsi_14"] > 65)
        )

        if self.use_sequence_filter:
            forecast_ok = dataframe["do_predict"] == 1
            trend_long &= forecast_ok & (
                dataframe["&-future_return"] > self.trend_prediction_threshold
            )
            trend_short &= forecast_ok & (
                dataframe["&-future_return"] < -self.trend_prediction_threshold
            )
            mean_reversion_long &= forecast_ok & (dataframe["&-future_return"] > 0)
            mean_reversion_short &= forecast_ok & (dataframe["&-future_return"] < 0)

        valid_volume = dataframe["volume"] > 0
        prefix = "hmm_lstm" if self.use_sequence_filter else "hmm"
        dataframe.loc[
            trend_long & valid_volume, ["enter_long", "enter_tag"]
        ] = (1, f"{prefix}_trend_long")
        dataframe.loc[
            trend_short & valid_volume, ["enter_short", "enter_tag"]
        ] = (1, f"{prefix}_trend_short")
        dataframe.loc[
            mean_reversion_long & valid_volume, ["enter_long", "enter_tag"]
        ] = (1, f"{prefix}_mean_reversion_long")
        dataframe.loc[
            mean_reversion_short & valid_volume, ["enter_short", "enter_tag"]
        ] = (1, f"{prefix}_mean_reversion_short")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        risk_off = dataframe["regime_crisis_prob"] >= self.crisis_probability_threshold
        dataframe.loc[
            risk_off & (dataframe["volume"] > 0), ["exit_long", "exit_tag"]
        ] = (1, "crisis_cash")
        dataframe.loc[
            risk_off & (dataframe["volume"] > 0), ["exit_short", "exit_tag"]
        ] = (1, "crisis_cash")
        if self.exit_on_uncertain:
            uncertain = dataframe["regime"] == "uncertain"
            dataframe.loc[
                uncertain & (dataframe["volume"] > 0), ["exit_long", "exit_tag"]
            ] = (1, "uncertain_cash")
            dataframe.loc[
                uncertain & (dataframe["volume"] > 0), ["exit_short", "exit_tag"]
            ] = (1, "uncertain_cash")
        return dataframe

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | bool | None:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        candle = dataframe.iloc[-1]
        if candle["regime_crisis_prob"] >= self.crisis_probability_threshold:
            return "crisis_cash"
        if self.exit_on_uncertain and candle["regime"] == "uncertain":
            return "uncertain_cash"

        tag = trade.enter_tag or ""
        confidence_ok = candle["regime_confidence"] >= self.regime_confidence_threshold
        if "mean_reversion" in tag:
            if confidence_ok and candle["regime"] != "sideways":
                return "regime_change"
            if not trade.is_short and current_rate >= candle["mean_reversion_middle"]:
                return "mean_reversion_middle"
            if trade.is_short and current_rate <= candle["mean_reversion_middle"]:
                return "mean_reversion_middle"
        elif "trend" in tag:
            if confidence_ok and candle["regime"] != "trend":
                return "regime_change"
            if not trade.is_short and current_rate <= candle["trend_middle"]:
                return "trend_middle"
            if trade.is_short and current_rate >= candle["trend_middle"]:
                return "trend_middle"
        return None

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


class HMMRegimeSwitchingStrategy(HMMRegimeStrategyBase):
    """HMM regime switching with deterministic trend/sideways sleeves."""


class HMMRegimeLSTMStrategy(HMMRegimeStrategyBase):
    """The same regime strategy with LSTM confirmation on new entries."""

    use_sequence_filter = True


class HMMTrendOnlyStrategy(HMMRegimeStrategyBase):
    """Control: trade only the momentum/breakout sleeve."""

    enable_mean_reversion_sleeve = False


class HMMSidewaysOnlyStrategy(HMMRegimeStrategyBase):
    """Control: trade only the sideways mean-reversion sleeve."""

    enable_trend_sleeve = False


class HMMRegimeDefensiveStrategy(HMMRegimeStrategyBase):
    """Lesson 12/13 policy: explicit uncertainty, hysteresis, and crisis priority."""

    use_defensive_router = True
    exit_on_uncertain = True


class HMMTrendOnlyDefensiveStrategy(HMMRegimeDefensiveStrategy):
    """Defensive regime policy with the previously stronger trend sleeve only."""

    enable_mean_reversion_sleeve = False
