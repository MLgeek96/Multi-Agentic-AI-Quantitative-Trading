"""Rule baselines and walk-forward parameter selection helpers.

The attached strategy reference is translated into daily, close-known rules:
moving-average crossover, Bollinger mean reversion/breakout, and a staged
dynamic-grid proxy.  A ridge linear-regression baseline is included without a
scikit-learn dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable

import numpy as np
import pandas as pd

from .hmm_regime import HMMRegimeConfig, _rsi, performance_metrics


@dataclass(frozen=True)
class DevelopmentFold:
    name: str
    start: str
    end: str


def build_rule_signals(
    closes: pd.DataFrame,
    *,
    family: str,
    parameters: dict[str, object],
    volumes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build long/short signals for one transparent rule family."""

    closes = closes.astype(float).sort_index()
    records: list[pd.DataFrame] = []
    for symbol in closes.columns:
        close = closes[symbol]
        if family == "ma_crossover":
            fast = int(parameters["fast"])
            slow = int(parameters["slow"])
            signal = np.sign(close.rolling(fast).mean() - close.rolling(slow).mean())
            filter_name = str(parameters.get("filter", "none"))
            if filter_name in {"macd", "macd_volume"}:
                macd = close.ewm(span=12, adjust=False).mean() - close.ewm(
                    span=26, adjust=False
                ).mean()
                macd_line = macd.ewm(span=9, adjust=False).mean()
                signal = signal.where(
                    ((signal > 0) & (macd > macd_line))
                    | ((signal < 0) & (macd < macd_line)),
                    0.0,
                )
            if filter_name == "macd_volume":
                if volumes is None or symbol not in volumes:
                    raise ValueError("macd_volume filter requires matching daily volumes")
                volume = volumes[symbol].astype(float)
                signal = signal.where(volume > volume.shift(1).rolling(20).mean(), 0.0)
        elif family in {"bollinger_mean_reversion", "bollinger_breakout"}:
            window = int(parameters["window"])
            width = float(parameters["width"])
            middle = close.rolling(window).mean()
            deviation = close.rolling(window).std(ddof=0)
            z_score = (close - middle) / deviation.replace(0.0, np.nan)
            exit_z = float(parameters.get("exit_z", 0.25))
            signal = _bollinger_state_machine(
                z_score,
                width=width,
                exit_z=exit_z,
                breakout=family == "bollinger_breakout",
            )
        elif family == "dynamic_grid":
            center_window = int(parameters["center_window"])
            grid_step = float(parameters["grid_step"])
            levels = int(parameters["levels"])
            trend_threshold = float(parameters["trend_threshold"])
            center = close.rolling(center_window).mean()
            displacement = close / center - 1.0
            completed_steps = np.floor(displacement.abs() / grid_step).clip(upper=levels)
            signal = -np.sign(displacement) * completed_steps / levels
            trend_fast = close.rolling(int(parameters.get("trend_fast", 20))).mean()
            trend_slow = close.rolling(int(parameters.get("trend_slow", 100))).mean()
            trend_strength = (trend_fast / trend_slow - 1.0).abs()
            signal = signal.where(trend_strength < trend_threshold, 0.0)
        elif family == "momentum_vote":
            signal = _momentum_vote(close, parameters)
        else:
            raise ValueError(f"Unknown rule family {family!r}")
        records.append(
            pd.DataFrame(
                {
                    "date": close.index,
                    "symbol": symbol,
                    "strategy": family,
                    "signal": pd.Series(signal, index=close.index).fillna(0.0).astype(float),
                }
            )
        )
    return pd.concat(records, ignore_index=True)


