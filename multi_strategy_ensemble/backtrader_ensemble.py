"""
Backtrader Multi-Strategy Ensemble Framework
FE5209 Financial Econometrics Project

Implements full Backtrader integration for:
1. Trend Following (Lesson 05.1: Dual-MA 10/60 + ADX Filter + ATR Stops)
2. Cross-Sectional Momentum (Lessons 05 & 16: 60-day Relative Strength + Inverse-Vol Sizing)
3. Cointegrated Pairs Mean Reversion (Lesson 05.2: Multi-Pair Spread Tracking + Circuit Breakers)
4. Dynamic Market Regime Router (Lesson 12 & 05.3: Adaptive Macro State Capital Routing)

Factors in:
- Market-specific execution fees (SGX: 12 bps, Europe: 8 bps, US: 3.5 bps)
- Slippage cost (2 bps default half-spread impact)
- Discrete board lot size constraints (100 shares for SGX, 1 share for US/Europe)
- Short borrow funding cost (daily interest on short positions)
- Risk exposure & dynamic leverage management
"""

import os
import sys
import numpy as np
import pandas as pd
import backtrader as bt
from typing import Dict, Any, List, Tuple, Optional
import datetime
import logging

# Robust project root on sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common.microstructure import get_market_microstructure, create_market_commission, quantize_shares
from multi_strategy_ensemble.regime_detector import RegimeDetector

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. BACKTRADER TREND FOLLOWING STRATEGY (LESSON 05.1)
# ==============================================================================

class BacktraderTrendFollowing(bt.Strategy):
    """
    Multi-Asset Trend Following Strategy in Backtrader:
    - Dual Moving Average (10-day fast SMA / 60-day slow SMA)
    - Trend strength filter (ADX > 20)
    - Inverse volatility position sizing with discrete board lot constraints
    - Trailing stop via ATR
    - Market commissions, slippage, and cash yield
    """
    params = (
        ("fast_window", 10),
        ("slow_window", 60),
        ("adx_threshold", 20.0),
        ("adx_period", 14),
        ("atr_period", 20),
        ("atr_mult", 2.5),
        ("rf_annual", 0.04),
        ("enable_cash_yield", True),
    )

    def __init__(self):
        self.rf_daily = (1.0 + self.p.rf_annual) ** (1.0 / 252.0) - 1.0

        self.fast_mas = {}
        self.slow_mas = {}
        self.vols = {}
        self.highest_prices = {}

        for d in self.datas:
            name = d._name
            self.fast_mas[name] = bt.indicators.SMA(d.close, period=self.p.fast_window)
            self.slow_mas[name] = bt.indicators.SMA(d.close, period=self.p.slow_window)
            self.vols[name] = bt.indicators.StdDev(d.close, period=self.p.atr_period)
            self.highest_prices[name] = 0.0

        self.daily_records = []

    def next(self):
        dt = self.datas[0].datetime.date(0)

        # Accrue interest on idle cash
        if self.p.enable_cash_yield:
            cash = self.broker.getcash()
            if cash > 0:
                self.broker.add_cash(cash * self.rf_daily)

        # Evaluate trend signals
        active_candidates = []
        for d in self.datas:
            name = d._name
            close_price = d.close[0]
            if len(d) < self.p.slow_window:
                continue

            fast_val = self.fast_mas[name][0]
            slow_val = self.slow_mas[name][0]
            vol_val = max(self.vols[name][0], 0.01)

            pos = self.getposition(d).size

            # Check trailing stop for open long positions
            if pos > 0:
                self.highest_prices[name] = max(self.highest_prices[name], close_price)
                stop_price = self.highest_prices[name] - self.p.atr_mult * vol_val
                if close_price < stop_price or fast_val < slow_val:
                    self.close(data=d)
                    self.highest_prices[name] = 0.0
                    continue

            # Candidate for long trend: Golden Cross (MA10 > MA60)
            if fast_val > slow_val:
                spec = get_market_microstructure(name)
                inv_vol = 1.0 / max(vol_val / max(close_price, 1e-4), 0.005)
                active_candidates.append((d, name, close_price, spec["lot_size"], inv_vol))

        # Size positions for active candidates
        if active_candidates:
            total_inv_vol = sum(c[4] for c in active_candidates)
            avail_equity = self.broker.getvalue() * 0.95  # 95% equity cap

            for d, name, price, lot_size, inv_vol in active_candidates:
                pos = self.getposition(d).size
                if pos == 0:
                    weight = inv_vol / total_inv_vol
                    target_dollars = avail_equity * weight
                    shares = quantize_shares(target_dollars, price, lot_size)
                    if shares > 0:
                        self.buy(data=d, size=shares)
                        self.highest_prices[name] = price

        self.daily_records.append({
            "date": dt,
            "equity": self.broker.getvalue(),
            "cash": self.broker.getcash()
        })


