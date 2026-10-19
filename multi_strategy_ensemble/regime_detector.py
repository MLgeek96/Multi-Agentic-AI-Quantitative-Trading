"""
Market Regime Detection Engine
Sourced solely from Lesson 12: Market Regime Detection in 'AI Quantitative Trading: From Zero to One':
- Categorizes market into: TRENDING, RANGING (Mean-Reverting), CRISIS, and TRANSITION.
- Implements Rules-Based Detection using ADX, 20-day realized volatility, and return direction.
- Acts as the "router" that dynamically shifts strategy weights to match market state.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Any

class RegimeDetector:
    def __init__(
        self,
        vol_window: int = 20,
        return_window: int = 20,
        adx_window: int = 14,
        adx_trend_thresh: float = 25.0,
        adx_ranging_thresh: float = 20.0,
        crisis_vol_thresh: float = 0.30
    ):
        self.vol_window = vol_window
        self.return_window = return_window
        self.adx_window = adx_window
        self.adx_trend_thresh = adx_trend_thresh
        self.adx_ranging_thresh = adx_ranging_thresh
        self.crisis_vol_thresh = crisis_vol_thresh

    def compute_adx(self, prices: pd.Series) -> pd.Series:
        """
        Computes synthetic Average Directional Index (ADX) from price series.
        Uses directional movement approximation for closing price series.
        """
        diff = prices.diff()
        pos_dm = diff.clip(lower=0.0)
        neg_dm = (-diff).clip(lower=0.0)

        # True range approximation on closing prices
        tr = prices.diff().abs().rolling(self.adx_window).mean()
        tr = tr.replace(0.0, 1e-6)

        plus_di = 100.0 * (pos_dm.rolling(self.adx_window).mean() / tr)
        minus_di = 100.0 * (neg_dm.rolling(self.adx_window).mean() / tr)

        dx = 100.0 * (plus_di - minus_di).abs() / ((plus_di + minus_di).replace(0.0, 1e-6))
        adx = dx.rolling(self.adx_window).mean().fillna(20.0)
        return adx

    def detect_regimes(self, benchmark_prices: pd.Series) -> pd.DataFrame:
        """
        Classifies each day into market states and determines dynamic strategy weights.
        Returns a DataFrame with columns:
        ['ret_20d', 'vol_20d_ann', 'adx', 'regime', 'weight_trend', 'weight_momentum', 'weight_reversion', 'weight_cash']
        """
        dates = benchmark_prices.index
        daily_ret = benchmark_prices.pct_change().fillna(0.0)

        # Rolling 20-day cumulative return
        ret_20d = (1.0 + daily_ret).rolling(self.return_window).apply(np.prod, raw=True) - 1.0
        ret_20d = ret_20d.fillna(0.0)

        # Rolling 20-day annualized realized volatility (Lesson 12: >30% is crisis warning)
        vol_20d_ann = daily_ret.rolling(self.vol_window).std() * np.sqrt(252.0)
        vol_20d_ann = vol_20d_ann.fillna(0.15)

        # ADX trend strength
        adx = self.compute_adx(benchmark_prices)

        n = len(dates)
        regimes = []
        w_trend = np.zeros(n)
        w_momentum = np.zeros(n)
        w_reversion = np.zeros(n)
        w_cash = np.zeros(n)

        for i in range(n):
            r = ret_20d.iloc[i]
            v = vol_20d_ann.iloc[i]
            a = adx.iloc[i]

            # Lesson 12 Decision Path (Optimized Alpha & Risk Budgeting - Blend B):
            # 1. Crisis Check takes priority: Vol > 30%
            if v >= self.crisis_vol_thresh:
                state = "CRISIS"
                # Crisis allocation: Capital preservation (70% Cash), trend hedge (15%), momentum (15%)
                wt, wm, wr, wc = 0.15, 0.15, 0.00, 0.70

            # 2. Trending Regime: ADX > 25
            elif a >= self.adx_trend_thresh:
                state = "TRENDING_BULL" if r >= 0.0 else "TRENDING_BEAR"
                # Trending allocation: Trend following takes lead (50%), Momentum (40%), Cash reserve (10%)
                wt, wm, wr, wc = 0.50, 0.40, 0.00, 0.10

            # 3. Ranging / Low Directional Index Regime: ADX < 20 and Vol < 20%
            elif a <= self.adx_ranging_thresh and v <= 0.20:
                state = "RANGING"
                # Smart Ranging Allocation (Blend B): Cross-sectional sector-neutral momentum dominates (80%), Trend (10%), Cash reserve (10%)
                wt, wm, wr, wc = 0.10, 0.80, 0.00, 0.10

            # 4. Transition / Gray Zone: Between thresholds
            else:
                state = "TRANSITION"
                # Balanced allocation with high-Sharpe alpha bias: Momentum (60%), Trend (25%), Cash reserve (15%)
                wt, wm, wr, wc = 0.25, 0.60, 0.00, 0.15

            regimes.append(state)
            w_trend[i] = wt
            w_momentum[i] = wm
            w_reversion[i] = wr
            w_cash[i] = wc

        df_regimes = pd.DataFrame({
            "price": benchmark_prices,
            "ret_20d": ret_20d,
            "vol_20d_ann": vol_20d_ann,
            "adx": adx,
            "regime": regimes,
            "weight_trend": w_trend,
            "weight_momentum": w_momentum,
            "weight_reversion": w_reversion,
            "weight_cash": w_cash
        }, index=dates)

        return df_regimes
