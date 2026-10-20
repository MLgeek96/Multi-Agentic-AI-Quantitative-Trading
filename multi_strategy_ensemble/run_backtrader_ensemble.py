"""
CLI Runner for Backtrader Multi-Strategy Ensemble System
FE5209 Financial Econometrics Project

Runs the complete quantitative ensemble under Backtrader with:
- Market execution commissions (SGX: 12 bps, Europe: 8 bps, US: 3.5 bps)
- Slippage (2 bps)
- Discrete board lots (100 shares for SGX, 1 for US/Europe)
- Short borrow interest financing
- Risk exposure & dynamic regime router allocation
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from tabulate import tabulate

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root in sys.path:
    sys.path.remove(project_root)
sys.path.insert(0, project_root)

from multi_strategy_ensemble.config import EnsembleConfig
from multi_strategy_ensemble.backtrader_ensemble import run_backtrader_multi_strategy_suite

def main():
    cfg = EnsembleConfig()
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)

    print("=" * 80)
    print(" BACKTRADER MULTI-STRATEGY ENSEMBLE SYSTEM")
    print(" (Trend Following + Momentum + Pairs Reversion + Risk Parity + Regime Router)")
    print("=" * 80)

    # 1. Load data
    print("\n[Step 1] Loading Universe Prices and Benchmark Data...")
    all_prices = pd.read_csv(cfg.DATA_CACHE_PRICES, index_col=0, parse_dates=True)
    spy_df = pd.read_csv(cfg.DATA_CACHE_SPY, index_col=0, parse_dates=True)
    bench_series = spy_df["Close"] if "Close" in spy_df.columns else spy_df.iloc[:, 0]

    if cfg.STRATEGY_UNIVERSE == "ALL" or "ALL" in cfg.STRATEGY_UNIVERSE or not cfg.STRATEGY_UNIVERSE:
        valid_tickers = [c for c in all_prices.columns if c not in ["Date", "date", "Unnamed: 0"]]
    else:
        valid_tickers = [t for t in cfg.STRATEGY_UNIVERSE if t in all_prices.columns]
    print(f"  [+] Multi-Asset Universe ({len(valid_tickers)} assets across S&P 500, STI, and STOXX 600)")
    universe_prices = all_prices[valid_tickers].dropna(how="all").ffill().bfill()

    # Default verified economic pairs
    default_pairs = [
        ("CAT", "DE"),
        ("UNP", "CSX"),
        ("XOM", "CVX"),
        ("KO", "PEP"),
        ("JNJ", "ABBV"),
        ("JPM", "BAC")
    ]

    # 2. Run Backtrader Suite
    print("\n[Step 2] Executing Backtrader Simulation Suite (Microstructure, Lots, Borrow & Slippage)...")
    res = run_backtrader_multi_strategy_suite(
        universe_prices=universe_prices,
        benchmark_series=bench_series,
        candidate_pairs=default_pairs,
        initial_capital=cfg.INITIAL_CAPITAL,
        start_date=cfg.OUT_OF_SAMPLE_START,
        end_date=cfg.END_DATE,
        slippage_bps=2.0,
        rf_annual=cfg.RISK_FREE_RATE_ANNUAL,
        warmup_bars=120,   # pre-test bars for 60-day indicator formation (no trading)
        min_test_bars=5,   # short Oct-2026 test window (~13 trading days)
    )

    metrics_df = res["metrics_summary"]
    equity_df = res["equity_curves"]

    # 3. Print Results Table
    print("\n" + "=" * 80)
    print(" BACKTRADER EMPIRICAL PERFORMANCE COMPARISON (OUT-OF-SAMPLE)")
    print("=" * 80)
    print(tabulate(metrics_df, headers="keys", tablefmt="fancy_grid", floatfmt=".2f"))

    # 4. Save CSV Reports
    csv_perf_path = os.path.join(cfg.OUTPUT_DIR, "backtrader_ensemble_performance.csv")
    metrics_df.to_csv(csv_perf_path)
    print(f"\n  [+] Saved performance comparison: {csv_perf_path}")

    csv_equity_path = os.path.join(cfg.OUTPUT_DIR, "backtrader_ensemble_equity_curves.csv")
    equity_df.to_csv(csv_equity_path)
    print(f"  [+] Saved daily equity curves: {csv_equity_path}")

    # 5. Generate Tearsheet Plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={"height_ratios": [3, 1]})

    palette = {
        "Trend_Following": "#2ca02c",
        "Momentum": "#1f77b4",
        "Mean_Reversion": "#9467bd",
        "Equal_Weight_1_3": "#ff7f0e",
        "Risk_Parity": "#8c564b",
        "Regime_Routed_Ensemble": "#d62728",
        "Benchmark_SPY": "#7f7f7f",
    }

    labels = {
        "Trend_Following": "Trend Following (L05.1)",
        "Momentum": "Momentum L/S (L05 & 16)",
        "Mean_Reversion": "Mean Reversion (L05.2)",
        "Equal_Weight_1_3": "Equal Weight 1/3 (L05.3)",
        "Risk_Parity": "Risk Parity Inv-Vol (L05.3)",
        "Regime_Routed_Ensemble": "Dynamic Regime Ensemble (L12)",
        "Benchmark_SPY": "Benchmark (SPY Buy & Hold)",
    }

    for col in equity_df.columns:
        norm_eq = equity_df[col] / cfg.INITIAL_CAPITAL
        lw = 2.5 if col in ["Regime_Routed_Ensemble", "Trend_Following", "Benchmark_SPY"] else 1.5
        ls = "--" if col == "Benchmark_SPY" else "-"
        ax1.plot(equity_df.index, norm_eq, label=labels.get(col, col), color=palette.get(col, "blue"), lw=lw, ls=ls)

    ax1.set_title("Backtrader Multi-Strategy Ensemble Equity Curves (Full Microstructure Friction & Board Lots)", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Normalized Portfolio Equity ($1.0 = Initial)", fontsize=11)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left", frameon=True, fontsize=9)

    # Drawdown panel for Regime Ensemble vs SPY
    eq_regime = equity_df["Regime_Routed_Ensemble"]
    dd_regime = (eq_regime - eq_regime.cummax()) / eq_regime.cummax() * 100.0

    eq_spy = equity_df["Benchmark_SPY"]
    dd_spy = (eq_spy - eq_spy.cummax()) / eq_spy.cummax() * 100.0

    ax2.plot(equity_df.index, dd_spy, label="SPY Drawdown", color="#7f7f7f", lw=1.5, ls="--")
    ax2.plot(equity_df.index, dd_regime, label="Regime Ensemble Drawdown", color="#d62728", lw=2.0)
    ax2.fill_between(equity_df.index, dd_regime, 0, color="#d62728", alpha=0.2)
    ax2.set_title("Underwater Drawdown Profile: Dynamic Regime Router vs SPY", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Drawdown (%)", fontsize=10)
    ax2.set_xlabel("Date", fontsize=11)
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="lower left", fontsize=9)

    plt.tight_layout()
    chart_path = os.path.join(cfg.OUTPUT_DIR, "backtrader_ensemble_equity_curves.png")
    plt.savefig(chart_path, dpi=300)
    plt.close()
    print(f"  [+] Saved tearsheet visualization: {chart_path}")

    print("\n" + "=" * 80)
    print(" BACKTRADER ENSEMBLE EXPERIMENT COMPLETED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    main()
