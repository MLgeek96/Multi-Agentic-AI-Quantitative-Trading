"""
Common Quantitative & Econometric Utilities Library
FE5209 Financial Econometrics Project

Modules:
- data_loader: Data ingestion, caching, and in/out-of-sample splitting
- microstructure: Global market commission schemes, discrete board lots, short borrow rates, slippage
- performance: Academic & institutional performance metrics, Sharpe, Sortino, Calmar, CAPM & Fama-French attribution
- tearsheet: Publication-grade tearsheets and visual analytics
"""

from common.data_loader import DataLoader
from common.performance import PerformanceEvaluator
from common.tearsheet import TearSheetGenerator
from common.microstructure import (
    get_market_microstructure,
    MarketCommissionInfo,
    create_market_commission,
    quantize_shares
)

__all__ = [
    "DataLoader",
    "PerformanceEvaluator",
    "TearSheetGenerator",
    "get_market_microstructure",
    "MarketCommissionInfo",
    "create_market_commission",
    "quantize_shares",
]
