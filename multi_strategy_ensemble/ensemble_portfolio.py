"""
Multi-Strategy Portfolio & Dynamic Regime Router
Sourced solely from 'AI Quantitative Trading: From Zero to One':
- Lesson 05.3: Multi-Strategy Portfolios (Equal Weight, Risk Parity)
- Lesson 12: Regime-Based Strategy Routing
- Lesson 15 & 16: Risk Exposure & Maximum Drawdown Protection
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple

class EnsemblePortfolioEngine:
    def __init__(
        self,
        rf_annual: float = 0.04,
        initial_capital: float = 100_000.0
    ):
        self.rf_annual = rf_annual
        self.rf_daily = (1.0 + rf_annual) ** (1.0 / 252.0) - 1.0
        self.initial_capital = initial_capital

    def evaluate_returns(self, daily_returns: pd.Series, name: str = "Strategy") -> Dict[str, Any]:
        """
        Computes standard quantitative metrics (Annual Return, Volatility, Sharpe, MDD, Calmar).
        """
        clean_ret = daily_returns.dropna()
        n = len(clean_ret)
        if n == 0:
            return {}

        total_ret = float(np.prod(1.0 + clean_ret.values) - 1.0)
        ann_ret = float((1.0 + total_ret) ** (252.0 / n) - 1.0)
        ann_vol = float(clean_ret.std() * np.sqrt(252.0))

        # Sharpe excess over annual risk-free rate
        excess_ret = clean_ret - self.rf_daily
        sharpe = float(np.sqrt(252.0) * excess_ret.mean() / (clean_ret.std() + 1e-8))

        # Drawdown calculation
        equity = (1.0 + clean_ret).cumprod()
        peaks = equity.cummax()
        drawdown = (equity - peaks) / peaks
        max_dd = float(drawdown.min())

        calmar = float(ann_ret / abs(max_dd)) if abs(max_dd) > 1e-4 else 0.0

        pos_days = (clean_ret > 0).sum()
        win_rate = float(pos_days / (clean_ret != 0).sum() * 100.0) if (clean_ret != 0).sum() > 0 else 0.0

        # Profit factor
        gross_gains = clean_ret[clean_ret > 0].sum()
        gross_losses = abs(clean_ret[clean_ret < 0].sum())
        profit_factor = float(gross_gains / gross_losses) if gross_losses > 0 else float("inf")

        return {
            "Strategy": name,
            "Total Return (%)": total_ret * 100.0,
            "Annual Return (%)": ann_ret * 100.0,
            "Annual Volatility (%)": ann_vol * 100.0,
            "Sharpe Ratio": sharpe,
            "Max Drawdown (%)": max_dd * 100.0,
            "Calmar Ratio": calmar,
            "Daily Win Rate (%)": win_rate,
            "Profit Factor": profit_factor
        }

    def combine_portfolios(
        self,
        ret_trend: pd.Series,
        ret_momentum: pd.Series,
        ret_reversion: pd.Series,
        regimes_df: pd.DataFrame
    ) -> Dict[str, pd.DataFrame]:
        """
        Constructs and compares:
        1. Standalone Trend Following
        2. Standalone Momentum
        3. Standalone Mean Reversion
        4. Static Equal Weight (1/3 each, Lesson 5.3 Method 1)
        5. Static Risk Parity (Inverse Volatility, Lesson 5.3 Method 2)
        6. Dynamic Regime-Routed Adaptive Ensemble (Lesson 12 Router)
        """
        common_idx = ret_trend.index.intersection(ret_momentum.index).intersection(ret_reversion.index).intersection(regimes_df.index)
        dates = common_idx.sort_values()

        r_t = ret_trend.loc[dates]
        r_m = ret_momentum.loc[dates]
        r_r = ret_reversion.loc[dates]
        reg_df = regimes_df.loc[dates]

        # 1. Static Equal Weight (33.3% Trend, 33.3% Momentum, 33.3% Reversion)
        ret_equal = (r_t + r_m + r_r) / 3.0

        # 2. Static Risk Parity (Lesson 5.3 Method 2)
        # Allocate inversely proportional to realized strategy volatility
        vol_t = r_t.std() + 1e-6
        vol_m = r_m.std() + 1e-6
        vol_r = r_r.std() + 1e-6

        inv_vols = np.array([1.0 / vol_t, 1.0 / vol_m, 1.0 / vol_r])
        w_rp = inv_vols / inv_vols.sum()
        ret_risk_parity = (w_rp[0] * r_t) + (w_rp[1] * r_m) + (w_rp[2] * r_r)

        # 3. Dynamic Regime-Routed Adaptive Ensemble (Lesson 12)
        # Weights adapt daily according to detected market regime
        w_trend = reg_df["weight_trend"]
        w_mom = reg_df["weight_momentum"]
        w_rev = reg_df["weight_reversion"]
        w_cash = reg_df["weight_cash"]

        # Active strategy return + cash yield on reserve
        ret_regime_routed = (
            (w_trend * r_t) +
            (w_mom * r_m) +
            (w_rev * r_r) +
            (w_cash * self.rf_daily)
        )

        curves_df = pd.DataFrame({
            "Trend_Following": (1.0 + r_t).cumprod(),
            "Momentum": (1.0 + r_m).cumprod(),
            "Mean_Reversion": (1.0 + r_r).cumprod(),
            "Equal_Weight_1_3": (1.0 + ret_equal).cumprod(),
            "Risk_Parity": (1.0 + ret_risk_parity).cumprod(),
            "Regime_Routed_Ensemble": (1.0 + ret_regime_routed).cumprod()
        }, index=dates)

        returns_df = pd.DataFrame({
            "Trend_Following": r_t,
            "Momentum": r_m,
            "Mean_Reversion": r_r,
            "Equal_Weight_1_3": ret_equal,
            "Risk_Parity": ret_risk_parity,
            "Regime_Routed_Ensemble": ret_regime_routed
        }, index=dates)

        return {
            "curves": curves_df,
            "returns": returns_df,
            "regimes": reg_df
        }
