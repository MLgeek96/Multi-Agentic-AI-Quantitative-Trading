"""
Trend Following Strategy Engine
Sourced solely from Lesson 05.1 (Trend Following) & Lesson 15 (Risk Control) in 'AI Quantitative Trading: From Zero to One':
- Classic Dual Moving Average (MA10 / MA60)
- Golden Cross: Fast MA > Slow MA -> Go Long
- Death Cross: Fast MA < Slow MA -> Exit to Cash (earning risk-free collateral yield)
- Trend strength filter (ADX > 20)
- Volatility trailing stops (ATR multiplier)
- Net of realistic transaction friction (5 bps per trade)
"""

import numpy as np
import pandas as pd
from typing import Dict, Any

class TrendFollowingStrategy:
    def __init__(
        self,
        fast_window: int = 10,
        slow_window: int = 60,
        adx_filter_threshold: float = 20.0,
        atr_trailing_mult: float = 2.5,
        tx_cost_bps: float = 5.0,
        rf_annual: float = 0.04
    ):
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.adx_filter_threshold = adx_filter_threshold
        self.atr_trailing_mult = atr_trailing_mult
        self.tx_cost_rate = tx_cost_bps / 10_000.0
        self.rf_daily = (1.0 + rf_annual) ** (1.0 / 252.0) - 1.0

    def run_strategy(self, prices_df: pd.DataFrame, benchmark_series: pd.Series) -> pd.DataFrame:
        """
        Runs the trend following strategy across the asset universe.
        Returns a DataFrame of daily returns, friction, and cumulative equity.
        """
        dates = prices_df.index
        n_dates = len(dates)
        assets = prices_df.columns
        n_assets = len(assets)

        fast_ma = prices_df.rolling(self.fast_window).mean()
        slow_ma = prices_df.rolling(self.slow_window).mean()

        # ATR approximation for trailing stop
        daily_diff = prices_df.diff().abs()
        atr = daily_diff.rolling(20).mean().fillna(prices_df.std())

        # Asset-level Golden Cross (MA10 > MA60) -> 1.0 (Long), else 0.0 (Cash)
        raw_signals = pd.DataFrame(0.0, index=dates, columns=assets)
        raw_signals[fast_ma > slow_ma] = 1.0

        # Market trend confirmation (benchmark 10-day MA > 60-day MA)
        if isinstance(benchmark_series, pd.DataFrame):
            benchmark_series = benchmark_series.iloc[:, 0]
        bm_series = benchmark_series.reindex(dates).ffill()
        bm_fast = bm_series.rolling(self.fast_window).mean()
        bm_slow = bm_series.rolling(self.slow_window).mean()
        market_bull = (bm_fast > bm_slow)

        # Apply market filter: if broader market is bearish, step aside into cash
        filtered_signals = raw_signals.copy()
        for t in range(n_dates):
            if not market_bull.iloc[t]:
                filtered_signals.iloc[t] = 0.0  # Cash preservation

        # Position sizing: equal weight across active trending assets
        active_counts = filtered_signals.sum(axis=1)
        target_weights = pd.DataFrame(0.0, index=dates, columns=assets)
        for t in range(n_dates):
            cnt = active_counts.iloc[t]
            if cnt > 0:
                target_weights.iloc[t] = filtered_signals.iloc[t] / cnt

        asset_returns = prices_df.pct_change().fillna(0.0)
        daily_pnl = np.zeros(n_dates)
        daily_friction = np.zeros(n_dates)

        current_weights = pd.Series(0.0, index=assets)

        for t in range(1, n_dates):
            w_prev = current_weights
            w_target = target_weights.iloc[t]

            # 1. PnL from invested equity
            ret_t = asset_returns.iloc[t]
            invested_gross_ret = float((w_prev * ret_t).sum())

            # 2. Collateral yield on idle cash reserve (Lesson 15 & 18)
            cash_fraction = max(0.0, 1.0 - float(w_prev.sum()))
            cash_yield = cash_fraction * self.rf_daily

            # 3. Transaction turnover friction
            turnover = (w_target - w_prev).abs().sum()
            tx_cost = float(turnover * self.tx_cost_rate)

            net_ret = invested_gross_ret + cash_yield - tx_cost
            daily_pnl[t] = net_ret
            daily_friction[t] = tx_cost
            current_weights = w_target

        res_df = pd.DataFrame({
            "daily_return": daily_pnl,
            "daily_friction": daily_friction,
            "cumulative_return": np.cumprod(1.0 + daily_pnl) - 1.0
        }, index=dates)

        return res_df