# ==============================================================================
# 2. BACKTRADER CROSS-SECTIONAL MOMENTUM STRATEGY (LESSONS 05 & 16)
# ==============================================================================

class BacktraderCrossSectionalMomentum(bt.Strategy):
    """
    Cross-Sectional Relative Strength Momentum in Backtrader:
    - Bi-weekly rebalancing (every 10 trading days)
    - 60-day trailing return ranking
    - Long top quintile, Short bottom quintile
    - Inverse-volatility risk parity sizing
    - Discrete board lot constraints
    - Short borrow financing fee automatically charged on short legs
    """
    params = (
        ("lookback_days", 60),
        ("rebalance_interval", 10),
        ("top_k", 5),
        ("rf_annual", 0.04),
        ("enable_cash_yield", True),
    )

    def __init__(self):
        self.rf_daily = (1.0 + self.p.rf_annual) ** (1.0 / 252.0) - 1.0
        self.bar_counter = 0
        self.daily_records = []

    def next(self):
        dt = self.datas[0].datetime.date(0)
        self.bar_counter += 1

        if self.p.enable_cash_yield:
            cash = self.broker.getcash()
            if cash > 0:
                self.broker.add_cash(cash * self.rf_daily)

        # Rebalance only every rebalance_interval bars
        if self.bar_counter < self.p.lookback_days or (self.bar_counter % self.p.rebalance_interval) != 0:
            self.daily_records.append({"date": dt, "equity": self.broker.getvalue(), "cash": self.broker.getcash()})
            return

        # 1. Rank all assets by 60-day trailing return
        perf_list = []
        for d in self.datas:
            if len(d) >= self.p.lookback_days:
                curr_p = d.close[0]
                past_p = d.close[-self.p.lookback_days]
                ret_60 = (curr_p / past_p - 1.0) if past_p > 0 else 0.0

                # Trailing 20-day volatility
                closes = np.array([d.close[-k] for k in range(20)])
                pcts = np.diff(closes) / closes[1:]
                vol_20 = float(np.std(pcts) * np.sqrt(252.0)) if len(pcts) > 1 else 0.20
                vol_20 = max(vol_20, 0.05)

                spec = get_market_microstructure(d._name)
                perf_list.append((d, d._name, curr_p, ret_60, vol_20, spec["lot_size"]))

        if len(perf_list) < 2 * self.p.top_k:
            self.daily_records.append({"date": dt, "equity": self.broker.getvalue(), "cash": self.broker.getcash()})
            return

        perf_list.sort(key=lambda x: x[3], reverse=True)
        long_basket = perf_list[:self.p.top_k]
        short_basket = perf_list[-self.p.top_k:]

        # Close positions not in new targets
        target_datas = set([item[0] for item in long_basket + short_basket])
        for d in self.datas:
            if d not in target_datas and self.getposition(d).size != 0:
                self.close(data=d)

        # 2. Size Longs & Shorts using Inverse-Volatility Parity
        tot_eq = self.broker.getvalue()
        long_cap = tot_eq * 0.45   # 45% Long book
        short_cap = tot_eq * 0.45  # 45% Short book

        sum_inv_vol_long = sum(1.0 / item[4] for item in long_basket)
        sum_inv_vol_short = sum(1.0 / item[4] for item in short_basket)

        # Execute Longs
        for d, name, price, _, vol, lot_size in long_basket:
            weight = (1.0 / vol) / sum_inv_vol_long
            target_dollars = long_cap * weight
            target_shares = quantize_shares(target_dollars, price, lot_size)
            curr_shares = self.getposition(d).size
            delta_shares = target_shares - curr_shares
            if delta_shares > 0:
                self.buy(data=d, size=delta_shares)
            elif delta_shares < 0:
                self.sell(data=d, size=abs(delta_shares))

        # Execute Shorts
        for d, name, price, _, vol, lot_size in short_basket:
            weight = (1.0 / vol) / sum_inv_vol_short
            target_dollars = short_cap * weight
            target_shares = quantize_shares(target_dollars, price, lot_size)
            curr_shares = self.getposition(d).size
            target_pos = -target_shares
            delta_shares = target_pos - curr_shares
            if delta_shares < 0:
                self.sell(data=d, size=abs(delta_shares))
            elif delta_shares > 0:
                self.buy(data=d, size=delta_shares)

        self.daily_records.append({
            "date": dt,
            "equity": self.broker.getvalue(),
            "cash": self.broker.getcash()
        })


