"""
Tearsheet and Visualization Module for Econometric Pairs Trading Strategy
Generates publication-quality figures:
1. Cumulative Performance & Drawdown vs SPY
2. Dynamic Kalman Filter Hedge Ratio Beta_t vs Static OLS
3. Spread Z-Score & Trade Execution Markers
4. Rolling Risk & Monthly Return Heatmap
"""
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from typing import Dict, Any, Optional

# Set sleek academic / quantitative style
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams["font.sans-serif"] = "DejaVu Sans"
plt.rcParams["axes.edgecolor"] = "#cccccc"
plt.rcParams["axes.linewidth"] = 0.8

class TearSheetGenerator:
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_full_tearsheet(
        self,
        strategy_df: pd.DataFrame,
        trades_df: pd.DataFrame,
        kalman_df: pd.DataFrame,
        benchmark_series: pd.Series,
        pair_info: Dict[str, Any],
        ou_params: Dict[str, Any],
        metrics: Dict[str, Any],
        prefix: str = "oos"
    ) -> Dict[str, str]:
        """
        Creates all tear-sheet charts and saves them to outputs/.
        Returns a dictionary of generated image paths.
        """
        saved_paths = {}

        # 1. Performance & Underwater Drawdown Chart
        p1_path = os.path.join(self.output_dir, f"{prefix}_performance_drawdown.png")
        self._plot_performance_and_drawdown(
            strategy_df=strategy_df,
            benchmark_series=benchmark_series,
            pair_name=pair_info["pair"],
            save_path=p1_path
        )
        saved_paths["performance_drawdown"] = p1_path

        # 2. Kalman Filter Dynamic Beta vs Static OLS
        p2_path = os.path.join(self.output_dir, f"{prefix}_kalman_dynamics.png")
        self._plot_kalman_dynamics(
            kalman_df=kalman_df,
            static_beta=pair_info.get("beta_ols", 1.0),
            pair_name=pair_info["pair"],
            save_path=p2_path
        )
        saved_paths["kalman_dynamics"] = p2_path

        # 3. Z-Score Signals and Trade Entry/Exit Markers
        p3_path = os.path.join(self.output_dir, f"{prefix}_zscore_signals.png")
        self._plot_signals_and_trades(
            kalman_df=kalman_df,
            trades_df=trades_df,
            entry_z=1.75,
            exit_z=0.10,
            stop_z=3.50,
            pair_name=pair_info["pair"],
            save_path=p3_path
        )
        saved_paths["zscore_signals"] = p3_path

        # 4. Rolling Risk Metrics & Return Distribution
        p4_path = os.path.join(self.output_dir, f"{prefix}_rolling_risk.png")
        self._plot_rolling_risk_and_dist(
            strategy_df=strategy_df,
            benchmark_series=benchmark_series,
            pair_name=pair_info["pair"],
            save_path=p4_path
        )
        saved_paths["rolling_risk"] = p4_path

        return saved_paths

    def _plot_performance_and_drawdown(
        self,
        strategy_df: pd.DataFrame,
        benchmark_series: pd.Series,
        pair_name: str,
        save_path: str
    ):
        dates = strategy_df.index
        strat_equity = strategy_df["equity"]
        strat_cum_ret = (strat_equity / strat_equity.iloc[0]) - 1.0

        # Align benchmark
        common_idx = dates.intersection(benchmark_series.dropna().index)
        bench_sub = benchmark_series.loc[common_idx]
        bench_cum_ret = (bench_sub / bench_sub.iloc[0]) - 1.0

        peak = strat_equity.cummax()
        drawdown = (strat_equity - peak) / peak

        bench_peak = bench_sub.cummax()
        bench_dd = (bench_sub - bench_peak) / bench_peak

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [2.5, 1.2]})

        # Top panel: Cumulative Return
        ax1.plot(strat_cum_ret.index, strat_cum_ret * 100.0, label=f"Strategy: {pair_name} (Kalman Stat-Arb)", color="#1f77b4", linewidth=2.2)
        ax1.plot(bench_cum_ret.index, bench_cum_ret * 100.0, label="Benchmark: S&P 500 (SPY)", color="#7f7f7f", linestyle="--", linewidth=1.8)
        ax1.set_title(f"Cumulative Performance vs Benchmark: {pair_name}", fontsize=14, fontweight="bold", pad=12)
        ax1.set_ylabel("Cumulative Return (%)", fontsize=11)
        ax1.legend(loc="upper left", frameon=True, facecolor="white", framealpha=0.9)
        ax1.axhline(0, color="black", linestyle=":", alpha=0.6)

        # Bottom panel: Underwater Drawdown
        ax2.fill_between(drawdown.index, drawdown * 100.0, 0, color="#d62728", alpha=0.35, label="Strategy Drawdown")
        ax2.plot(drawdown.index, drawdown * 100.0, color="#d62728", linewidth=1.2)
        ax2.plot(bench_dd.index, bench_dd * 100.0, color="#7f7f7f", linestyle="--", linewidth=1.0, label="SPY Drawdown")
        ax2.set_ylabel("Drawdown (%)", fontsize=11)
        ax2.set_xlabel("Date", fontsize=11)
        ax2.legend(loc="lower left", frameon=True, facecolor="white", framealpha=0.9)
        ax2.set_ylim([min(drawdown.min() * 100.0 * 1.2, -10), 2])

        plt.tight_layout()
        plt.savefig(save_path, dpi=300)
        plt.close()

    def _plot_kalman_dynamics(
        self,
        kalman_df: pd.DataFrame,
        static_beta: float,
        pair_name: str,
        save_path: str
    ):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

        # Hedge ratio beta_t
        ax1.plot(kalman_df.index, kalman_df["beta"], label=r"Kalman Dynamic Hedge Ratio $\beta_t$", color="#2ca02c", linewidth=2.0)
        ax1.axhline(static_beta, color="#d62728", linestyle="--", label=f"Static In-Sample OLS Beta ({static_beta:.3f})", linewidth=1.8)
        ax1.set_title(f"Dynamic Kalman Filter State Evolution: {pair_name}", fontsize=14, fontweight="bold")
        ax1.set_ylabel(r"Hedge Ratio ($\beta$)", fontsize=11)
        ax1.legend(loc="best", frameon=True, facecolor="white")

        # Dynamic conditional spread standard deviation sqrt(F_t)
        ax2.plot(kalman_df.index, kalman_df["spread_std"] * 100.0, color="#9467bd", linewidth=1.8, label=r"Dynamic Conditional Volatility $\sqrt{F_t}$ (%)")
        ax2.set_ylabel("Conditional Spread Vol (%)", fontsize=11)
        ax2.set_xlabel("Date", fontsize=11)
        ax2.legend(loc="upper right", frameon=True, facecolor="white")

        plt.tight_layout()
        plt.savefig(save_path, dpi=300)
        plt.close()

    def _plot_signals_and_trades(
        self,
        kalman_df: pd.DataFrame,
        trades_df: pd.DataFrame,
        entry_z: float,
        exit_z: float,
        stop_z: float,
        pair_name: str,
        save_path: str
    ):
        fig, ax = plt.subplots(figsize=(13, 6))

        z_series = kalman_df["z_score"]
        ax.plot(z_series.index, z_series, color="#1f77b4", linewidth=1.5, label="Dynamic Z-Score ($Z_t$)")

        # Threshold bands
        ax.axhline(entry_z, color="#e377c2", linestyle="--", label=f"+Entry ({entry_z:.2f})")
        ax.axhline(-entry_z, color="#e377c2", linestyle="--", label=f"-Entry (-{entry_z:.2f})")
        ax.axhline(exit_z, color="#7f7f7f", linestyle=":", label=f"Exit Target (+/- {exit_z:.2f})")
        ax.axhline(-exit_z, color="#7f7f7f", linestyle=":")
        ax.axhline(stop_z, color="#d62728", linestyle="-.", label=f"+/- Stop Loss ({stop_z:.2f})")
        ax.axhline(-stop_z, color="#d62728", linestyle="-.")
        ax.axhline(0, color="black", linewidth=0.8, alpha=0.7)

        # Plot trade markers if any
        if not trades_df.empty:
            for _, tr in trades_df.iterrows():
                e_date = tr["entry_date"]
                x_date = tr["exit_date"]
                direction = tr["direction"]
                e_z = tr["entry_z"]
                x_z = tr["exit_z"]

                marker = "^" if direction == "LONG SPREAD" else "v"
                m_color = "green" if direction == "LONG SPREAD" else "orange"
                ax.scatter(e_date, e_z, color=m_color, marker=marker, s=80, zorder=5)
                ax.scatter(x_date, x_z, color="black", marker="x", s=60, zorder=5)

        ax.set_title(f"Kalman Z-Score Signal & Trade Executions: {pair_name}", fontsize=14, fontweight="bold")
        ax.set_ylabel("Standardized Z-Score", fontsize=11)
        ax.set_xlabel("Date", fontsize=11)
        ax.legend(loc="upper right", frameon=True, facecolor="white", framealpha=0.9, ncol=2)

        plt.tight_layout()
        plt.savefig(save_path, dpi=300)
        plt.close()

    def _plot_rolling_risk_and_dist(
        self,
        strategy_df: pd.DataFrame,
        benchmark_series: pd.Series,
        pair_name: str,
        save_path: str
    ):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        daily_ret = strategy_df["daily_return"].dropna()

        # Left panel: Return Distribution
        sns.histplot(daily_ret * 100.0, kde=True, ax=ax1, color="#1f77b4", bins=30, stat="density")
        ax1.set_title("Strategy Daily Return Distribution (%)", fontsize=12, fontweight="bold")
        ax1.set_xlabel("Daily Return (%)", fontsize=10)
        ax1.set_ylabel("Density", fontsize=10)

        # Right panel: Rolling 60-Day Sharpe Ratio
        rolling_sharpe = (daily_ret.rolling(60).mean() / (daily_ret.rolling(60).std() + 1e-8)) * np.sqrt(252.0)
        ax2.plot(rolling_sharpe.index, rolling_sharpe, color="#ff7f0e", linewidth=1.8, label="Rolling 60D Sharpe")
        ax2.axhline(0, color="black", linestyle="--", alpha=0.6)
        ax2.axhline(1.0, color="green", linestyle=":", alpha=0.6, label="Sharpe = 1.0 Benchmark")
        ax2.set_title("Rolling 60-Day Annualized Sharpe Ratio", fontsize=12, fontweight="bold")
        ax2.set_ylabel("Sharpe Ratio", fontsize=10)
        ax2.set_xlabel("Date", fontsize=10)
        ax2.legend(loc="best", frameon=True, facecolor="white")

        plt.tight_layout()
        plt.savefig(save_path, dpi=300)
        plt.close()
