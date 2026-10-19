# Common Quantitative & Econometric Utilities
**FE5209 Financial Econometrics Project**

Reusable core library shared across both **Pairs Trading** and **Multi-Strategy Ensemble**:

---

## Modules

| Module | Description |
| :--- | :--- |
| [`data_loader.py`](file:///Users/jacsonchong/Documents/NUS/AY2026%202027%20Semester%201/FE5209%20Financial%20Econometrics/project/common/data_loader.py) | Universal data ingestion via Yahoo Finance, persistent local CSV caching, and in/out-of-sample data splitting |
| [`microstructure.py`](file:///Users/jacsonchong/Documents/NUS/AY2026%202027%20Semester%201/FE5209%20Financial%20Econometrics/project/common/microstructure.py) | Multi-market execution costs: broker commissions (SGX 12 bps, Europe 8 bps, US 3.5 bps), discrete board lots (100 shares for SGX, 1 for US/Europe), borrow interest, slippage, and custom Backtrader `CommInfoBase` / `quantize_shares` helpers |
| [`performance.py`](file:///Users/jacsonchong/Documents/NUS/AY2026%202027%20Semester%201/FE5209%20Financial%20Econometrics/project/common/performance.py) | Full institutional metrics: Sharpe, Sortino, Calmar, Max Drawdown duration, Win Rate, Profit Factor, CAPM Jensen's Alpha & Beta, Fama-French 3-Factor regression |
| [`tearsheet.py`](file:///Users/jacsonchong/Documents/NUS/AY2026%202027%20Semester%201/FE5209%20Financial%20Econometrics/project/common/tearsheet.py) | Academic publication-grade figures, cumulative equity comparison vs benchmark, underwater drawdown plots, and monthly return heatmaps |

---

## Usage

```python
from common import (
    DataLoader,
    PerformanceEvaluator,
    TearSheetGenerator,
    get_market_microstructure,
    create_market_commission,
    quantize_shares
)

# Ingest data
loader = DataLoader(cache_dir="data/cache")
prices = loader.fetch_price_data(["AAPL", "MSFT", "D05.SI"], "2019-01-01", "2026-08-31")

# Evaluate performance
evaluator = PerformanceEvaluator(risk_free_rate_annual=0.04)
metrics = evaluator.evaluate_returns(strategy_returns, equity_curve)
```
