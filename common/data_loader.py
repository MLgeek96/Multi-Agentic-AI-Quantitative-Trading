"""
Data Loader and Preprocessing Module for Econometric Pairs Trading
Handles retrieval, caching, adjustment, and cleaning of financial time series.
"""
import os
import pandas as pd
import numpy as np
import yfinance as yf
from typing import List, Tuple, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class DataLoader:
    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch_price_data(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        use_cache: bool = True,
        cache_filename: str = "asset_prices.csv"
    ) -> pd.DataFrame:
        """
        Fetches adjusted close prices for given tickers between start_date and end_date.
        Uses local CSV caching to ensure reproducible and fast repeated runs.
        """
        cache_path = os.path.join(self.cache_dir, cache_filename)

        if use_cache and os.path.exists(cache_path):
            logger.info(f"Loading cached price data from {cache_path}")
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            missing_tickers = [t for t in tickers if t not in df.columns]
            start_ts = pd.Timestamp(start_date)
            end_ts = pd.Timestamp(end_date)
            covers_date_range = (df.index[0] <= start_ts + pd.Timedelta(days=10)) and (df.index[-1] >= min(end_ts - pd.Timedelta(days=10), pd.Timestamp.now()))
            if not missing_tickers and covers_date_range:
                mask = (df.index >= start_ts) & (df.index <= end_ts)
                return df.loc[mask]
            else:
                if missing_tickers:
                    logger.warning(f"Cache missing tickers: {missing_tickers}. Re-downloading...")
                if not covers_date_range:
                    logger.warning(f"Cache date range [{df.index[0].date()} to {df.index[-1].date()}] does not cover [{start_date} to {end_date}]. Re-downloading...")

        logger.info(f"Downloading historical data for {len(tickers)} tickers from {start_date} to {end_date} via yfinance...")
        # Download data
        raw_data = yf.download(
            tickers=tickers,
            start=start_date,
            end=end_date,
            auto_adjust=True,
            progress=False
        )

        if raw_data.empty:
            raise ValueError("No data returned from yfinance. Please check network connection or ticker symbols.")

        # Handle yfinance multi-index columns
        if isinstance(raw_data.columns, pd.MultiIndex):
            if "Close" in raw_data.columns.levels[0]:
                prices = raw_data["Close"]
            else:
                prices = raw_data.xs("Close", axis=1, level=0, drop_level=True)
        else:
            prices = raw_data[["Close"]] if "Close" in raw_data else raw_data

        # Clean column names
        prices.columns = [str(c).upper() for c in prices.columns]

        # Forward fill small missing gaps (e.g. holiday mismatches), then drop remaining NaNs
        prices = prices.ffill().bfill().dropna(how="all")

        # Save to cache
        prices.to_csv(cache_path)
        logger.info(f"Saved cleaned price data to {cache_path} (Shape: {prices.shape})")

        return prices

    def fetch_benchmark_data(
        self,
        benchmark_ticker: str = "SPY",
        start_date: str = "2019-01-01",
        end_date: str = "2025-01-01",
        use_cache: bool = True
    ) -> pd.Series:
        """
        Fetches adjusted close prices for market benchmark (e.g. SPY).
        """
        df = self.fetch_price_data(
            tickers=[benchmark_ticker],
            start_date=start_date,
            end_date=end_date,
            use_cache=use_cache,
            cache_filename=f"benchmark_{benchmark_ticker}.csv"
        )
        if benchmark_ticker in df.columns:
            return df[benchmark_ticker]
        return df.iloc[:, 0]

    def split_in_out_sample(
        self,
        prices: pd.DataFrame,
        in_sample_end: str,
        out_of_sample_start: str
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Splits price dataframe into In-Sample (formation) and Out-of-Sample (trading) periods.
        """
        in_sample = prices.loc[:pd.Timestamp(in_sample_end)].copy()
        out_of_sample = prices.loc[pd.Timestamp(out_of_sample_start):].copy()

        logger.info(f"In-Sample window: {in_sample.index[0].date()} to {in_sample.index[-1].date()} ({len(in_sample)} days)")
        logger.info(f"Out-of-Sample window: {out_of_sample.index[0].date()} to {out_of_sample.index[-1].date()} ({len(out_of_sample)} days)")

        return in_sample, out_of_sample
