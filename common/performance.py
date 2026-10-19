"""
Performance Analytics and Econometric Factor Benchmarking Module
Calculates risk-adjusted returns (Sharpe, Sortino, Calmar, Max Drawdown)
and conducts CAPM and Fama-French 3-Factor econometric regressions.
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple
import statsmodels.api as sm
import pandas_datareader.data as web
import logging

logger = logging.getLogger(__name__)

class PerformanceEvaluator:
    def __init__(self, risk_free_rate_annual: float = 0.04):
        self.rf_annual = risk_free_rate_annual
        self.rf_daily = (1.0 + self.rf_annual) ** (1.0 / 252.0) - 1.0

    @staticmethod
    def calculate_drawdown_series(equity_curve: pd.Series) -> Tuple[pd.Series, float, int]:
        """
        Calculates drawdown time series, maximum drawdown (MDD), and maximum drawdown duration.
        """
        peak = equity_curve.cummax()
        drawdown = (equity_curve - peak) / peak
        max_dd = float(drawdown.min())

        # Drawdown duration in days
        end_idx = np.argmin(drawdown.values)
        peak_idx = np.argmax(equity_curve.values[:end_idx + 1])
        dd_duration = int(end_idx - peak_idx)

        return drawdown, max_dd, dd_duration

    def evaluate_returns(
        self,
        strategy_returns: pd.Series,
        equity_curve: pd.Series,
        benchmark_returns: Optional[pd.Series] = None
    ) -> Dict[str, Any]:
        """
        Computes standard quantitative portfolio metrics.
        """
        clean_ret = strategy_returns.dropna()
        T = len(clean_ret)
        if T < 5:
            return {}

        total_ret = float((equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1.0)
        years = max(T / 252.0, 1e-4)
        cagr = float((1.0 + total_ret) ** (1.0 / years) - 1.0) if total_ret > -1.0 else -1.0

        ann_vol = float(clean_ret.std() * np.sqrt(252.0))
        excess_daily_ret = clean_ret - self.rf_daily
        sharpe = float(np.sqrt(252.0) * excess_daily_ret.mean() / (clean_ret.std() + 1e-8))

        # Downside deviation for Sortino
        downside_ret = clean_ret[clean_ret < 0]
        downside_std = float(downside_ret.std() * np.sqrt(252.0)) if len(downside_ret) > 1 else 1e-8
        sortino = float(np.sqrt(252.0) * excess_daily_ret.mean() / (downside_std + 1e-8))

        # Drawdown and Drawdown Patterns (Slide 2 requirement)
        drawdown, max_dd, dd_duration = self.calculate_drawdown_series(equity_curve)
        calmar = float(cagr / abs(max_dd)) if abs(max_dd) > 1e-6 else np.nan

        # Count drawdown patterns (distinct episodes where drawdown < -0.001)
        in_drawdown = drawdown < -0.001
        # Count rising edges where in_drawdown switches from False to True
        drawdown_episodes = int((in_drawdown & (~in_drawdown.shift(1).fillna(False))).sum())

        metrics = {
            "Annual Return (%)": cagr * 100.0,
            "Total Return (%)": total_ret * 100.0,
            "Sharpe Ratio": sharpe,
            "Max Drawdown (%)": max_dd * 100.0,
            "Annual Volatility (%)": ann_vol * 100.0,
            "Drawdown Patterns (Count)": drawdown_episodes,
            "Max Drawdown Duration (Days)": dd_duration,
            "Sortino Ratio": sortino,
            "Calmar Ratio": calmar,
            "Daily Win Rate (%)": float((clean_ret > 0).mean() * 100.0),
            "Trading Days": T
        }

        # Benchmark Comparison (CAPM Alpha & Beta)
        if benchmark_returns is not None:
            common_idx = clean_ret.index.intersection(benchmark_returns.dropna().index)
            if len(common_idx) > 20:
                y = clean_ret.loc[common_idx] - self.rf_daily
                x = benchmark_returns.loc[common_idx] - self.rf_daily

                X_mat = sm.add_constant(x)
                capm_model = sm.OLS(y, X_mat).fit()

                alpha_ann = float(capm_model.params.iloc[0] * 252.0)
                alpha_pval = float(capm_model.pvalues.iloc[0])
                beta_mkt = float(capm_model.params.iloc[1])
                beta_pval = float(capm_model.pvalues.iloc[1])
                r2 = float(capm_model.rsquared)

                metrics.update({
                    "CAPM Alpha (Ann %)": alpha_ann * 100.0,
                    "Alpha t-stat": float(capm_model.tvalues.iloc[0]),
                    "Alpha p-value": alpha_pval,
                    "Market Beta": beta_mkt,
                    "Beta t-stat": float(capm_model.tvalues.iloc[1]),
                    "CAPM R-squared": r2
                })

        return metrics

    def run_fama_french_regression(
        self,
        strategy_returns: pd.Series,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Runs Fama-French 3-Factor Econometric Regression:
        (R_p - R_f) = alpha + beta_mkt * (R_m - R_f) + beta_smb * SMB + beta_hml * HML + eps
        """
        try:
            cache_file = os.path.join("data", "cache", "fama_french_3factor_daily.csv")
            if os.path.exists(cache_file):
                logger.info(f"Loading Fama-French 3-Factor data from local cache: {cache_file}")
                ff_factors = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            else:
                logger.info("Fetching Fama-French 3-Factor data from Dartmouth / Kenneth French library...")
                ff_factors = web.DataReader(
                    "F-F_Research_Data_Factors_daily",
                    "famafrench",
                    start=start_date,
                    end=end_date
                )[0] / 100.0  # Convert percentage to decimal

                if hasattr(ff_factors.index, "to_timestamp"):
                    ff_factors.index = ff_factors.index.to_timestamp()

                # Save to local cache for offline reproducibility
                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                ff_factors.to_csv(cache_file)
                logger.info(f"Cached Fama-French 3-Factor data to {cache_file}")

            # Align indices
            common_idx = strategy_returns.index.intersection(ff_factors.index)
            if len(common_idx) < 30:
                return {"error": "Insufficient overlapping dates for Fama-French regression."}

            strat_ret = strategy_returns.loc[common_idx]
            ff_sub = ff_factors.loc[common_idx]

            excess_ret = strat_ret - ff_sub["RF"]
            X = sm.add_constant(ff_sub[["Mkt-RF", "SMB", "HML"]])

            model = sm.OLS(excess_ret, X).fit()

            results = {
                "ff_alpha_annualized": float(model.params["const"] * 252.0),
                "ff_alpha_tstat": float(model.tvalues["const"]),
                "ff_alpha_pvalue": float(model.pvalues["const"]),
                "beta_mkt": float(model.params["Mkt-RF"]),
                "beta_mkt_pvalue": float(model.pvalues["Mkt-RF"]),
                "beta_smb": float(model.params["SMB"]),
                "beta_smb_pvalue": float(model.pvalues["SMB"]),
                "beta_hml": float(model.params["HML"]),
                "beta_hml_pvalue": float(model.pvalues["HML"]),
                "ff_r_squared": float(model.rsquared),
                "summary_text": str(model.summary())
            }
            return results
        except Exception as e:
            logger.warning(f"Could not complete Fama-French regression: {e}")
            return {"error": str(e)}

    def evaluate_trades(self, trades_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Computes trade-level performance statistics.
        """
        if trades_df.empty:
            return {"Total Trades": 0}

        pnl_col = "net_pnl" if "net_pnl" in trades_df.columns else "pnl"
        pnls = trades_df[pnl_col]
        winning_trades = pnls[pnls > 0]
        losing_trades = pnls[pnls < 0]

        total_trades = len(trades_df)
        win_rate = (len(winning_trades) / total_trades) * 100.0 if total_trades > 0 else 0.0

        gross_profit = winning_trades.sum()
        gross_loss = abs(losing_trades.sum())
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.inf

        avg_trade_pnl = float(pnls.mean())
        avg_trade_ret = float(trades_df["return_pct"].mean())
        avg_holding_days = float(trades_df["holding_days"].mean())

        exit_reasons = trades_df["exit_reason"].value_counts().to_dict()

        return {
            "Total Trades": total_trades,
            "Win Rate (%)": win_rate,
            "Profit per Trade ($)": avg_trade_pnl,
            "Profit Factor": profit_factor,
            "Gross Profit ($)": float(gross_profit),
            "Gross Loss ($)": float(gross_loss),
            "Average Trade Return (%)": avg_trade_ret,
            "Average Holding Period (Days)": avg_holding_days,
            "Exit Reason Breakdown": exit_reasons
        }
