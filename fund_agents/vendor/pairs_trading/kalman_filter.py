"""
Kalman Filter State-Space Dynamic Hedge Ratio and Spread Estimator
Implements recursive online estimation of time-varying intercept (alpha_t) and hedge ratio (beta_t),
along with innovation error e_t and dynamic conditional volatility sqrt(F_t).
"""
import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any, Optional

class KalmanPairsFilter:
    def __init__(
        self,
        q_intercept: float = 1e-4,
        q_slope: float = 1e-4,
        r_meas: float = 1e-3,
        initial_covariance: float = 1.0
    ):
        """
        State-Space Formulation:
        State vector: theta_t = [alpha_t, beta_t]^T
        State equation: theta_t = theta_{t-1} + w_t,  w_t ~ N(0, Q)
        Observation equation: y_t = [1, x_t] * theta_t + v_t,  v_t ~ N(0, R)
        """
        self.q_intercept = q_intercept
        self.q_slope = q_slope
        self.r_meas = r_meas
        self.initial_covariance = initial_covariance

        # Process noise covariance Q
        self.Q = np.diag([self.q_intercept, self.q_slope])
        # Measurement noise variance R
        self.R = self.r_meas

    def run_filter(
        self,
        y: pd.Series,
        x: pd.Series,
        initial_alpha: Optional[float] = None,
        initial_beta: Optional[float] = None
    ) -> pd.DataFrame:
        """
        Runs the online Kalman Filter sequentially over the series y and x.
        y: Dependent log-price series ln(P_{1,t})
        x: Independent log-price series ln(P_{2,t})

        Returns a DataFrame containing:
        - alpha: dynamic intercept
        - beta: dynamic hedge ratio
        - spread: innovation error e_t = y_t - (alpha_{t|t-1} + beta_{t|t-1} * x_t)
        - spread_var: innovation variance F_t
        - spread_std: conditional volatility sqrt(F_t)
        - z_score: standardized innovation e_t / sqrt(F_t)
        """
        # Ensure common index
        common_idx = y.dropna().index.intersection(x.dropna().index)
        y_vals = y.loc[common_idx].values
        x_vals = x.loc[common_idx].values
        T = len(common_idx)

        # Initial state guess: use first 20 observations OLS or user priors
        if initial_alpha is None or initial_beta is None:
            init_n = min(30, T)
            X_init = np.column_stack([np.ones(init_n), x_vals[:init_n]])
            beta_hat, alpha_hat = np.linalg.lstsq(X_init, y_vals[:init_n], rcond=None)[0][[1, 0]]
        else:
            alpha_hat = initial_alpha
            beta_hat = initial_beta

        # Initialize state theta = [alpha, beta]^T
        theta = np.array([alpha_hat, beta_hat], dtype=float)
        # Initialize error covariance P
        P = np.eye(2, dtype=float) * self.initial_covariance

        # Storage arrays
        alphas = np.zeros(T, dtype=float)
        betas = np.zeros(T, dtype=float)
        spreads = np.zeros(T, dtype=float)
        spread_vars = np.zeros(T, dtype=float)
        z_scores = np.zeros(T, dtype=float)

        I = np.eye(2, dtype=float)

        for t in range(T):
            x_t = x_vals[t]
            y_t = y_vals[t]

            # 1. State Prediction (Random walk assumption: theta_{t|t-1} = theta_{t-1|t-1})
            theta_pred = theta
            P_pred = P + self.Q

            # 2. Measurement Prediction
            H_t = np.array([1.0, x_t])  # 1x2 row vector
            y_pred = np.dot(H_t, theta_pred)

            # 3. Innovation (Spread) & Innovation Variance
            e_t = y_t - y_pred
            # F_t = H_t * P_pred * H_t^T + R
            F_t = float(np.dot(H_t, np.dot(P_pred, H_t)) + self.R)

            # Standardized Z-Score (using conditional standard deviation)
            std_t = np.sqrt(max(F_t, 1e-8))
            z_t = e_t / std_t

            # 4. Kalman Gain
            # K_t = P_pred * H_t^T / F_t
            K_t = np.dot(P_pred, H_t) / F_t  # 2x1 vector

            # 5. State Posterior Update
            theta = theta_pred + K_t * e_t

            # 6. Covariance Posterior Update (Joseph stabilized form: (I - K H) P (I - K H)^T + K R K^T)
            IKH = I - np.outer(K_t, H_t)
            P = np.dot(IKH, np.dot(P_pred, IKH.T)) + np.outer(K_t, K_t) * self.R

            # Store records
            alphas[t] = theta[0]
            betas[t] = theta[1]
            spreads[t] = e_t
            spread_vars[t] = F_t
            z_scores[t] = z_t

        df_out = pd.DataFrame(
            {
                "alpha": alphas,
                "beta": betas,
                "spread": spreads,
                "spread_var": spread_vars,
                "spread_std": np.sqrt(spread_vars),
                "z_score": z_scores
            },
            index=common_idx
        )

        return df_out
