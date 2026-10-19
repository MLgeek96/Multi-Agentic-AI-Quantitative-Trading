"""
Main Execution Script for Multi-Strategy Ensemble System
Sourced solely from 'AI Quantitative Trading: From Zero to One' (ai-quant-book/manuscript/en):
Runs:
1. Trend Following (Lesson 05.1)
2. Cross-Sectional Momentum (Lessons 05 & 16)
3. Mean Reversion (Lesson 05.2)
4. Equal Weight (Lesson 05.3 Method 1)
5. Risk Parity (Lesson 05.3 Method 2)
6. Dynamic Regime-Routed Adaptive Ensemble (Lesson 12)
Outputs complete comparative performance tearsheets and charts to outputs/.
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from tabulate import tabulate

# Add project root and current folder to sys.path
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_proj_root = os.path.dirname(_cur_dir)
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)
if _cur_dir not in sys.path:
    sys.path.insert(0, _cur_dir)

from multi_strategy_ensemble.config import EnsembleConfig
from multi_strategy_ensemble.regime_detector import RegimeDetector
from multi_strategy_ensemble.trend_strategy import TrendFollowingStrategy
from multi_strategy_ensemble.momentum_strategy import MomentumStrategy
from multi_strategy_ensemble.reversion_strategy import MeanReversionStrategy
from multi_strategy_ensemble.ensemble_portfolio import EnsemblePortfolioEngine

def run_experiment(cfg: EnsembleConfig = None):
    if cfg is None:
        cfg = EnsembleConfig()
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)

    print("=" * 80)
    print(" MULTI-STRATEGY ENSEMBLE SYSTEM: MOMENTUM + TREND + REVERSION + REGIME ROUTER")
    print(" Sourced solely from: https://github.com/waylandzhang/ai-quant-book/tree/main/manuscript/en")
    print("=" * 80)

    # 1. Load cached price data
    print("\n[Step 1] Loading Universe Prices and Benchmark Data...")
    if not os.path.exists(cfg.DATA_CACHE_PRICES):
        raise FileNotFoundError(f"Missing price cache: {cfg.DATA_CACHE_PRICES}")
    if not os.path.exists(cfg.DATA_CACHE_SPY):
        raise FileNotFoundError(f"Missing benchmark cache: {cfg.DATA_CACHE_SPY}")

    all_prices = pd.read_csv(cfg.DATA_CACHE_PRICES, index_col=0, parse_dates=True)
    spy_df = pd.read_csv(cfg.DATA_CACHE_SPY, index_col=0, parse_dates=True)
    bench_series = spy_df["Close"] if "Close" in spy_df.columns else spy_df.iloc[:, 0]

    # Select tickers in universe that are present in prices (Equities Only)
    crypto_tickers = ["BTC-USD", "ETH-USD", "SOL-USD"]
    etf_tickers = ["SPY", "EWS", "GLD", "GDX", "USO", "XLE", "XOP", "XLF", "KRE", "XLK", "QQQ"]
    if cfg.STRATEGY_UNIVERSE == "ALL" or "ALL" in cfg.STRATEGY_UNIVERSE or not cfg.STRATEGY_UNIVERSE:
        valid_tickers = [c for c in all_prices.columns if c not in ["Date", "date", "Unnamed: 0"] and c not in crypto_tickers and c not in etf_tickers and "USD" not in c]
    else:
        valid_tickers = [t for t in cfg.STRATEGY_UNIVERSE if t in all_prices.columns and t not in crypto_tickers and t not in etf_tickers and "USD" not in t]
    print(f"  [+] Active Pure Equities Universe ({len(valid_tickers)} equities across S&P 500, STI, and STOXX 600)")
    universe_prices = all_prices[valid_tickers].dropna(how="all").ffill().bfill()

    # Align universe prices and benchmark series on common datetime index
    common_idx = universe_prices.index.intersection(bench_series.dropna().index).sort_values()
    universe_prices = universe_prices.loc[common_idx]
    bench_series = bench_series.loc[common_idx]

    # 2. Run Regime Detection (Lesson 12)
    print("\n[Step 2] Executing Market Regime Detection (Lesson 12)...")
    detector = RegimeDetector(
        vol_window=cfg.REGIME_VOL_WINDOW,
        return_window=cfg.REGIME_RETURN_WINDOW,
        adx_window=cfg.REGIME_ADX_WINDOW,
        adx_trend_thresh=cfg.ADX_TREND_THRESHOLD,
        adx_ranging_thresh=cfg.ADX_RANGING_THRESHOLD,
        crisis_vol_thresh=cfg.CRISIS_VOL_ANNUAL_THRESHOLD
    )
    regimes_df = detector.detect_regimes(bench_series)
    regimes_counts = regimes_df.loc[cfg.OUT_OF_SAMPLE_START:cfg.END_DATE, "regime"].value_counts()
    print("  [+] Out-of-Sample Regime Distribution:")
    for reg, cnt in regimes_counts.items():
        print(f"      - {reg}: {cnt} trading days ({cnt / len(regimes_df.loc[cfg.OUT_OF_SAMPLE_START:cfg.END_DATE]) * 100:.1f}%)")

    # 3. Run Individual Strategies
    print("\n[Step 3] Running Individual Strategies over Out-of-Sample Period (2023-2024)...")

    # A. Trend Following (Lesson 05.1)
    print("  [>] Executing Trend Following (Dual MA10/MA60 + ADX filter + ATR trailing stops)...")
    trend_model = TrendFollowingStrategy(
        fast_window=cfg.TREND_FAST_MA,
        slow_window=cfg.TREND_SLOW_MA,
        adx_filter_threshold=20.0,
        atr_trailing_mult=cfg.TREND_TRAILING_STOP_ATR_MULT,
        tx_cost_bps=cfg.TRANSACTION_COST_BPS,
        rf_annual=cfg.RISK_FREE_RATE_ANNUAL
    )
    trend_res = trend_model.run_strategy(universe_prices, bench_series)

    # B. Momentum Strategy (Lessons 05 & 16)
    print("  [>] Executing Cross-Sectional Momentum with Sector-Neutral Risk Controls (Lesson 16)...")
    sec_csv = os.path.join(os.path.dirname(cfg.DATA_CACHE_PRICES), "full_universe_sectors.csv")
    sec_map = {}
    if os.path.exists(sec_csv):
        sec_df = pd.read_csv(sec_csv)
        broad_map = {
            'Information Technology': 'Technology', 'Technology': 'Technology',
            'Financials': 'Financials', 'Banks': 'Financials', 'Insurance': 'Financials', 'Financial Services': 'Financials',
            'Health Care': 'Healthcare', 'Personal Care, Drug and Grocery Stores': 'Healthcare',
            'Industrials': 'Industrials', 'Industrial Goods and Services': 'Industrials', 'Construction and Materials': 'Industrials',
            'Consumer Discretionary': 'Consumer_Disc', 'Consumer Products and Services': 'Consumer_Disc', 'Automobiles and Parts': 'Consumer_Disc', 'Retail': 'Consumer_Disc', 'Travel and Leisure': 'Consumer_Disc',
            'Consumer Staples': 'Consumer_Staples', 'Food, Beverage and Tobacco': 'Consumer_Staples',
            'Energy': 'Energy', 'Utilities': 'Utilities', 'Real Estate': 'Real_Estate',
            'Communication Services': 'Communication', 'Telecommunications': 'Communication', 'Media': 'Communication',
            'Materials': 'Materials', 'Basic Resources': 'Materials', 'Chemicals': 'Materials'
        }
        sec_map = {str(r['Ticker']).upper(): broad_map.get(str(r['Sector']), 'Other') for _, r in sec_df.iterrows()}

    momentum_model = MomentumStrategy(
        lookback_days=cfg.MOMENTUM_LOOKBACK_DAYS,
        rebalance_interval=cfg.MOMENTUM_HOLDING_DAYS,
        top_k=cfg.MOMENTUM_TOP_K,
        vol_scale=cfg.MOMENTUM_VOL_SCALE,
        sector_neutral=True if sec_map else False,
        k_per_sector=2,
        sector_mapping=sec_map,
        tx_cost_bps=cfg.TRANSACTION_COST_BPS,
        rf_annual=cfg.RISK_FREE_RATE_ANNUAL
    )
    mom_res = momentum_model.run_strategy(universe_prices)

    # C. Mean Reversion Strategy (Lesson 05.2)
    print("  [>] Executing Mean Reversion (Cointegrated Pairs Spread Reversion)...")
    rev_model = MeanReversionStrategy(
        window=cfg.REVERSION_WINDOW,
        entry_z=cfg.REVERSION_ENTRY_Z,
        exit_z=cfg.REVERSION_EXIT_Z,
        stop_loss_z=cfg.REVERSION_STOP_LOSS_Z,
        tx_cost_bps=cfg.TRANSACTION_COST_BPS,
        rf_annual=cfg.RISK_FREE_RATE_ANNUAL
    )
    rev_res = rev_model.run_strategy(universe_prices)

    # 4. Filter for Out-of-Sample evaluation window
    oos_mask = (trend_res.index >= pd.Timestamp(cfg.OUT_OF_SAMPLE_START)) & (trend_res.index <= pd.Timestamp(cfg.END_DATE))
    r_trend_oos = trend_res.loc[oos_mask, "daily_return"]
    r_mom_oos = mom_res.loc[oos_mask, "daily_return"]
    r_rev_oos = rev_res.loc[oos_mask, "daily_return"]
    reg_oos = regimes_df.loc[oos_mask]
    bench_oos = bench_series.loc[oos_mask]
    r_bench_oos = bench_oos.pct_change().fillna(0.0)

    # 5. Multi-Strategy Portfolio Ensemble (Lesson 05.3 & 12)
    print("\n[Step 4] Combining Multi-Strategy Ensembles (Equal Weight, Risk Parity, Regime Router)...")
    ensemble_engine = EnsemblePortfolioEngine(rf_annual=cfg.RISK_FREE_RATE_ANNUAL)
    combined = ensemble_engine.combine_portfolios(
        ret_trend=r_trend_oos,
        ret_momentum=r_mom_oos,
        ret_reversion=r_rev_oos,
        regimes_df=reg_oos
    )

    returns_df = combined["returns"]
    curves_df = combined["curves"]

    # 6. Performance Evaluation & Comparative Table
    print("\n[Step 5] Computing Rigorous Performance Metrics...")
    eval_list = []
    # Individual strategies
    eval_list.append(ensemble_engine.evaluate_returns(returns_df["Trend_Following"], "Trend Following (L05.1)"))
    eval_list.append(ensemble_engine.evaluate_returns(returns_df["Momentum"], "Momentum L/S (L05 & 16)"))
    eval_list.append(ensemble_engine.evaluate_returns(returns_df["Mean_Reversion"], "Mean Reversion (L05.2)"))
    # Portfolios
    eval_list.append(ensemble_engine.evaluate_returns(returns_df["Equal_Weight_1_3"], "Equal Weight 1/3 (L05.3)"))
    eval_list.append(ensemble_engine.evaluate_returns(returns_df["Risk_Parity"], "Risk Parity Inv-Vol (L05.3)"))
    eval_list.append(ensemble_engine.evaluate_returns(returns_df["Regime_Routed_Ensemble"], "Dynamic Regime Ensemble (L12)"))
    # Benchmark
    eval_list.append(ensemble_engine.evaluate_returns(r_bench_oos, "Benchmark (SPY Buy & Hold)"))

    metrics_df = pd.DataFrame(eval_list)
    print("\n" + tabulate(metrics_df, headers="keys", tablefmt="fancy_grid", showindex=False, floatfmt=".2f"))

    # Save CSV outputs
    comparison_csv_path = os.path.join(cfg.OUTPUT_DIR, "ensemble_performance_comparison.csv")
    metrics_df.to_csv(comparison_csv_path, index=False)
    reg_oos.to_csv(os.path.join(cfg.OUTPUT_DIR, "regime_detection_log.csv"))
    curves_df.to_csv(os.path.join(cfg.OUTPUT_DIR, "ensemble_equity_curves.csv"))
    print(f"\n  [+] Saved performance comparison table: {comparison_csv_path}")

    # 7. Visualization Plotting
    print("\n[Step 6] Generating Comparative Tearsheet & Regime Visualizations...")
    plot_equity_curves(curves_df, bench_oos, reg_oos, cfg.OUTPUT_DIR)

    print("\n" + "=" * 80)
    print(" EXPERIMENT SUCCESSFULLY COMPLETED")
    print("=" * 80)

def plot_equity_curves(curves_df: pd.DataFrame, bench_series: pd.Series, reg_df: pd.DataFrame, output_dir: str):
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12), gridspec_kw={"height_ratios": [2.5, 1.2, 1.0]}, sharex=True)

    # 1. Equity Curves
    dates = curves_df.index
    bench_norm = bench_series / bench_series.iloc[0]

    ax1.plot(dates, curves_df["Trend_Following"], label="Trend Following (L05.1)", color="#3498db", lw=1.5, alpha=0.7)
    ax1.plot(dates, curves_df["Momentum"], label="Momentum L/S (L05/16)", color="#e67e22", lw=1.5, alpha=0.7)
    ax1.plot(dates, curves_df["Mean_Reversion"], label="Mean Reversion (L05.2)", color="#9b59b6", lw=1.5, alpha=0.7)
    ax1.plot(dates, curves_df["Equal_Weight_1_3"], label="Equal Weight 1/3 (L05.3)", color="#95a5a6", lw=1.8, linestyle="--")
    ax1.plot(dates, curves_df["Risk_Parity"], label="Risk Parity Inv-Vol (L05.3)", color="#f39c12", lw=2.0, linestyle="-.")
    ax1.plot(dates, curves_df["Regime_Routed_Ensemble"], label="Dynamic Regime Ensemble (L12)", color="#27ae60", lw=2.8)
    ax1.plot(dates, bench_norm, label="Benchmark SPY", color="#e74c3c", lw=2.0, alpha=0.5, linestyle=":")

    ax1.set_title("Multi-Strategy Ensemble: Trend + Momentum + Reversion vs. Dynamic Regime Router\nSourced from ai-quant-book/manuscript/en (Lessons 05, 12, 15, 16)", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Normalized Portfolio Equity", fontsize=11)
    ax1.legend(loc="upper left", frameon=True, fontsize=9, ncol=2)
    ax1.grid(True, linestyle="--", alpha=0.4)

    # 2. Drawdowns
    dd_ensemble = (curves_df["Regime_Routed_Ensemble"] - curves_df["Regime_Routed_Ensemble"].cummax()) / curves_df["Regime_Routed_Ensemble"].cummax()
    dd_bench = (bench_norm - bench_norm.cummax()) / bench_norm.cummax()
    dd_equal = (curves_df["Equal_Weight_1_3"] - curves_df["Equal_Weight_1_3"].cummax()) / curves_df["Equal_Weight_1_3"].cummax()

    ax2.fill_between(dates, dd_ensemble * 100, 0, color="#27ae60", alpha=0.35, label="Regime Ensemble Drawdown")
    ax2.plot(dates, dd_bench * 100, color="#e74c3c", lw=1.5, label="SPY Drawdown")
    ax2.plot(dates, dd_equal * 100, color="#95a5a6", lw=1.2, linestyle="--", label="Equal Weight Drawdown")
    ax2.set_ylabel("Drawdown (%)", fontsize=11)
    ax2.legend(loc="lower left", frameon=True, fontsize=9)
    ax2.grid(True, linestyle="--", alpha=0.4)

    # 3. Dynamic Strategy Regime Weights
    w_trend = reg_df["weight_trend"]
    w_mom = reg_df["weight_momentum"]
    w_rev = reg_df["weight_reversion"]
    w_cash = reg_df["weight_cash"]

    ax3.stackplot(dates, w_trend, w_mom, w_rev, w_cash, labels=["Trend Weight", "Momentum Weight", "Reversion Weight", "Cash / T-Bills"],
                  colors=["#3498db", "#e67e22", "#9b59b6", "#1abc9c"], alpha=0.7)
    ax3.set_ylabel("Allocation Weight", fontsize=11)
    ax3.set_ylim(0, 1.0)
    ax3.legend(loc="upper left", frameon=True, fontsize=8, ncol=4)
    ax3.grid(True, linestyle="--", alpha=0.4)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    plt.tight_layout()
    chart_path = os.path.join(output_dir, "multi_strategy_equity_curves.png")
    plt.savefig(chart_path, dpi=300)
    plt.close()
    print(f"  [+] Saved ensemble tearsheet chart: {chart_path}")

if __name__ == "__main__":
    run_experiment()
