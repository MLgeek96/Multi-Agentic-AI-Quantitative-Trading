from __future__ import annotations

from pandas import DataFrame

from freqtrade.strategy import IStrategy


class BollingerBreakout40D(IStrategy):
    """Long/short 40-day Bollinger breakout control on hourly candles."""

    INTERFACE_VERSION = 3

    can_short = True
    timeframe = "1h"
    process_only_new_candles = True
    startup_candle_count = 1000

    # Exit is controlled by the middle-band signal.  The large ROI target keeps
    # Freqtrade's ROI table from closing trades before that rule fires.
    minimal_roi = {"0": 100.0}
    stoploss = -0.25
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False

    bollinger_window = 40 * 24
    bollinger_width = 1.5

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        middle = dataframe["close"].rolling(self.bollinger_window).mean()
        deviation = dataframe["close"].rolling(self.bollinger_window).std(ddof=0)
        dataframe["bb_middle"] = middle
        dataframe["bb_upper"] = middle + self.bollinger_width * deviation
        dataframe["bb_lower"] = middle - self.bollinger_width * deviation
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long_cross = (dataframe["close"] > dataframe["bb_upper"]) & (
            dataframe["close"].shift(1) <= dataframe["bb_upper"].shift(1)
        )
        short_cross = (dataframe["close"] < dataframe["bb_lower"]) & (
            dataframe["close"].shift(1) >= dataframe["bb_lower"].shift(1)
        )

        dataframe.loc[long_cross & (dataframe["volume"] > 0), ["enter_long", "enter_tag"]] = (
            1,
            "bb40d_long",
        )
        dataframe.loc[
            short_cross & (dataframe["volume"] > 0), ["enter_short", "enter_tag"]
        ] = (1, "bb40d_short")
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

