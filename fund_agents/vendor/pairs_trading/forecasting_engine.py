"""
Automated Live Strategy Update and Multi-Horizon Spread Forecasting Engine
FE5209 Financial Econometrics Project
Fulfills Group Project Slide 1 Mandate:
"Each group needs to work on models and methods that can automatically update
 the trading strategy including the forecasting of the portfolio."
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
import logging

from .kalman_filter import KalmanPairsFilter
from .ou_process import OUModel

logger = logging.getLogger(__name__)

class ForecastingEngine:
    def __init__(
        self,
        entry_z: float = 1.25,
        exit_z: float = 0.10,
        stop_loss_z: float = 3.50,
        kalman_q: float = 1e-5,
        kalman_r: float = 1e-3
    ):
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.stop_loss_z = stop_loss_z
        self.kalman_q = kalman_q
        self.kalman_r = kalman_r

    def update_pair_state_and_forecast(
        self,
        p1_series: pd.Series,
        p2_series: pd.Series,
        pair_name: str,
        horizons: List[int] = [1, 2, 3, 5, 10],
        current_position: int = 0
    ) -> Dict[str, Any]:
        """
        Updates the Kalman filter online to current day t, calibrates the Ornstein-Uhlenbeck
        mean-reversion process, forecasts spread trajectory over h-steps ahead with 95% confidence
        prediction intervals, and generates tomorrow's actionable trading signal.
        """
        # Ensure alignment
        common_idx = p1_series.dropna().index.intersection(p2_series.dropna().index).sort_values()
        s1 = p1_series.loc[common_idx]
        s2 = p2_series.loc[common_idx]

        log_p1 = np.log(s1)
        log_p2 = np.log(s2)

        # 1. Run Online Kalman Filter
        kf = KalmanPairsFilter(
            q_intercept=self.kalman_q,
            q_slope=self.kalman_q,
            r_meas=self.kalman_r
        )
        kalman_df = kf.run_filter(log_p1, log_p2)

        latest_date = kalman_df.index[-1]
        latest_row = kalman_df.iloc[-1]

        alpha_t = float(latest_row["alpha"])
        beta_t = float(latest_row["beta"])
        spread_t = float(latest_row["spread"])
        std_t = float(latest_row["spread_std"])
        z_t = float(latest_row["z_score"])
        price_1 = float(s1.iloc[-1])
        price_2 = float(s2.iloc[-1])

        # 2. Fit Continuous-Time Ornstein-Uhlenbeck Process over recent rolling history (e.g. 252 days)
        lookback = min(len(kalman_df), 252)
        recent_spreads = kalman_df["spread"].iloc[-lookback:]
        ou_model = OUModel(dt=1.0)
        ou_params = ou_model.fit_ols(recent_spreads)

        theta = ou_params["theta"]
        mu = ou_params["mu"]
        sigma = ou_params["sigma"]
        half_life = ou_params["half_life"]

        # 3. Compute Multi-Horizon Forecasts: E[S_{t+h} | S_t] & Var(S_{t+h} | S_t)
        # E[S_{t+h}] = mu + (S_t - mu) * exp(-theta * h)
        # Var(S_{t+h}) = (sigma^2 / (2*theta)) * (1 - exp(-2*theta * h))
        forecasts = []
        for h in horizons:
            decay = np.exp(-theta * h)
            e_spread = mu + (spread_t - mu) * decay
            if theta > 1e-6:
                var_spread = (sigma**2 / (2.0 * theta)) * (1.0 - np.exp(-2.0 * theta * h))
            else:
                var_spread = (sigma**2) * h
            se_spread = np.sqrt(max(var_spread, 1e-8))

            forecast_z = (e_spread - alpha_t) / (std_t + 1e-8)
            lower_95 = e_spread - 1.96 * se_spread
            upper_95 = e_spread + 1.96 * se_spread

            forecasts.append({
                "horizon_days": h,
                "expected_spread": e_spread,
                "expected_z": forecast_z,
                "se_spread": se_spread,
                "lower_95": lower_95,
                "upper_95": upper_95
            })

        forecast_df = pd.DataFrame(forecasts)

        # 4. Generate Tomorrow's Actionable Signal
        signal = "HOLD / NEUTRAL"
        target_pos = current_position
        rationale = "Spread within normal equilibrium bounds."

        if current_position == 0:
            if z_t <= -self.entry_z:
                signal = "ENTRY LONG SPREAD"
                target_pos = 1
                rationale = f"Spread undervaluation Z={z_t:.2f} <= -{self.entry_z:.2f}. Buy {s1.name}, Short {s2.name}."
            elif z_t >= self.entry_z:
                signal = "ENTRY SHORT SPREAD"
                target_pos = -1
                rationale = f"Spread overvaluation Z={z_t:.2f} >= +{self.entry_z:.2f}. Short {s1.name}, Buy {s2.name}."
            else:
                signal = "STAY FLAT"
                target_pos = 0
                rationale = f"Spread Z={z_t:.2f} within [{-self.entry_z:.2f}, +{self.entry_z:.2f}]. No trade."
        elif current_position == 1:
            # Long Spread
            if z_t >= -self.exit_z:
                signal = "EXIT / TAKE PROFIT"
                target_pos = 0
                rationale = f"Spread mean-reverted to Z={z_t:.2f} >= -{self.exit_z:.2f}. Close long position."
            elif z_t <= -self.stop_loss_z:
                signal = "STOP LOSS CIRCUIT BREAKER"
                target_pos = 0
                rationale = f"Extreme divergence Z={z_t:.2f} <= -{self.stop_loss_z:.2f}. Cut position immediately."
            else:
                signal = "HOLD LONG SPREAD"
                target_pos = 1
                rationale = f"Holding Long Spread: Current Z={z_t:.2f}, targeting {-self.exit_z:.2f}."
        elif current_position == -1:
            # Short Spread
            if z_t <= self.exit_z:
                signal = "EXIT / TAKE PROFIT"
                target_pos = 0
                rationale = f"Spread mean-reverted to Z={z_t:.2f} <= +{self.exit_z:.2f}. Close short position."
            elif z_t >= self.stop_loss_z:
                signal = "STOP LOSS CIRCUIT BREAKER"
                target_pos = 0
                rationale = f"Extreme divergence Z={z_t:.2f} >= +{self.stop_loss_z:.2f}. Cut position immediately."
            else:
                signal = "HOLD SHORT SPREAD"
                target_pos = -1
                rationale = f"Holding Short Spread: Current Z={z_t:.2f}, targeting +{self.exit_z:.2f}."

        # Compute dynamic portfolio target weights
        scale = 1.0 + abs(beta_t)
        weight_1 = target_pos * (1.0 / scale)
        weight_2 = -target_pos * (abs(beta_t) / scale)

        # Expected days to mean-reversion target
        if abs(z_t) > self.exit_z and theta > 1e-4:
            exp_days_to_reversion = float((1.0 / theta) * np.log(max(abs(z_t) / self.exit_z, 1.01)))
        else:
            exp_days_to_reversion = 0.0

        return {
            "pair": pair_name,
            "latest_date": str(latest_date.date()),
            "price_1": price_1,
            "price_2": price_2,
            "alpha_kalman": alpha_t,
            "beta_kalman": beta_t,
            "spread_t": spread_t,
            "std_t": std_t,
            "z_score": z_t,
            "ou_theta": theta,
            "ou_half_life": half_life,
            "exp_days_to_reversion": exp_days_to_reversion,
            "signal": signal,
            "current_position": current_position,
            "target_position": target_pos,
            "target_weight_1": weight_1,
            "target_weight_2": weight_2,
            "rationale": rationale,
            "forecast_df": forecast_df,
            "kalman_history": kalman_df
        }

    def update_portfolio(
        self,
        prices: pd.DataFrame,
        portfolio_pairs: List[Tuple[str, str]],
        current_positions: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """
        Runs automated state update and multi-horizon forecasting across all portfolio pairs.
        """
        if current_positions is None:
            current_positions = {f"{a}-{b}": 0 for a, b in portfolio_pairs}

        pair_updates = []
        forecast_trajectories = {}

        for a1, a2 in portfolio_pairs:
            pair_name = f"{a1}-{a2}"
            if a1 not in prices.columns or a2 not in prices.columns:
                logger.warning(f"Ticker {a1} or {a2} missing from prices dataframe. Skipping.")
                continue

            pos = current_positions.get(pair_name, 0)
            update_res = self.update_pair_state_and_forecast(
                p1_series=prices[a1],
                p2_series=prices[a2],
                pair_name=pair_name,
                current_position=pos
            )

            pair_updates.append({
                "Pair": pair_name,
                "Latest Date": update_res["latest_date"],
                "Price 1": f"${update_res['price_1']:,.2f}",
                "Price 2": f"${update_res['price_2']:,.2f}",
                "Hedge Ratio Beta": f"{update_res['beta_kalman']:.3f}",
                "Current Z-Score": f"{update_res['z_score']:.2f}",
                "OU Half-Life": f"{update_res['ou_half_life']:.1f} d",
                "Exp Days to Target": f"{update_res['exp_days_to_reversion']:.1f} d",
                "Action Signal": update_res["signal"],
                "Target W1": f"{update_res['target_weight_1']*100:+.1f}%",
                "Target W2": f"{update_res['target_weight_2']*100:+.1f}%",
                "Rationale": update_res["rationale"]
            })

            forecast_trajectories[pair_name] = update_res["forecast_df"]

        summary_df = pd.DataFrame(pair_updates)
        return {
            "summary_df": summary_df,
            "forecast_trajectories": forecast_trajectories
        }
