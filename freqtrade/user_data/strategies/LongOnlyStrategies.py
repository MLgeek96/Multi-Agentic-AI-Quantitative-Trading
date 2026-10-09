from __future__ import annotations

from pandas import DataFrame

from BollingerBreakout40D import BollingerBreakout40D
from HMMRegimeSwitchingStrategy import (
    HMMRegimeDefensiveStrategy,
    HMMRegimeLSTMStrategy,
    HMMRegimeSwitchingStrategy,
    HMMTrendOnlyDefensiveStrategy,
    HMMTrendOnlyStrategy,
)
from SequenceBreakoutStrategy import SequenceBreakoutStrategy


class LongOnlyMixin:
    """Use the parent strategy's long rules while disabling every short entry."""

    can_short = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        if "enter_short" in dataframe:
            short_rows = dataframe["enter_short"].fillna(0).astype(bool)
            dataframe.loc[short_rows, "enter_tag"] = None
            dataframe.loc[:, "enter_short"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_exit_trend(dataframe, metadata)
        if "exit_short" in dataframe:
            dataframe.loc[:, "exit_short"] = 0
        return dataframe


class BollingerBreakout40DLongOnly(LongOnlyMixin, BollingerBreakout40D):
    """Long-only Bollinger control for futures and spot comparisons."""


class SequenceBreakoutLongOnlyStrategy(LongOnlyMixin, SequenceBreakoutStrategy):
    """Long-only RNN/GRU/LSTM/Transformer-gated Bollinger strategy."""


class HMMTrendOnlyLongOnlyStrategy(LongOnlyMixin, HMMTrendOnlyStrategy):
    """Long-only HMM trend sleeve."""


class HMMRegimeSwitchingLongOnlyStrategy(LongOnlyMixin, HMMRegimeSwitchingStrategy):
    """Long-only HMM trend/sideways sleeves."""


class HMMRegimeDefensiveLongOnlyStrategy(LongOnlyMixin, HMMRegimeDefensiveStrategy):
    """Long-only defensive HMM sleeves."""


class HMMTrendOnlyDefensiveLongOnlyStrategy(
    LongOnlyMixin, HMMTrendOnlyDefensiveStrategy
):
    """Long-only defensive HMM trend sleeve."""


class HMMRegimeLSTMLongOnlyStrategy(LongOnlyMixin, HMMRegimeLSTMStrategy):
    """Long-only HMM plus LSTM strategy."""
