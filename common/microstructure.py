"""
Institutional Market Microstructure & Execution Parameters
FE5209 Financial Econometrics Project

Common library for:
- Discrete board lot sizes (SGX: 100 shares, US/Europe: 1 share, Crypto: 0.0001)
- Percentage-based commission fees (SGX: 12 bps, Europe: 8 bps, US: 3.5 bps, Crypto: 10 bps)
- Short borrow financing drag (daily borrow interest charged on short notional)
- Execution slippage modeling (bid-ask half-spread impact)
- Backtrader custom CommissionInfo & share quantization
"""

import numpy as np
import backtrader as bt
from typing import Optional, Dict, Any


def get_market_microstructure(ticker: str) -> Dict[str, Any]:
    """
    Returns realistic market-specific microstructure parameters:
    1. SGX (Singapore, .SI):
       - Lot size: 100 shares (standard SGX board lot)
       - Transaction friction: 12.0 bps per side (brokerage commission 8 bps + SGX clearing/trading fees 4 bps + GST)
       - Annual short borrow fee: 1.50% (150 bps)
    2. STOXX 600 (Europe, .DE, .PA, .L, .AS, .SW, .MC, .MI):
       - Lot size: 1 share
       - Transaction friction: 8.0 bps per side (broker commission + exchange fees + stamp duty / FTT impact)
       - Annual short borrow fee: 1.25% (125 bps)
    3. S&P 500 (US, NYSE/Nasdaq):
       - Lot size: 1 share
       - Transaction friction: 3.5 bps per side (institutional prime broker commission ~1 bps + bid-ask half spread ~2.5 bps)
       - Annual short borrow fee: 0.75% (75 bps, general collateral)
    4. Digital Currencies (Crypto, -USD, -USDT):
       - Lot size: 0.0001
       - Transaction friction: 10.0 bps per side (exchange taker fee + slippage)
       - Annual short borrow fee: 8.00% (800 bps crypto lending funding rate)
    """
    t = ticker.upper()
    if t.endswith(".SI"):
        return {
            "market": "SGX (Singapore)",
            "lot_size": 100,
            "tx_bps": 12.0,
            "tx_rate": 0.0012,
            "borrow_annual": 0.015,
            "borrow_daily": 0.015 / 252.0
        }
    elif any(t.endswith(sfx) for sfx in [".DE", ".PA", ".L", ".AS", ".SW", ".MC", ".MI"]):
        return {
            "market": "STOXX 600 (Europe)",
            "lot_size": 1,
            "tx_bps": 8.0,
            "tx_rate": 0.0008,
            "borrow_annual": 0.0125,
            "borrow_daily": 0.0125 / 252.0
        }
    elif "-USD" in t or "-USDT" in t:
        return {
            "market": "Digital Currency",
            "lot_size": 0.0001,
            "tx_bps": 10.0,
            "tx_rate": 0.0010,
            "borrow_annual": 0.08,
            "borrow_daily": 0.08 / 252.0
        }
    else:
        return {
            "market": "US S&P 500",
            "lot_size": 1,
            "tx_bps": 3.5,
            "tx_rate": 0.00035,
            "borrow_annual": 0.0075,
            "borrow_daily": 0.0075 / 252.0
        }


class MarketCommissionInfo(bt.CommInfoBase):
    """
    Backtrader Commission Scheme tailored to global exchange microstructure:
    - Percentage-based brokerage & exchange clearing fee (commtype = COMM_PERC)
    - Short borrow interest financing rate (interest charged only on short positions)
    - Stock-like margin behavior
    """
    params = (
        ("commission", 0.00035),    # Default: US 3.5 bps = 0.00035
        ("commtype", bt.CommInfoBase.COMM_PERC),
        ("stocklike", True),
        ("interest", 0.0075),        # Annual short borrow fee (0.75% for US)
        ("interest_long", False),    # No borrow interest on long positions
        ("mult", 1.0),
        ("automargin", False),
    )


def create_market_commission(
    ticker: str,
    custom_tx_bps: Optional[float] = None,
    custom_borrow_annual: Optional[float] = None
) -> bt.CommInfoBase:
    """
    Factory function creating a MarketCommissionInfo instance configured
    with the exact microstructure parameters for a given ticker.
    """
    spec = get_market_microstructure(ticker)
    tx_rate = (custom_tx_bps / 10_000.0) if custom_tx_bps is not None else spec["tx_rate"]
    borrow_rate = custom_borrow_annual if custom_borrow_annual is not None else spec["borrow_annual"]

    class SpecificMarketCommission(bt.CommInfoBase):
        params = (
            ("commission", tx_rate),
            ("commtype", bt.CommInfoBase.COMM_PERC),
            ("stocklike", True),
            ("interest", borrow_rate),
            ("interest_long", False),
            ("mult", 1.0),
            ("automargin", False),
        )
    return SpecificMarketCommission()


def quantize_shares(target_dollars: float, price: float, lot_size: float) -> float:
    """
    Quantizes target dollar demand into discrete shares respecting exchange board lot sizes:
    - SGX (.SI): Multiples of 100 shares
    - US / STOXX 600: Multiples of 1 share
    - Crypto: Step size of 0.0001
    """
    if price <= 0.0 or target_dollars <= 0.0:
        return 0.0

    raw_shares = target_dollars / price
    if lot_size >= 1.0:
        lot = int(lot_size)
        quantized = (int(raw_shares) // lot) * lot
        return float(quantized)
    else:
        steps = int(raw_shares / lot_size)
        return float(steps * lot_size)