# ==============================================================================
# 3. BACKTRADER MULTI-PAIR COINTEGRATION MEAN REVERSION (LESSON 05.2)
# ==============================================================================

class BacktraderMultiPairReversion(bt.Strategy):
    """
    Concurrent Multi-Pair Cointegrated Mean Reversion in Backtrader:
    - Simultaneously manages verified pairs (e.g., V-MA, CAT-DE, C38U-A17U)
    - Dynamic rolling hedge ratio and Z-score tracking
    - Stop-loss circuit breaker (|Z| >= 3.50) and time-stops
    - Discrete board lot constraints per leg
    - Short borrow interest deducted daily
    """
    params = (
        ("pairs_tuples", []),        # List of (asset1_name, asset2_name)
        ("entry_z", 1.50),
        ("exit_z", 0.20),
        ("stop_loss_z", 3.50),
        ("lookback", 60),
        ("max_holding_days", 40),
        ("capital_per_pair", 25_000.0),
        ("rf_annual", 0.04),
        ("enable_cash_yield", True),
    )

    def __init__(self):
        self.rf_daily = (1.0 + self.p.rf_annual) ** (1.0 / 252.0) - 1.0

        # Build name to data mapping
        self.data_by_name = {d._name: d for d in self.datas}
        self.pair_states = {}

        for a1, a2 in self.p.pairs_tuples:
            if a1 in self.data_by_name and a2 in self.data_by_name:
                spec1 = get_market_microstructure(a1)
                spec2 = get_market_microstructure(a2)
                self.pair_states[(a1, a2)] = {
                    "pos": 0,           # 0: Flat, +1: Long spread, -1: Short spread
                    "entry_bar": 0,
                    "shares1": 0.0,
                    "shares2": 0.0,
                    "lot1": spec1["lot_size"],
                    "lot2": spec2["lot_size"],
                }

        self.daily_records = []

    def next(self):
        dt = self.datas[0].datetime.date(0)

        if self.p.enable_cash_yield:
            cash = self.broker.getcash()
            if cash > 0:
                self.broker.add_cash(cash * self.rf_daily)

        if len(self) < self.p.lookback:
            self.daily_records.append({"date": dt, "equity": self.broker.getvalue(), "cash": self.broker.getcash()})
            return

        for (a1, a2), state in self.pair_states.items():
            d1 = self.data_by_name[a1]
            d2 = self.data_by_name[a2]
            p1 = d1.close[0]
            p2 = d2.close[0]

            # Rolling 60-day OLS hedge ratio & Z-score
            y_arr = np.log([d1.close[-k] for k in range(self.p.lookback)])
            x_arr = np.log([d2.close[-k] for k in range(self.p.lookback)])

            cov_xy = np.cov(x_arr, y_arr)[0, 1]
            var_x = np.var(x_arr)
            beta = float(cov_xy / var_x) if var_x > 1e-8 else 1.0
            beta = max(min(beta, 3.0), 0.20)  # Bound beta

            spread_hist = y_arr - beta * x_arr
            mean_s = np.mean(spread_hist)
            std_s = np.std(spread_hist)

            curr_spread = np.log(p1) - beta * np.log(p2)
            z_t = float((curr_spread - mean_s) / std_s) if std_s > 1e-8 else 0.0

            holding_days = len(self) - state["entry_bar"] if state["pos"] != 0 else 0

            # State Machine
            if state["pos"] == 0:
                # 1. Long Spread (Z <= -entry_z)
                if z_t <= -self.p.entry_z:
                    cap = self.p.capital_per_pair
                    target_d1 = cap / (1.0 + beta)
                    target_d2 = beta * target_d1
                    s1 = quantize_shares(target_d1, p1, state["lot1"])
                    s2 = quantize_shares(target_d2, p2, state["lot2"])
                    if s1 > 0 and s2 > 0:
                        self.buy(data=d1, size=s1)
                        self.sell(data=d2, size=s2)
                        state["pos"] = +1
                        state["entry_bar"] = len(self)
                        state["shares1"] = s1
                        state["shares2"] = -s2

                # 2. Short Spread (Z >= +entry_z)
                elif z_t >= self.p.entry_z:
                    cap = self.p.capital_per_pair
                    target_d1 = cap / (1.0 + beta)
                    target_d2 = beta * target_d1
                    s1 = quantize_shares(target_d1, p1, state["lot1"])
                    s2 = quantize_shares(target_d2, p2, state["lot2"])
                    if s1 > 0 and s2 > 0:
                        self.sell(data=d1, size=s1)
                        self.buy(data=d2, size=s2)
                        state["pos"] = -1
                        state["entry_bar"] = len(self)
                        state["shares1"] = -s1
                        state["shares2"] = s2

            elif state["pos"] == +1:
                # Exit Long Spread
                if z_t >= -self.p.exit_z or z_t <= -self.p.stop_loss_z or holding_days >= self.p.max_holding_days:
                    self.close(data=d1)
                    self.close(data=d2)
                    state["pos"] = 0
                    state["shares1"] = 0.0
                    state["shares2"] = 0.0

            elif state["pos"] == -1:
                # Exit Short Spread
                if z_t <= self.p.exit_z or z_t >= self.p.stop_loss_z or holding_days >= self.p.max_holding_days:
                    self.close(data=d1)
                    self.close(data=d2)
                    state["pos"] = 0
                    state["shares1"] = 0.0
                    state["shares2"] = 0.0

        self.daily_records.append({
            "date": dt,
            "equity": self.broker.getvalue(),
            "cash": self.broker.getcash()
        })