def build_linear_regression_signals(
    closes: pd.DataFrame,
    *,
    training_days: int,
    retrain_days: int,
    ridge_penalty: float,
    volatility_threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit per-asset ridge regressions to next-day log returns walk-forward."""

    closes = closes.astype(float).sort_index()
    log_returns = np.log(closes).diff()
    feature_parts: list[pd.DataFrame] = []
    for symbol in closes.columns:
        close = closes[symbol]
        returns = log_returns[symbol]
        feature_parts.append(
            pd.DataFrame(
                {
                    f"{symbol}_return_1": returns,
                    f"{symbol}_return_5": np.log(close).diff(5),
                    f"{symbol}_return_20": np.log(close).diff(20),
                    f"{symbol}_volatility_20": returns.rolling(20).std(ddof=0),
                    f"{symbol}_sma_gap_5_20": close.rolling(5).mean()
                    / close.rolling(20).mean()
                    - 1.0,
                    f"{symbol}_sma_gap_20_100": close.rolling(20).mean()
                    / close.rolling(100).mean()
                    - 1.0,
                    f"{symbol}_rsi": _rsi(close, 14) / 100.0 - 0.5,
                },
                index=closes.index,
            )
        )
    features = pd.concat(feature_parts, axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    targets = log_returns.shift(-1).reindex(features.index)
    daily_volatility = log_returns.rolling(20).std(ddof=0).reindex(features.index)
    records: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    models: dict[str, tuple[np.ndarray, np.ndarray, float, np.ndarray]] = {}
    last_refit = -retrain_days

    for position in range(training_days, len(features)):
        date = features.index[position]
        if position - last_refit >= retrain_days:
            train_start = max(0, position - training_days)
            # Row position-1 predicts the return ending at the current close,
            # which is known when today's new forecast is formed.
            x_train = features.iloc[train_start:position]
            for symbol in closes.columns:
                y_train = targets[symbol].iloc[train_start:position]
                valid = y_train.notna() & x_train.notna().all(axis=1)
                x = x_train.loc[valid].to_numpy(dtype=float)
                y = y_train.loc[valid].to_numpy(dtype=float)
                location = x.mean(axis=0)
                scale = x.std(axis=0, ddof=0)
                scale = np.where(scale < 1e-8, 1.0, scale)
                standardized = (x - location) / scale
                y_mean = float(y.mean())
                penalty = np.eye(standardized.shape[1]) * ridge_penalty
                coefficients = np.linalg.solve(
                    standardized.T @ standardized + penalty,
                    standardized.T @ (y - y_mean),
                )
                models[symbol] = (location, scale, y_mean, coefficients)
                diagnostics.append(
                    {
                        "refit_date": date,
                        "symbol": symbol,
                        "training_start": x_train.index[0],
                        "training_observations": int(valid.sum()),
                        "coefficient_norm": float(np.linalg.norm(coefficients)),
                    }
                )
            last_refit = position

        observation = features.iloc[position].to_numpy(dtype=float)
        for symbol in closes.columns:
            location, scale, y_mean, coefficients = models[symbol]
            forecast = float(y_mean + ((observation - location) / scale) @ coefficients)
            threshold = volatility_threshold * float(daily_volatility.at[date, symbol])
            signal = 1 if forecast > threshold else -1 if forecast < -threshold else 0
            records.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "strategy": "linear_regression",
                    "signal": signal,
                    "forecast_next_log_return": forecast,
                    "forecast_threshold": threshold,
                }
            )
    return pd.DataFrame.from_records(records), pd.DataFrame.from_records(diagnostics)


def score_development_folds(
    portfolio: pd.DataFrame,
    folds: Iterable[DevelopmentFold],
) -> tuple[dict[str, float | int], pd.DataFrame]:
    """Score a candidate using only rolling development fold outcomes."""

    records: list[dict[str, object]] = []
    for fold in folds:
        metrics = performance_metrics(portfolio, start=fold.start, end=fold.end)
        records.append({"fold": fold.name, **metrics})
    frame = pd.DataFrame.from_records(records)
    sharpes = frame["sharpe_ratio_zero_risk_free"].astype(float)
    median_sharpe = float(sharpes.median())
    sharpe_dispersion = float(sharpes.std(ddof=0))
    worst_drawdown = float(frame["maximum_drawdown"].min())
    mean_turnover = float(frame["average_daily_turnover"].mean())
    mean_gross = float(frame["average_gross_exposure"].mean())
    activity_penalty = max(0.0, 0.05 - mean_gross) * 10.0
    robust_score = (
        median_sharpe
        - 0.25 * sharpe_dispersion
        - 0.50 * abs(worst_drawdown)
        - 0.50 * mean_turnover
        - activity_penalty
    )
    summary: dict[str, float | int] = {
        "robust_score": robust_score,
        "median_fold_sharpe": median_sharpe,
        "fold_sharpe_dispersion": sharpe_dispersion,
        "worst_fold_drawdown": worst_drawdown,
        "positive_return_folds": int(frame["total_return"].gt(0).sum()),
        "mean_daily_turnover": mean_turnover,
        "mean_gross_exposure": mean_gross,
    }
    return summary, frame


def _momentum_vote(close: pd.Series, parameters: dict[str, object]) -> pd.Series:
    macd_fast = int(parameters.get("macd_fast", 12))
    macd_slow = int(parameters.get("macd_slow", 26))
    macd_signal_window = int(parameters.get("macd_signal", 9))
    sma_fast = int(parameters["sma_fast"])
    sma_slow = int(parameters["sma_slow"])
    rsi_period = int(parameters.get("rsi_period", 14))
    rsi_long = float(parameters["rsi_long"])
    rsi_short = float(parameters["rsi_short"])
    minimum_votes = int(parameters["minimum_votes"])
    macd = close.ewm(span=macd_fast, adjust=False).mean() - close.ewm(
        span=macd_slow, adjust=False
    ).mean()
    macd_line = macd.ewm(span=macd_signal_window, adjust=False).mean()
    rsi = _rsi(close, rsi_period)
    votes = pd.DataFrame(
        {
            "macd": np.sign(macd - macd_line),
            "sma": np.sign(
                close.rolling(sma_fast).mean() - close.rolling(sma_slow).mean()
            ),
            "rsi": np.select([rsi >= rsi_long, rsi <= rsi_short], [1, -1], default=0),
        },
        index=close.index,
    )
    positive = votes.eq(1).sum(axis=1)
    negative = votes.eq(-1).sum(axis=1)
    return pd.Series(
        np.select(
            [
                (positive >= minimum_votes) & (positive > negative),
                (negative >= minimum_votes) & (negative > positive),
            ],
            [1, -1],
            default=0,
        ),
        index=close.index,
    )


def _bollinger_state_machine(
    z_score: pd.Series,
    *,
    width: float,
    exit_z: float,
    breakout: bool,
) -> pd.Series:
    values = np.zeros(len(z_score), dtype=float)
    current = 0.0
    for position, value in enumerate(z_score.to_numpy(dtype=float)):
        if not np.isfinite(value):
            current = 0.0
        elif breakout:
            if value >= width:
                current = 1.0
            elif value <= -width:
                current = -1.0
            elif current > 0 and value <= exit_z:
                current = 0.0
            elif current < 0 and value >= -exit_z:
                current = 0.0
        else:
            if value <= -width:
                current = 1.0
            elif value >= width:
                current = -1.0
            elif current > 0 and value >= -exit_z:
                current = 0.0
            elif current < 0 and value <= exit_z:
                current = 0.0
        values[position] = current
    return pd.Series(values, index=z_score.index)
