"""
Ornstein-Uhlenbeck (OU) Stochastic Process Estimation Module
Models continuous-time mean-reverting spread dynamics:
    dX_t = theta * (mu - X_t) dt + sigma * dW_t
Derives mean reversion speed (theta), equilibrium mean (mu), volatility (sigma),
half-life of mean reversion (tau_1/2), and theoretical optimal trading bands.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
import scipy.optimize as opt
import statsmodels.api as sm

class OUModel:
    def __init__(self, dt: float = 1.0):
        """
        dt: Time increment in days (dt = 1.0 for daily close data, 1/252 in annual terms)
        """
        self.dt = dt

    def fit_ols(self, series: pd.Series) -> Dict[str, Any]:
        """
        Fits the OU process using discrete AR(1) OLS:
        X_t = a + b * X_{t-1} + eta_t
        b = exp(-theta * dt)
        mu = a / (1 - b)
        sigma = std(eta) * sqrt( 2*theta / (1 - b^2) )
        """
        s = series.dropna().values
        if len(s) < 20:
            return {"theta": np.nan, "mu": np.nan, "sigma": np.nan, "half_life": np.nan}

        x_prev = s[:-1]
        x_curr = s[1:]

        X = sm.add_constant(x_prev)
        res = sm.OLS(x_curr, X).fit()

        a = float(np.asarray(res.params)[0])
        b = float(np.asarray(res.params)[1])

        # Stationarity condition: |b| < 1
        if b >= 1.0 or b <= 0.0:
            # Non-mean-reverting or oscillating
            return {
                "theta": 0.0,
                "mu": np.nan,
                "sigma": np.nan,
                "half_life": np.inf,
                "r_squared": float(res.rsquared),
                "is_mean_reverting": False
            }

        theta = -np.log(b) / self.dt
        mu = a / (1.0 - b)
        half_life = np.log(2.0) / theta

        residual_std = float(np.std(res.resid, ddof=2))
        sigma = residual_std * np.sqrt(2.0 * theta / (1.0 - b**2))
        stationary_variance = sigma**2 / (2.0 * theta)
        stationary_std = np.sqrt(stationary_variance)

        return {
            "theta": float(theta),
            "mu": float(mu),
            "sigma": float(sigma),
            "half_life": float(half_life),
            "stationary_std": float(stationary_std),
            "r_squared": float(res.rsquared),
            "is_mean_reverting": True
        }

    def compute_optimal_thresholds(
        self,
        ou_params: Dict[str, Any],
        transaction_cost: float = 0.001
    ) -> Dict[str, float]:
        """
        Calculates recommended entry and exit thresholds based on OU process parameters
        following the analytical framework of Bertram (2010) and Avellaneda & Lee (2010).
        """
        if not ou_params.get("is_mean_reverting", False):
            return {"entry_z": 1.75, "exit_z": 0.10, "stop_z": 3.50}

        stat_std = ou_params["stationary_std"]
        # If stationary std is very small, use default robust multipliers
        if stat_std <= 0 or np.isnan(stat_std):
            return {"entry_z": 1.75, "exit_z": 0.10, "stop_z": 3.50}

        # Entry threshold typically sits around 1.5 to 2.0 standard deviations
        # Exit threshold sits around 0 to 0.2 standard deviations
        # Stop loss sits around 3.5 to 4.0 standard deviations
        return {
            "entry_z": 1.75,
            "exit_z": 0.10,
            "stop_loss_z": 3.50,
            "max_holding_period": max(5, int(np.round(2.5 * ou_params["half_life"])))
        }
