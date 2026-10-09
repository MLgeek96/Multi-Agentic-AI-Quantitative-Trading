"""Small, dependency-free client for Binance public Spot market data."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from email.message import Message
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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

INTERVAL_MILLISECONDS = {
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "2h": 2 * 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "6h": 6 * 60 * 60_000,
    "8h": 8 * 60 * 60_000,
    "12h": 12 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


class BinanceAPIError(RuntimeError):
    """A public Binance request failed or returned an invalid response."""


@dataclass
class SimpleResponse:
    """Minimal response protocol used by tests and the urllib adapter."""

    body: bytes
    headers: Message

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> "SimpleResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None


class BinancePublicClient:
    """Read public candles without an API key.

    ``opener`` is injectable to make every network behavior deterministic in
    unit tests.  Production uses :func:`urllib.request.urlopen`.
    """

    def __init__(
        self,
        base_url: str = "https://data-api.binance.vision",
        *,
        timeout: float = 15.0,
        retries: int = 3,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.opener = opener

    def _get_json(self, path: str, params: dict[str, object] | None = None) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        request = Request(url, headers={"User-Agent": "crypto-quant-research/1.0"})
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, dict) and "code" in payload and int(payload["code"]) < 0:
                    raise BinanceAPIError(f"Binance error {payload['code']}: {payload.get('msg', '')}")
                return payload
            except HTTPError as error:
                last_error = error
                if error.code not in (418, 429) and error.code < 500:
                    break
                retry_after = error.headers.get("Retry-After") if error.headers else None
                delay = min(float(retry_after), 30.0) if retry_after else 2.0**attempt
            except (URLError, TimeoutError, json.JSONDecodeError) as error:
                last_error = error
                delay = 2.0**attempt
            if attempt + 1 < self.retries:
                time.sleep(delay)
        raise BinanceAPIError(f"GET {url} failed after {self.retries} attempts: {last_error}")

    def server_time(self) -> pd.Timestamp:
        payload = self._get_json("/api/v3/time")
        if not isinstance(payload, dict) or "serverTime" not in payload:
            raise BinanceAPIError("Server-time response is missing serverTime")
        return pd.to_datetime(int(payload["serverTime"]), unit="ms", utc=True)

    def listing_time(self, symbol: str) -> pd.Timestamp:
        payload = self._get_json(
            "/api/v3/klines",
            {"symbol": symbol.upper(), "interval": "1d", "startTime": 0, "limit": 1},
        )
        if not isinstance(payload, list) or not payload:
            raise BinanceAPIError(f"No daily candles returned for {symbol}")
        return pd.to_datetime(int(payload[0][0]), unit="ms", utc=True)

    def fetch_klines(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        start: pd.Timestamp,
        end: pd.Timestamp,
        closed_at: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Fetch ``[start, end)`` candles, paginating and keeping closed bars only."""

        if interval not in INTERVAL_MILLISECONDS:
            raise ValueError(f"Unsupported interval {interval!r}")
        start = _utc(start)
        end = _utc(end)
        if end <= start:
            raise ValueError("end must be later than start")
        interval_ms = INTERVAL_MILLISECONDS[interval]
        cursor = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        rows: list[list[object]] = []
        while cursor < end_ms:
            payload = self._get_json(
                "/api/v3/klines",
                {
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "startTime": cursor,
                    "endTime": end_ms - 1,
                    "limit": 1000,
                },
            )
            if not isinstance(payload, list):
                raise BinanceAPIError(f"Unexpected kline response for {symbol}")
            if not payload:
                break
            rows.extend(payload)
            next_cursor = int(payload[-1][0]) + interval_ms
            if next_cursor <= cursor:
                raise BinanceAPIError(f"Non-advancing kline page for {symbol}")
            cursor = next_cursor
            if len(payload) < 1000:
                break

        frame = pd.DataFrame(rows, columns=KLINE_COLUMNS)
        if frame.empty:
            raise BinanceAPIError(f"No {interval} candles returned for {symbol}")
        for column in KLINE_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
        cutoff = _utc(closed_at) if closed_at is not None else self.server_time()
        frame = frame.loc[frame["close_time"] <= cutoff].copy()
        frame.insert(0, "symbol", symbol.upper())
        if frame["open_time"].duplicated().any():
            raise BinanceAPIError(f"Duplicate {interval} candle timestamps for {symbol}")
        if not frame["open_time"].is_monotonic_increasing:
            raise BinanceAPIError(f"Unordered {interval} candles for {symbol}")
        return frame.reset_index(drop=True)


def _utc(value: pd.Timestamp | str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tz is None else timestamp.tz_convert("UTC")