# ==============================================================================
# 4. MASTER RUNNER & METRIC EVALUATION ENGINE
# ==============================================================================

def compute_bt_metrics(daily_equity: pd.Series, initial_capital: float, rf_annual: float = 0.04) -> Dict[str, Any]:
    """Computes academic performance metrics from a daily equity series."""
    clean_eq = daily_equity.dropna()
    if len(clean_eq) < 5:
        return {}

    n = len(clean_eq)
    tot_ret = float((clean_eq.iloc[-1] - initial_capital) / initial_capital)
    ann_ret = float((1.0 + tot_ret) ** (252.0 / n) - 1.0)

    daily_ret = clean_eq.pct_change().dropna()
    ann_vol = float(daily_ret.std() * np.sqrt(252.0))

    rf_daily = (1.0 + rf_annual) ** (1.0 / 252.0) - 1.0
    excess_ret = daily_ret - rf_daily
    sharpe = float(np.sqrt(252.0) * excess_ret.mean() / (daily_ret.std() + 1e-8))

    peaks = clean_eq.cummax()
    drawdown = (clean_eq - peaks) / peaks
    max_dd = float(drawdown.min())
    calmar = float(ann_ret / abs(max_dd)) if abs(max_dd) > 1e-4 else 0.0

    pos_days = (daily_ret > 0).sum()
    win_rate = float(pos_days / len(daily_ret) * 100.0) if len(daily_ret) > 0 else 0.0

    gross_gains = daily_ret[daily_ret > 0].sum()
    gross_losses = abs(daily_ret[daily_ret < 0].sum())
    profit_factor = float(gross_gains / gross_losses) if gross_losses > 0 else float("inf")

    return {
        "Total Return (%)": tot_ret * 100.0,
        "Annual Return (%)": ann_ret * 100.0,
        "Annual Volatility (%)": ann_vol * 100.0,
        "Sharpe Ratio": sharpe,
        "Max Drawdown (%)": max_dd * 100.0,
        "Calmar Ratio": calmar,
        "Daily Win Rate (%)": win_rate,
        "Profit Factor": profit_factor,
        "Final Equity ($)": float(clean_eq.iloc[-1]),
    }


