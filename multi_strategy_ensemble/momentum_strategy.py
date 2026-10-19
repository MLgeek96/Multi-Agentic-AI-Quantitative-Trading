"""
Cross-Sectional & Time-Series Momentum Engine
Sourced solely from Lesson 05 (Strategy Paradigms) & Lesson 16 (Portfolio Construction) in 'AI Quantitative Trading: From Zero to One':
- Relative strength ranking over 60-day trailing window
- Long top performers (leaders)
- Volatility scaling (1 / sigma) from Lesson 16 risk parity
- T-bill cash collateral yield on unallocated margin
- Bi-weekly rebalancing to control transaction friction
"""

import numpy as np
import pandas as pd
from typing import Dict, Any

class MomentumStrategy:
    def __init__(
        self,
        lookback_days: int = 60,
        rebalance_interval: int = 10,
        top_k: int = 5,
        vol_scale: bool = True,
        sector_neutral: bool = True,
        k_per_sector: int = 2,
        sector_mapping: Dict[str, str] = None,
        tx_cost_bps: float = 5.0,
        rf_annual: float = 0.04
    ):
        self.lookback_days = lookback_days
        self.rebalance_interval = rebalance_interval
        self.top_k = top_k
        self.vol_scale = vol_scale
        self.sector_neutral = sector_neutral
        self.k_per_sector = k_per_sector
        self.sector_mapping = sector_mapping or {}
        self.tx_cost_rate = tx_cost_bps / 10_000.0
        self.rf_daily = (1.0 + rf_annual) ** (1.0 / 252.0) - 1.0

    def run_strategy(self, prices_df: pd.DataFrame, sector_mapping: Dict[str, str] = None) -> pd.DataFrame:
        """
        Runs the cross-sectional momentum strategy.
        Supports Sector-Neutral Long/Short Risk Controls (Lesson 16) across large multi-asset universes.
        Returns a DataFrame with daily_return, daily_friction, and cumulative_return.
        """
        if sector_mapping is not None:
            self.sector_mapping = sector_mapping

        dates = prices_df.index
        n_dates = len(dates)
        assets = prices_df.columns
        asset_returns = prices_df.pct_change().fillna(0.0)

        # Trailing 60-day returns for momentum ranking
        trailing_ret = prices_df.pct_change(self.lookback_days).fillna(0.0)

        # Trailing 20-day volatility for inverse-volatility scaling (Lesson 16)
        trailing_vol = asset_returns.rolling(20).std().replace(0.0, np.nan).fillna(0.02)

        # Build sector groupings if sector-neutral is enabled
        sector_groups = {}
        if self.sector_neutral and self.sector_mapping:
            for a in assets:
                sec = self.sector_mapping.get(a, "Other")
                sector_groups.setdefault(sec, []).append(a)

        daily_pnl = np.zeros(n_dates)
        daily_friction = np.zeros(n_dates)
        current_weights = pd.Series(0.0, index=assets)

        for t in range(self.lookback_days, n_dates):
            # 1. PnL from previously held positions
            ret_t = asset_returns.iloc[t]
            gross_ret = float((current_weights * ret_t).sum())

            # 2. Cash yield on idle cash
            cash_fraction = max(0.0, 1.0 - float(current_weights.abs().sum()))
            cash_yield = cash_fraction * self.rf_daily

            tx_cost = 0.0

            # Rebalance on scheduled intervals (Lesson 16: periodic rebalancing controls friction)
            if t % self.rebalance_interval == 0:
                dt = dates[t]
                new_weights = pd.Series(0.0, index=assets)

                if self.sector_neutral and sector_groups:
                    # Lesson 16 Sector-Neutral Portfolio Construction
                    valid_secs = [s for s, syms in sector_groups.items() if len(syms) >= 4]
                    n_valid_secs = len(valid_secs)

                    if n_valid_secs > 0:
                        weight_per_sec = 1.0 / n_valid_secs
                        for sec in valid_secs:
                            syms = sector_groups[sec]
                            ranks = trailing_ret.loc[dt, syms].sort_values()
                            k = min(self.k_per_sector, len(syms) // 2)
                            longs = ranks.tail(k).index
                            shorts = ranks.head(k).index

                            if self.vol_scale:
                                inv_l = 1.0 / trailing_vol.loc[dt, longs]
                                inv_s = 1.0 / trailing_vol.loc[dt, shorts]
                                w_long = (inv_l / inv_l.sum()) * (0.5 * weight_per_sec)
                                w_short = -(inv_s / inv_s.sum()) * (0.5 * weight_per_sec)
                            else:
                                w_long = (0.5 * weight_per_sec) / k
                                w_short = -(0.5 * weight_per_sec) / k

                            new_weights.loc[longs] = w_long
                            new_weights.loc[shorts] = w_short
                else:
                    # Global cross-sectional top-k unconstrained
                    ranks = trailing_ret.iloc[t].sort_values()
                    top_leaders = ranks.tail(self.top_k).index

                    if self.vol_scale:
                        inv_vols = 1.0 / trailing_vol.loc[dt, top_leaders]
                        new_weights.loc[top_leaders] = inv_vols / inv_vols.sum()
                    else:
                        new_weights.loc[top_leaders] = 1.0 / self.top_k

                turnover = (new_weights - current_weights).abs().sum()
                tx_cost = float(turnover * self.tx_cost_rate)
                current_weights = new_weights

            net_ret = gross_ret + cash_yield - tx_cost
            daily_pnl[t] = net_ret
            daily_friction[t] = tx_cost

        res_df = pd.DataFrame({
            "daily_return": daily_pnl,
            "daily_friction": daily_friction,
            "cumulative_return": np.cumprod(1.0 + daily_pnl) - 1.0
        }, index=dates)

        return res_df
