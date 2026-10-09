"""Immutable contracts and reproducible content identities."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import math

import pandas as pd


def json_value(value):
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    return value


def canonical_json(value) -> str:
    return json.dumps(json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def number(value, label: str, lower=0.0):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < lower:
        raise ValueError(f"{label} must be finite and >= {lower}")


def session(value: str):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tz is not None or stamp != stamp.normalize():
        raise ValueError("sessions must be ISO dates at UTC midnight")


@dataclass(frozen=True)
class Bar:
    date: str
    close: float
    quote_volume: float

    def __post_init__(self):
        session(self.date)
        number(self.close, "close", 1e-12)
        number(self.quote_volume, "quote_volume")


@dataclass(frozen=True)
class Dataset:
    symbol: str
    bars: tuple[Bar, ...]
    quality_status: str
    failed_checks: tuple[str, ...]
    source_sha256: str

    def __post_init__(self):
        if self.quality_status not in ("PASS", "FAIL"):
            raise ValueError("invalid quality status")
        if self.quality_status == "PASS" and self.failed_checks:
            raise ValueError("PASS cannot carry failed checks")
        if self.bars:
            dates = [b.date for b in self.bars]
            if dates != sorted(set(dates)):
                raise ValueError("snapshot bars must be ordered and unique")


@dataclass(frozen=True)
class MarketSnapshot:
    as_of: str
    datasets: tuple[Dataset, ...]
    basis: str
    source: str
    audit_sha256: str

    def __post_init__(self):
        session(self.as_of)
        if self.basis not in ("SYNTHETIC_DEMO", "LOCAL_SPOT_RESEARCH"):
            raise ValueError("unknown data basis")
        if not self.datasets or len({d.symbol for d in self.datasets}) != len(self.datasets):
            raise ValueError("snapshot must contain unique symbols")
        if any(b.date > self.as_of for d in self.datasets for b in d.bars):
            raise ValueError("snapshot contains future bars")

    @property
    def quality_pass(self):
        return all(d.quality_status == "PASS" and d.bars and d.bars[-1].date == self.as_of for d in self.datasets)

    def closes(self) -> pd.DataFrame:
        series = [pd.Series([b.close for b in d.bars], index=pd.to_datetime([b.date for b in d.bars], utc=True), name=d.symbol)
                  for d in self.datasets]
        return pd.concat(series, axis=1).sort_index()

    def dataset(self, symbol: str) -> Dataset:
        return next(d for d in self.datasets if d.symbol == symbol)


@dataclass(frozen=True)
class Holding:
    symbol: str
    units: float
    entry_price: float

    def __post_init__(self):
        number(self.units, "units")
        number(self.entry_price, "entry_price", 1e-12)


@dataclass(frozen=True)
class PortfolioSnapshot:
    as_of: str
    cash_usdt: float
    holdings: tuple[Holding, ...] = ()
    peak_equity_usdt: float = 100_000.0

    def __post_init__(self):
        session(self.as_of)
        number(self.cash_usdt, "cash")
        number(self.peak_equity_usdt, "peak_equity", 1e-12)
        if len({h.symbol for h in self.holdings}) != len(self.holdings):
            raise ValueError("duplicate holdings")

    def units(self, symbol):
        return next((h.units for h in self.holdings if h.symbol == symbol), 0.0)

    def equity(self, market: MarketSnapshot):
        return self.cash_usdt + sum(h.units * market.dataset(h.symbol).bars[-1].close for h in self.holdings)


@dataclass(frozen=True)
class RegimeEstimate:
    as_of: str
    routing: tuple[tuple[str, float], ...]
    model: str
    trained_through: str | None = None
    high_volatility_probability: float | None = None
    model_sha256: str | None = None
    interpretation: str = "Declared routing policy, not calibrated regime confidence"

    def __post_init__(self):
        if set(dict(self.routing)) != {"trend", "mean_revert", "crisis"} or len(self.routing) != 3:
            raise ValueError("routing needs exactly three specialists")
        for _, value in self.routing:
            number(value, "probability")
        if not math.isclose(sum(v for _, v in self.routing), 1.0, abs_tol=1e-8):
            raise ValueError("routing must sum to one")
        if self.trained_through is not None and self.trained_through >= self.as_of:
            raise ValueError("regime training must end before inference")


@dataclass(frozen=True)
class ExpertSignal:
    symbol: str
    expert: str
    exposure: float | None
    annualized_volatility: float | None
    reason: str
    parameters: tuple[tuple[str, float | int | None], ...] = ()

    def __post_init__(self):
        if self.exposure is not None:
            number(self.exposure, "exposure")
            if self.exposure > 1:
                raise ValueError("expert exposure cannot exceed one")
        if self.annualized_volatility is not None:
            number(self.annualized_volatility, "volatility")


@dataclass(frozen=True)
class BlendedSignal:
    symbol: str
    exposure: float | None
    annualized_volatility: float | None


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    as_of: str
    symbol: str
    side: str
    units: float
    reference_price: float
    source_key: str
    reason: str

    def __post_init__(self):
        number(self.units, "order units", 1e-12)
        number(self.reference_price, "reference price", 1e-12)
        if self.side not in ("BUY", "SELL"):
            raise ValueError("invalid order side")
        values = (self.as_of, self.symbol, self.side, self.units, self.reference_price, self.source_key, self.reason)
        if self.intent_id != fingerprint(values):
            raise ValueError("intent identity does not match contents")

    @classmethod
    def create(cls, as_of, symbol, side, units, price, source_key, reason):
        values = (as_of, symbol, side, float(units), float(price), source_key, reason)
        return cls(fingerprint(values), *values)

    def resized(self, units):
        return self.create(self.as_of, self.symbol, self.side, units, self.reference_price, self.source_key, self.reason)


@dataclass(frozen=True)
class OrderReview:
    proposed: OrderIntent
    outcome: str
    approved: OrderIntent | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RiskState:
    peak_equity_usdt: float
    breaker_latched: bool = False
    last_session: str | None = None

    def __post_init__(self):
        number(self.peak_equity_usdt, "risk peak equity", 1e-12)
        if not isinstance(self.breaker_latched, bool):
            raise ValueError("breaker state must be boolean")
        if self.last_session is not None:
            session(self.last_session)


@dataclass(frozen=True)
class RiskDecision:
    decision_id: str
    as_of: str
    account_key: str
    reviews: tuple[OrderReview, ...]
    state: RiskState
    alerts: tuple[str, ...]
    marked_equity_usdt: float | None

    def __post_init__(self):
        for review in self.reviews:
            if review.outcome not in ("PASS", "REDUCE", "REJECT") or (review.approved is None) != (review.outcome == "REJECT"):
                raise ValueError("invalid approval outcome")
            if review.approved is not None:
                before, after = review.proposed, review.approved
                if before.as_of != self.as_of or after.units > before.units:
                    raise ValueError("approval cannot increase units or change date")
                for key in ("as_of", "symbol", "side", "reference_price", "source_key", "reason"):
                    if getattr(before, key) != getattr(after, key):
                        raise ValueError("risk may resize, but cannot substitute an intent")
                if (review.outcome == "PASS") != (before.units == after.units):
                    raise ValueError("risk outcome must reflect resizing")
        ids = [i.intent_id for i in self.approved]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate approvals")

    @property
    def approved(self):
        return tuple(r.approved for r in self.reviews if r.approved is not None)


@dataclass(frozen=True)
class ExecutionReceipt:
    intent_id: str
    status: str
    filled_units: float = 0.0
    exchange_order_id: None = None

    def __post_init__(self):
        if self.status not in ("RECORDED_NOT_EXECUTED", "ALREADY_RECORDED_NOT_EXECUTED") or self.filled_units != 0 or self.exchange_order_id is not None:
            raise ValueError("record-only receipts cannot contain fills or exchange order IDs")
