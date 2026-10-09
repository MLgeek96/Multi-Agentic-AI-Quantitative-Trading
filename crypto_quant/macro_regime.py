"""Macro, relationship, and volume features for regime research."""

from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd


KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]


def load_extended_daily_futures(
    hourly_path: str | Path,
    *,
    monthly_daily_directory: str | Path,
    daily_directory: str | Path,
) -> pd.DataFrame:
    """Combine the checked 2020-2025 hourly file with checked 2026 daily archives."""

    hourly = pd.read_csv(hourly_path, parse_dates=["open_time"])
    hourly["open_time"] = pd.to_datetime(hourly["open_time"], utc=True)
    hourly = hourly.set_index("open_time").sort_index()
    aggregate = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "quote_volume": "sum",
        "trade_count": "sum",
        "taker_buy_base_volume": "sum",
        "taker_buy_quote_volume": "sum",
    }
    local = hourly.resample("1D", closed="left", label="left").agg(aggregate)
    count = hourly["close"].resample("1D", closed="left", label="left").count()
    local["source_bar_count"] = count
    local.loc[count.ne(24), list(aggregate)] = np.nan

    archives = [
        *sorted(Path(monthly_daily_directory).glob("*.zip")),
        *sorted(Path(daily_directory).glob("*.zip")),
    ]
    archive_frames = [_read_checked_archive(path) for path in archives]
    if not archive_frames:
        raise FileNotFoundError("No 2026 daily archives were found")
    extended = pd.concat(archive_frames, ignore_index=True)
    extended = extended.set_index("open_time").sort_index()
    extended = extended[list(aggregate)].apply(pd.to_numeric, errors="raise")
    extended["source_bar_count"] = 24
    combined = pd.concat([local, extended]).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined.dropna(subset=["close"])


def load_fred_levels(directory: str | Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Load downloaded FRED series and align last-known levels to crypto days."""

    series: list[pd.Series] = []
    for name in ("SP500", "NASDAQCOM", "VIXCLS", "DGS10", "DFF"):
        frame = pd.read_csv(Path(directory) / f"{name}.csv", na_values=["."])
        frame["observation_date"] = pd.to_datetime(
            frame["observation_date"], utc=True
        )
        value = pd.to_numeric(frame[name], errors="coerce")
        series.append(pd.Series(value.to_numpy(), index=frame["observation_date"], name=name))
    levels = pd.concat(series, axis=1).sort_index()
    return levels.reindex(index).ffill()


def build_macro_volume_features(
    markets: dict[str, pd.DataFrame],
    macro_levels: pd.DataFrame,
    *,
    macro_lag_days: int = 1,
    relationship_window: int = 60,
    volume_window: int = 20,
) -> pd.DataFrame:
    """Create stationary macro, relationship, volume, and order-flow features."""

    closes = pd.DataFrame({symbol: frame["close"] for symbol, frame in markets.items()})
    crypto_returns = np.log(closes).diff()
    macro = pd.DataFrame(index=closes.index)
    macro["sp500_return"] = np.log(macro_levels["SP500"]).diff()
    macro["nasdaq_return"] = np.log(macro_levels["NASDAQCOM"]).diff()
    macro["vix_change"] = np.log(macro_levels["VIXCLS"]).diff()
    macro["dgs10_change"] = macro_levels["DGS10"].diff()
    macro["fed_funds_change"] = macro_levels["DFF"].diff()
    # Publication/market-close conservatism: yesterday's macro observation is
    # the newest value allowed in today's decision.
    macro = macro.shift(macro_lag_days)

    parts = [macro]
    unlagged_sp500 = np.log(macro_levels["SP500"]).diff()
    unlagged_nasdaq = np.log(macro_levels["NASDAQCOM"]).diff()
    unlagged_yield = macro_levels["DGS10"].diff()
    for symbol, market in markets.items():
        prior_volume = market["volume"].shift(1).rolling(volume_window).median()
        volume_surprise = np.log(market["volume"] / prior_volume.replace(0.0, np.nan))
        taker_imbalance = (
            2.0 * market["taker_buy_base_volume"] / market["volume"].replace(0.0, np.nan)
            - 1.0
        )
        features = pd.DataFrame(index=closes.index)
        features[f"{symbol}_volume_surprise"] = volume_surprise
        features[f"{symbol}_taker_buy_imbalance"] = taker_imbalance
        features[f"{symbol}_flow_mean_5"] = taker_imbalance.rolling(5).mean()
        # These rolling features explicitly measure whether the relationships
        # are positive or inverse instead of imposing a permanent sign.
        features[f"{symbol}_corr_sp500"] = crypto_returns[symbol].rolling(
            relationship_window
        ).corr(unlagged_sp500).shift(1)
        features[f"{symbol}_corr_nasdaq"] = crypto_returns[symbol].rolling(
            relationship_window
        ).corr(unlagged_nasdaq).shift(1)
        features[f"{symbol}_corr_dgs10"] = crypto_returns[symbol].rolling(
            relationship_window
        ).corr(unlagged_yield).shift(1)
        parts.append(features)
    return pd.concat(parts, axis=1).replace([np.inf, -np.inf], np.nan)


def walk_forward_macro_forecasts(
    closes: pd.DataFrame,
    features: pd.DataFrame,
    *,
    training_days: int,
    retrain_days: int,
    ridge_penalty: float,
    volatility_threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimate next-day returns and changing macro coefficient signs."""

    closes = closes.astype(float).sort_index()
    log_returns = np.log(closes).diff()
    aligned = features.reindex(closes.index).replace([np.inf, -np.inf], np.nan).dropna()
    targets = log_returns.shift(-1).reindex(aligned.index)
    daily_volatility = log_returns.rolling(20).std(ddof=0).reindex(aligned.index)
    models: dict[str, tuple[np.ndarray, np.ndarray, float, np.ndarray]] = {}
    records: list[dict[str, object]] = []
    coefficients: list[dict[str, object]] = []
    last_refit = -retrain_days

    for position in range(training_days, len(aligned)):
        date = aligned.index[position]
        if position - last_refit >= retrain_days:
            start = max(0, position - training_days)
            x_frame = aligned.iloc[start:position]
            for symbol in closes.columns:
                y_series = targets[symbol].iloc[start:position]
                valid = y_series.notna() & x_frame.notna().all(axis=1)
                x = x_frame.loc[valid].to_numpy(dtype=float)
                y = y_series.loc[valid].to_numpy(dtype=float)
                location = x.mean(axis=0)
                scale = x.std(axis=0, ddof=0)
                scale = np.where(scale < 1e-8, 1.0, scale)
                standardized = (x - location) / scale
                y_mean = float(y.mean())
                penalty = np.eye(standardized.shape[1]) * ridge_penalty
                beta = np.linalg.solve(
                    standardized.T @ standardized + penalty,
                    standardized.T @ (y - y_mean),
                )
                models[symbol] = (location, scale, y_mean, beta)
                for feature, coefficient in zip(aligned.columns, beta):
                    coefficients.append(
                        {
                            "refit_date": date,
                            "symbol": symbol,
                            "feature": feature,
                            "standardized_coefficient": float(coefficient),
                        }
                    )
            last_refit = position

        observation = aligned.iloc[position].to_numpy(dtype=float)
        for symbol in closes.columns:
            location, scale, y_mean, beta = models[symbol]
            forecast = float(y_mean + ((observation - location) / scale) @ beta)
            threshold = volatility_threshold * float(daily_volatility.at[date, symbol])
            records.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "forecast": forecast,
                    "threshold": threshold,
                    "forecast_signal": 1 if forecast > threshold else -1 if forecast < -threshold else 0,
                }
            )
    return pd.DataFrame.from_records(records), pd.DataFrame.from_records(coefficients)