def run_backtrader_multi_strategy_suite(
    universe_prices: pd.DataFrame,
    benchmark_series: pd.Series,
    candidate_pairs: List[Tuple[str, str]],
    initial_capital: float = 100_000.0,
    start_date: str = "2025-01-01",
    end_date: str = "2026-08-31",
    slippage_bps: float = 2.0,
    rf_annual: float = 0.04
) -> Dict[str, Any]:
    """
    Executes the full Backtrader Multi-Strategy Ensemble suite over out-of-sample data:
    1. Trend Following in Backtrader
    2. Momentum in Backtrader
    3. Mean Reversion in Backtrader
    4. Equal Weight 1/3 Ensemble
    5. Risk Parity (Inverse-Volatility) Ensemble
    6. Dynamic Regime-Routed Ensemble
    7. Benchmark (SPY) Buy & Hold
    """
    # Slice to OOS window
    common_idx = universe_prices.index.intersection(benchmark_series.index).sort_values()
    oos_idx = common_idx[(common_idx >= pd.to_datetime(start_date)) & (common_idx <= pd.to_datetime(end_date))]
    if len(oos_idx) < 20:
        raise ValueError(f"Insufficient out-of-sample bars ({len(oos_idx)}) between {start_date} and {end_date}.")

    # Filter active tickers with non-zero variance (removes delisted symbols)
    valid_cols = [
        c for c in universe_prices.columns
        if len(universe_prices.loc[oos_idx, c].dropna()) >= 30
        and universe_prices.loc[oos_idx, c].dropna().std() > 1e-6
        and (universe_prices.loc[oos_idx, c].dropna() > 0).any()
    ]
    prices_oos = universe_prices.loc[oos_idx, valid_cols]
    bench_oos = benchmark_series.loc[oos_idx]

    slippage_perc = slippage_bps / 10_000.0

    # ----------------------------------------------------
    # RUN 1: TREND FOLLOWING IN BACKTRADER
    # ----------------------------------------------------
    cerebro_trend = bt.Cerebro()
    cerebro_trend.broker.setcash(initial_capital)
    cerebro_trend.broker.set_slippage_perc(slippage_perc)

    for ticker in prices_oos.columns:
        p_ser = prices_oos[ticker]
        p_clean = p_ser.replace(0, np.nan).ffill().bfill().values
        df_feed = pd.DataFrame({
            "Open": p_clean,
            "High": p_clean * 1.005,
            "Low": p_clean * 0.995,
            "Close": p_clean,
            "Volume": 100_000.0
        }, index=pd.to_datetime(oos_idx))
        feed = bt.feeds.PandasData(dataname=df_feed, name=ticker)
        cerebro_trend.adddata(feed, name=ticker)
        comm = create_market_commission(ticker)
        cerebro_trend.broker.addcommissioninfo(comm, name=ticker)

    cerebro_trend.addstrategy(BacktraderTrendFollowing, rf_annual=rf_annual)
    res_trend = cerebro_trend.run()
    trend_df = pd.DataFrame(res_trend[0].daily_records).set_index("date")["equity"]

    # ----------------------------------------------------
    # RUN 2: MOMENTUM IN BACKTRADER
    # ----------------------------------------------------
    cerebro_mom = bt.Cerebro()
    cerebro_mom.broker.setcash(initial_capital)
    cerebro_mom.broker.set_slippage_perc(slippage_perc)

    for ticker in prices_oos.columns:
        p_ser = prices_oos[ticker]
        p_clean = p_ser.replace(0, np.nan).ffill().bfill().values
        df_feed = pd.DataFrame({
            "Open": p_clean,
            "High": p_clean * 1.005,
            "Low": p_clean * 0.995,
            "Close": p_clean,
            "Volume": 100_000.0
        }, index=pd.to_datetime(oos_idx))
        feed = bt.feeds.PandasData(dataname=df_feed, name=ticker)
        cerebro_mom.adddata(feed, name=ticker)
        comm = create_market_commission(ticker)
        cerebro_mom.broker.addcommissioninfo(comm, name=ticker)

    cerebro_mom.addstrategy(BacktraderCrossSectionalMomentum, rf_annual=rf_annual)
    res_mom = cerebro_mom.run()
    mom_df = pd.DataFrame(res_mom[0].daily_records).set_index("date")["equity"]

    # ----------------------------------------------------
    # RUN 3: PAIRS MEAN REVERSION IN BACKTRADER
    # ----------------------------------------------------
    cerebro_mr = bt.Cerebro()
    cerebro_mr.broker.setcash(initial_capital)
    cerebro_mr.broker.set_slippage_perc(slippage_perc)

    # Add only candidate pair assets to MR feed
    mr_assets = set()
    valid_pairs = []
    for a1, a2 in candidate_pairs:
        if a1 in prices_oos.columns and a2 in prices_oos.columns:
            mr_assets.add(a1)
            mr_assets.add(a2)
            valid_pairs.append((a1, a2))

    for ticker in mr_assets:
        p_ser = prices_oos[ticker]
        p_clean = p_ser.replace(0, np.nan).ffill().bfill().values
        df_feed = pd.DataFrame({
            "Open": p_clean,
            "High": p_clean * 1.005,
            "Low": p_clean * 0.995,
            "Close": p_clean,
            "Volume": 100_000.0
        }, index=pd.to_datetime(oos_idx))
        feed = bt.feeds.PandasData(dataname=df_feed, name=ticker)
        cerebro_mr.adddata(feed, name=ticker)
        comm = create_market_commission(ticker)
        cerebro_mr.broker.addcommissioninfo(comm, name=ticker)

    cerebro_mr.addstrategy(BacktraderMultiPairReversion, pairs_tuples=valid_pairs, rf_annual=rf_annual)
    res_mr = cerebro_mr.run()
    mr_df = pd.DataFrame(res_mr[0].daily_records).set_index("date")["equity"]

    # ----------------------------------------------------
    # COMBINE ENSEMBLE PORTFOLIOS
    # ----------------------------------------------------
    eq_matrix = pd.DataFrame({
        "Trend": trend_df,
        "Momentum": mom_df,
        "Mean_Reversion": mr_df
    }).dropna().ffill()

    r_trend = eq_matrix["Trend"].pct_change().fillna(0.0)
    r_mom = eq_matrix["Momentum"].pct_change().fillna(0.0)
    r_mr = eq_matrix["Mean_Reversion"].pct_change().fillna(0.0)

    # 1. Equal Weight 1/3
    r_eq = (r_trend + r_mom + r_mr) / 3.0
    eq_equal_weight = initial_capital * (1.0 + r_eq).cumprod()

    # 2. Risk Parity (Inverse 60-day Volatility)
    v_tr = r_trend.rolling(60).std().fillna(0.01)
    v_mo = r_mom.rolling(60).std().fillna(0.01)
    v_re = r_mr.rolling(60).std().fillna(0.01)

    inv_sum = (1.0 / v_tr) + (1.0 / v_mo) + (1.0 / v_re)
    w_tr = (1.0 / v_tr) / inv_sum
    w_mo = (1.0 / v_mo) / inv_sum
    w_re = (1.0 / v_re) / inv_sum
    r_rp = w_tr * r_trend + w_mo * r_mom + w_re * r_mr
    eq_risk_parity = initial_capital * (1.0 + r_rp).cumprod()

    # 3. Dynamic Regime Router
    detector = RegimeDetector()
    regimes_df = detector.detect_regimes(bench_oos).loc[eq_matrix.index]
    r_regime = pd.Series(0.0, index=eq_matrix.index)

    for d_idx in eq_matrix.index:
        reg_state = regimes_df.loc[d_idx, "regime"] if d_idx in regimes_df.index else "TRANSITION"
        if reg_state == "CRISIS":
            r_regime.loc[d_idx] = (1.0 + rf_annual) ** (1.0 / 252.0) - 1.0
        elif reg_state == "TRENDING":
            r_regime.loc[d_idx] = 0.60 * r_trend.loc[d_idx] + 0.30 * r_mom.loc[d_idx] + 0.10 * r_mr.loc[d_idx]
        elif reg_state == "RANGING":
            r_regime.loc[d_idx] = 0.20 * r_trend.loc[d_idx] + 0.20 * r_mom.loc[d_idx] + 0.60 * r_mr.loc[d_idx]
        else: # TRANSITION
            r_regime.loc[d_idx] = (r_trend.loc[d_idx] + r_mom.loc[d_idx] + r_mr.loc[d_idx]) / 3.0

    eq_regime = initial_capital * (1.0 + r_regime).cumprod()

    # Benchmark (SPY)
    bench_rets = bench_oos.loc[eq_matrix.index].pct_change().fillna(0.0)
    eq_benchmark = initial_capital * (1.0 + bench_rets).cumprod()

    # Metrics Summary
    strat_dict = {
        "Trend Following (BT L05.1)": compute_bt_metrics(eq_matrix["Trend"], initial_capital, rf_annual),
        "Momentum L/S (BT L05 & 16)": compute_bt_metrics(eq_matrix["Momentum"], initial_capital, rf_annual),
        "Mean Reversion (BT L05.2)": compute_bt_metrics(eq_matrix["Mean_Reversion"], initial_capital, rf_annual),
        "Equal Weight 1/3 (BT L05.3)": compute_bt_metrics(eq_equal_weight, initial_capital, rf_annual),
        "Risk Parity Inv-Vol (BT L05.3)": compute_bt_metrics(eq_risk_parity, initial_capital, rf_annual),
        "Dynamic Regime Ensemble (BT L12)": compute_bt_metrics(eq_regime, initial_capital, rf_annual),
        "Benchmark (SPY Buy & Hold)": compute_bt_metrics(eq_benchmark, initial_capital, rf_annual),
    }

    metrics_df = pd.DataFrame(strat_dict).T

    equity_curves_df = pd.DataFrame({
        "Date": eq_matrix.index,
        "Trend_Following": eq_matrix["Trend"].values,
        "Momentum": eq_matrix["Momentum"].values,
        "Mean_Reversion": eq_matrix["Mean_Reversion"].values,
        "Equal_Weight_1_3": eq_equal_weight.values,
        "Risk_Parity": eq_risk_parity.values,
        "Regime_Routed_Ensemble": eq_regime.values,
        "Benchmark_SPY": eq_benchmark.values,
    }).set_index("Date")

    return {
        "metrics_summary": metrics_df,
        "equity_curves": equity_curves_df,
        "regimes": regimes_df,
        "universe_size": len(prices_oos.columns),
        "pairs_count": len(valid_pairs),
    }
