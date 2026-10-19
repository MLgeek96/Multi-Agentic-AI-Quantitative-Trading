"""
Configuration for Multi-Strategy Ensemble System
Sourced solely from 'AI Quantitative Trading: From Zero to One' (ai-quant-book/manuscript/en):
- Lesson 04: The Real Role of Technical Indicators (ADX, ATR, RSI, Moving Averages)
- Lesson 05: Classic Strategy Paradigms (Trend Following, Mean Reversion, Multi-Strategy Portfolios)
- Lesson 08: Beta, Hedging, and Market Neutrality
- Lesson 12: Market Regime Detection (Trending, Ranging, Crisis)
- Lesson 15: Risk Control and Capital Management
- Lesson 16: Portfolio Construction and Exposure Management
- Lesson 18: Transaction Cost Modeling and Tradability
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
import os

@dataclass
class EnsembleConfig:
    # ----------------------------------------------------
    # Path & Environment
    # ----------------------------------------------------
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_DIR: str = os.path.join(BASE_DIR, "outputs")
    DATA_CACHE_PRICES: str = os.path.join(os.path.dirname(BASE_DIR), "data", "cache", "asset_prices.csv")
    DATA_CACHE_SPY: str = os.path.join(os.path.dirname(BASE_DIR), "data", "cache", "benchmark_SPY.csv")

    # ----------------------------------------------------
    # Timeline (Group Project Mandate: Test Period Oct 2026 - Week 11)
    # ----------------------------------------------------
    START_DATE: str = "2014-01-01"
    IN_SAMPLE_END: str = "2026-09-30"        # In-sample calibration up to eve of Oct 2026
    OUT_OF_SAMPLE_START: str = "2026-10-01"  # Test period begins Oct 1, 2026
    END_DATE: str = "2026-10-16"             # Current test period cutoff (Oct 16; extend to 2026-10-23 next Friday)

    # ----------------------------------------------------
    # Capital & Realistic Execution Friction (Lessons 07 & 18)
    # ----------------------------------------------------
    INITIAL_CAPITAL: float = 1_000_000.0       # Starting portfolio equity ($)
    TRANSACTION_COST_BPS: float = 5.0        # Commission + slippage (5 bps = 0.0005)
    SHORT_BORROW_FEE_ANNUAL: float = 0.01    # 1.0% annual short borrow financing cost
    RISK_FREE_RATE_ANNUAL: float = 0.04      # 4.0% annualized risk-free collateral yield

    # ----------------------------------------------------
    # Multi-Asset Strategy Universe (All 308 Global Tickers)
    # Covering S&P 500 (11 GICS sectors), STI (all 30 constituents), and STOXX 600 leaders
    # ----------------------------------------------------
    STRATEGY_UNIVERSE: List[str] = field(default_factory=lambda: [
        # Set to "ALL" to dynamically ingest all tickers from cache, or define explicitly
        "ALL"
    ])
    BENCHMARK_TICKER: str = "SPY"

    # ----------------------------------------------------
    # Lesson 12: Regime Detection Thresholds (Rules-Based)
    # ----------------------------------------------------
    REGIME_VOL_WINDOW: int = 20              # 20-day rolling realized volatility
    REGIME_RETURN_WINDOW: int = 20           # 20-day rolling cumulative return
    REGIME_ADX_WINDOW: int = 14              # 14-day ADX trend strength
    ADX_TREND_THRESHOLD: float = 25.0        # ADX > 25 -> Strong trend regime
    ADX_RANGING_THRESHOLD: float = 20.0      # ADX < 20 -> Ranging / Mean-reverting regime
    CRISIS_VOL_ANNUAL_THRESHOLD: float = 0.30# Realized volatility > 30% -> Crisis regime

    # ----------------------------------------------------
    # Lesson 05.1: Trend Following Parameters
    # ----------------------------------------------------
    TREND_FAST_MA: int = 10                  # Short-term MA (Lesson 05.1: MA10/MA60)
    TREND_SLOW_MA: int = 60                  # Long-term trend MA
    TREND_ADX_FILTER: bool = True            # Only trade trend when ADX > 20
    TREND_TRAILING_STOP_ATR_MULT: float = 2.5 # ATR trailing stop (Lesson 15)

    # ----------------------------------------------------
    # Momentum Parameters (Lessons 05 & 16)
    # ----------------------------------------------------
    MOMENTUM_LOOKBACK_DAYS: int = 60         # 60-day relative momentum lookback
    MOMENTUM_HOLDING_DAYS: int = 10          # Rebalance frequency (bi-weekly)
    MOMENTUM_TOP_K: int = 5                  # Long top 5 relative strength leaders
    MOMENTUM_BOTTOM_K: int = 5               # Short bottom 5 relative strength laggards
    MOMENTUM_VOL_SCALE: bool = True          # Inverse volatility position sizing

    # ----------------------------------------------------
    # Lesson 05.2: Mean Reversion Parameters
    # ----------------------------------------------------
    REVERSION_WINDOW: int = 20               # 20-day rolling mean & standard deviation
    REVERSION_ENTRY_Z: float = 2.0           # Enter when price / spread deviates > 2.0 std dev
    REVERSION_EXIT_Z: float = 0.2            # Exit when price returns within 0.2 std dev
    REVERSION_STOP_LOSS_Z: float = 3.5       # Strict stop loss to prevent "buying all the way down"

# Re-export microstructure lookup from common.microstructure
import sys
_p_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _p_root not in sys.path:
    sys.path.insert(0, _p_root)

from common.microstructure import get_market_microstructure