def combine_regime_signals(
    regimes: pd.DataFrame,
    high_signals: pd.DataFrame,
    low_signals: pd.DataFrame | None,
    forecasts: pd.DataFrame | None,
    *,
    confirmation: str,
) -> pd.DataFrame:
    """Route technical signals by regime and optionally require ridge agreement."""

    high = high_signals.set_index(["date", "symbol"])["signal"]
    low = (
        low_signals.set_index(["date", "symbol"])["signal"]
        if low_signals is not None
        else pd.Series(dtype=float)
    )
    forecast = (
        forecasts.set_index(["date", "symbol"])["forecast_signal"]
        if forecasts is not None
        else pd.Series(dtype=float)
    )
    symbols = sorted(high_signals["symbol"].unique())
    records: list[dict[str, object]] = []
    for date, regime_row in regimes.iterrows():
        regime = str(regime_row["regime"])
        for symbol in symbols:
            key = (date, symbol)
            base = float(high.get(key, 0.0)) if regime == "high_volatility" else float(low.get(key, 0.0))
            forecast_signal = float(forecast.get(key, 0.0))
            if confirmation == "agreement" and base != 0:
                signal = base if np.sign(base) == np.sign(forecast_signal) else 0.0
            elif confirmation == "soft" and base != 0:
                signal = base if np.sign(base) == np.sign(forecast_signal) else 0.5 * base
            elif confirmation == "none":
                signal = base
            else:
                signal = base if base == 0 else 0.0
            records.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "regime": regime,
                    "high_volatility_probability": regime_row["high_volatility_probability"],
                    "strategy": "combined_macro_regime",
                    "base_signal": base,
                    "forecast_signal": forecast_signal,
                    "signal": signal,
                }
            )
    return pd.DataFrame.from_records(records)


def _read_checked_archive(path: Path) -> pd.DataFrame:
    checksum_path = Path(f"{path}.CHECKSUM")
    if not checksum_path.exists():
        raise FileNotFoundError(f"Missing checksum for {path}")
    expected = checksum_path.read_text(encoding="utf-8").split()[0].lower()
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"Checksum mismatch for {path}")
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"Expected one CSV in {path}")
        with archive.open(names[0]) as handle:
            frame = pd.read_csv(handle, header=None, names=KLINE_COLUMNS, dtype=str)
    frame = frame.loc[frame["open_time"].str.lower() != "open_time"].copy()
    for column in KLINE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    open_raw = frame["open_time"].astype("int64")
    close_raw = frame["close_time"].astype("int64")
    unit = "us" if open_raw.abs().median() >= 100_000_000_000_000 else "ms"
    frame["open_time"] = pd.to_datetime(open_raw, unit=unit, utc=True)
    frame["close_time"] = pd.to_datetime(close_raw, unit=unit, utc=True)
    return frame
