"""
Econometric Pair Selection and Cointegration Screening Module
Implements ADF stationarity tests, Engle-Granger 2-step procedure, Johansen Cointegration test,
and Ornstein-Uhlenbeck half-life filtering to select statistically robust pairs.
"""
import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Any, Optional
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, coint
from statsmodels.tsa.vector_ar.vecm import coint_johansen
import logging

logger = logging.getLogger(__name__)

class PairSelector:
    def __init__(
        self,
        adf_pvalue_threshold: float = 0.05,
        min_correlation: float = 0.70,
        min_half_life: float = 2.0,
        max_half_life: float = 60.0
    ):
        self.adf_pvalue_threshold = adf_pvalue_threshold
        self.min_correlation = min_correlation
        self.min_half_life = min_half_life
        self.max_half_life = max_half_life

    @staticmethod
    def estimate_half_life(spread: pd.Series) -> float:
        """
        Estimates the half-life of mean reversion using an Ornstein-Uhlenbeck (AR(1)) specification:
        delta_S_t = theta * (mu - S_{t-1}) + epsilon_t
                  = alpha + lambda * S_{t-1} + epsilon_t
        where lambda = -(1 - e^{-theta}) approx -theta.
        Half-life = -ln(2) / lambda.
        """
        spread_clean = spread.dropna()
        if len(spread_clean) < 20:
            return np.nan

        lagged = spread_clean.shift(1).dropna()
        delta = (spread_clean - lagged).dropna()
        lagged = lagged.loc[delta.index]

        X = sm.add_constant(lagged.values)
        model = sm.OLS(delta.values, X).fit()

        lambda_coef = float(np.asarray(model.params)[1])

        # If lambda >= 0, the process does not mean-revert (explosive or random walk)
        if lambda_coef >= 0 or np.isnan(lambda_coef):
            return np.inf

        half_life = -np.log(2.0) / lambda_coef
        return float(half_life)

    def test_engle_granger(
        self,
        y: pd.Series,
        x: pd.Series
    ) -> Dict[str, Any]:
        """
        Runs Engle-Granger two-step cointegration test using log prices:
        Step 1: OLS regression ln(Y) = alpha + beta * ln(X) + eps
        Step 2: ADF test on residuals eps using MacKinnon critical values
        """
        log_y = np.log(y)
        log_x = np.log(x)

        # Regress Y on X
        X_mat = sm.add_constant(log_x)
        ols_res = sm.OLS(log_y, X_mat).fit()

        alpha = float(np.asarray(ols_res.params)[0])
        beta = float(np.asarray(ols_res.params)[1])
        r_squared = float(ols_res.rsquared)

        spread = log_y - (alpha + beta * log_x)

        # Engle-Granger test via statsmodels.tsa.stattools.coint (uses MacKinnon critical values)
        score, pvalue, _ = coint(log_y, log_x)

        # Half-life of the OLS spread
        half_life = self.estimate_half_life(spread)

        return {
            "alpha": float(alpha),
            "beta": float(beta),
            "r_squared": float(r_squared),
            "coint_t_stat": float(score),
            "coint_pvalue": float(pvalue),
            "spread_std": float(spread.std()),
            "half_life": float(half_life),
            "spread_series": spread
        }

    def test_johansen(
        self,
        y: pd.Series,
        x: pd.Series,
        det_order: int = 0,
        k_ar_diff: int = 1
    ) -> Dict[str, Any]:
        """
        Runs Johansen Maximum Likelihood Cointegration Test on [log_y, log_x].
        Evaluates Trace statistic and Maximum Eigenvalue statistic against 95% critical value.
        """
        data = np.column_stack([np.log(y.values), np.log(x.values)])
        try:
            joh_res = coint_johansen(data, det_order=det_order, k_ar_diff=k_ar_diff)
            # Rank r=0 test (testing hypothesis of zero cointegrating vectors)
            trace_stat_r0 = joh_res.lr1[0]
            trace_crit_95 = joh_res.cvt[0, 1]  # 95% critical value
            max_eig_stat_r0 = joh_res.lr2[0]
            max_eig_crit_95 = joh_res.cvm[0, 1]

            is_cointegrated_trace = bool(trace_stat_r0 > trace_crit_95)
            is_cointegrated_maxeig = bool(max_eig_stat_r0 > max_eig_crit_95)

            # Cointegrating vector normalized on first variable
            evec = joh_res.evec[:, 0]
            normalized_beta = -evec[1] / evec[0] if evec[0] != 0 else np.nan

            return {
                "trace_stat": float(trace_stat_r0),
                "trace_crit_95": float(trace_crit_95),
                "trace_reject": is_cointegrated_trace,
                "max_eig_stat": float(max_eig_stat_r0),
                "max_eig_crit_95": float(max_eig_crit_95),
                "max_eig_reject": is_cointegrated_maxeig,
                "johansen_beta": float(normalized_beta)
            }
        except Exception as e:
            logger.warning(f"Johansen test failed: {e}")
            return {
                "trace_stat": np.nan,
                "trace_crit_95": np.nan,
                "trace_reject": False,
                "max_eig_stat": np.nan,
                "max_eig_crit_95": np.nan,
                "max_eig_reject": False,
                "johansen_beta": np.nan
            }

    def evaluate_pair(
        self,
        prices: pd.DataFrame,
        asset1: str,
        asset2: str
    ) -> Optional[Dict[str, Any]]:
        """
        Performs full econometric diagnostic tests on a pair in the formation window.
        """
        if asset1 not in prices.columns or asset2 not in prices.columns:
            return None

        p1 = prices[asset1].dropna()
        p2 = prices[asset2].dropna()

        # Common index
        common_idx = p1.index.intersection(p2.index)
        if len(common_idx) < 100:
            return None

        p1 = p1.loc[common_idx]
        p2 = p2.loc[common_idx]

        # 1. Check Return Correlation
        ret1 = np.log(p1 / p1.shift(1)).dropna()
        ret2 = np.log(p2 / p2.shift(1)).dropna()
        corr = float(ret1.corr(ret2))

        # 2. Check Unit Root in Log Prices (should be I(1))
        adf_p1 = adfuller(np.log(p1), maxlag=1)[1]
        adf_p2 = adfuller(np.log(p2), maxlag=1)[1]

        # 3. Engle-Granger Cointegration
        eg_results = self.test_engle_granger(p1, p2)

        # 4. Johansen Cointegration Test
        joh_results = self.test_johansen(p1, p2)

        # Diagnostic qualification flags
        is_stationary_spread = eg_results["coint_pvalue"] < self.adf_pvalue_threshold
        has_adequate_corr = corr >= self.min_correlation
        valid_half_life = self.min_half_life <= eg_results["half_life"] <= self.max_half_life
        johansen_confirmed = joh_results["trace_reject"] or joh_results["max_eig_reject"]

        is_qualified = bool(
            is_stationary_spread and
            has_adequate_corr and
            valid_half_life
        )

        return {
            "pair": f"{asset1}-{asset2}",
            "asset1": asset1,
            "asset2": asset2,
            "correlation": corr,
            "adf_p1_pvalue": adf_p1,
            "adf_p2_pvalue": adf_p2,
            "beta_ols": eg_results["beta"],
            "alpha_ols": eg_results["alpha"],
            "r_squared": eg_results["r_squared"],
            "eg_pvalue": eg_results["coint_pvalue"],
            "eg_t_stat": eg_results["coint_t_stat"],
            "half_life": eg_results["half_life"],
            "johansen_trace_stat": joh_results["trace_stat"],
            "johansen_trace_crit": joh_results["trace_crit_95"],
            "johansen_reject": joh_results["trace_reject"],
            "johansen_beta": joh_results["johansen_beta"],
            "qualified": is_qualified
        }

    def screen_universe(
        self,
        prices: pd.DataFrame,
        candidate_pairs: List[Tuple[str, str]]
    ) -> pd.DataFrame:
        """
        Screens candidate pairs over the in-sample period and returns a ranked summary dataframe.
        """
        results = []
        logger.info(f"Screening {len(candidate_pairs)} candidate pairs for cointegration & mean reversion...")

        for a1, a2 in candidate_pairs:
            res = self.evaluate_pair(prices, a1, a2)
            if res is not None:
                results.append(res)

        df = pd.DataFrame(results)
        if not df.empty:
            # Sort by cointegration p-value ascending, then R-squared descending
            df = df.sort_values(by=["qualified", "eg_pvalue", "r_squared"], ascending=[False, True, False]).reset_index(drop=True)

        logger.info(f"Screening complete. Qualified pairs: {df['qualified'].sum()} / {len(df)}")
        return df
