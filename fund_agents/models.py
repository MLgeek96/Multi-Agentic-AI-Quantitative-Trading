"""Signed sleeve holdings and linked target groups, valued in USD."""

from dataclasses import dataclass, field
import math

import pandas as pd

from crypto_agents.models import fingerprint, json_value


def finite(value, name, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")


def date(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tz is not None or str(stamp.date()) != value:
        raise ValueError("as_of and session labels must be YYYY-MM-DD dates")
    return stamp


@dataclass(frozen=True)
class PairSpec:
    asset1: str
    asset2: str
    calendar: str = "XNYS"
    currency: str = "USD"

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in (self.asset1, self.asset2, self.calendar, self.currency)) or self.asset1 == self.asset2:
            raise ValueError("pair needs two different assets, a calendar and a quote currency")

    @property
    def key(self):
        return f"{self.asset1}~{self.asset2}"


@dataclass(frozen=True)
class FundConfig:
    mode: str = "demo"
    account_key: str = "two-pm-demo"
    execution_mode: str = "record_only"
    crypto_budget_usd: float = 1_500_000.0
    pairs_budget_usd: float = 1_500_000.0
    momentum_reserve_usd: float = 1_500_000.0
    central_cash_usd: float = 500_000.0
    maximum_fund_gross: float = 0.8
    maximum_name_gross: float = 0.2
    maximum_drawdown: float = 0.25
    risk_envelope: str = "standard"
    soft_drawdown: float = 0.12
    soft_drawdown_scale: float = 0.50
    fee_buffer_bps: float = 15.0
    collateral_buffer: float = 0.02
    pairs_gross_fraction: float = 0.8
    pair_minimum_rows: int = 60
    formation_end: str = "2024-12-31"
    require_formation_qualification: bool = True
    entry_z: float = 1.25
    exit_z: float = 0.10
    stop_z: float = 3.50
    max_holding_sessions: int = 45
    kalman_q: float = 1e-5
    kalman_r: float = 1e-3
    crypto_config_path: str = "config/agents.demo.json"
    state_path: str = "runtime/fund_agents.demo.sqlite"
    report_directory: str = "runs/fund_agents/demo"
    pairs: tuple[PairSpec, ...] = field(default_factory=lambda: (PairSpec("V", "MA"),))

    def __post_init__(self) -> None:
        if self.mode not in ("demo", "research") or self.execution_mode != "record_only" or not self.account_key:
            raise ValueError("fund supports demo/research with record_only execution")
        if self.risk_envelope not in ("standard", "conservative", "aggressive"):
            raise ValueError("risk_envelope must be standard, conservative or aggressive")
        for name in ("crypto_budget_usd", "pairs_budget_usd"):
            finite(getattr(self, name), name, 1e-12)
        for name in ("momentum_reserve_usd", "central_cash_usd", "fee_buffer_bps"):
            finite(getattr(self, name), name, 0)
        for name in ("maximum_fund_gross", "maximum_name_gross", "maximum_drawdown", "pairs_gross_fraction",
                     "soft_drawdown", "soft_drawdown_scale"):
            finite(getattr(self, name), name, 1e-12)
            if getattr(self, name) > 1:
                raise ValueError(f"{name} cannot exceed one in the initial unlevered mandate")
        if self.soft_drawdown >= self.maximum_drawdown:
            raise ValueError("soft_drawdown must be strictly below maximum_drawdown")
        finite(self.collateral_buffer, "collateral_buffer", 0)
        if self.collateral_buffer >= 1 or not (0 < self.exit_z < self.entry_z < self.stop_z):
            raise ValueError("invalid collateral buffer or spread thresholds")
        for name in ("entry_z", "exit_z", "stop_z", "kalman_q", "kalman_r"):
            finite(getattr(self, name), name, 1e-12)
        for name, lower in (("pair_minimum_rows", 60), ("max_holding_sessions", 1)):
            value = getattr(self, name)
            if type(value) is not int or value < lower:
                raise ValueError(f"{name} must be an integer >= {lower}")
        date(self.formation_end)
        if type(self.require_formation_qualification) is not bool or not self.pairs or len({p.key for p in self.pairs}) != len(self.pairs):
            raise ValueError("invalid formation switch or duplicate/empty pairs")

    @property
    def initial_nav_usd(self) -> float:
        return self.crypto_budget_usd + self.pairs_budget_usd + self.momentum_reserve_usd + self.central_cash_usd


@dataclass(frozen=True)
class PhantomBook:
    """Shadow accounting of unscaled PM proposals vs. risk-approved exposure."""

    proposed_gross_usd: float
    approved_gross_usd: float
    throttled_gross_usd: float
    preserved_buffer_usd: float
    envelope_tier: str
    soft_throttle_active: bool
    sleeve_throttled_usd: dict[str, float]



@dataclass(frozen=True)
class Holding:
    pm: str
    group: str
    symbol: str
    units: float
    entry_price_usd: float
    opened_on: str | None = None

    def __post_init__(self):
        if self.pm not in ("crypto", "pairs") or not self.group or not self.symbol:
            raise ValueError("unknown PM or empty holding identity")
        finite(self.units, "signed units")
        finite(self.entry_price_usd, "entry price", 1e-12)
        if self.pm == "crypto" and self.units < 0:
            raise ValueError("the current Crypto PM supports long-only Spot")
        if self.pm == "pairs" and self.units != 0 and self.opened_on is None:
            raise ValueError("open pairs need an opened_on session for time stops")
        if self.opened_on is not None:
            date(self.opened_on)


@dataclass(frozen=True)
class FundSnapshot:
    as_of: str
    crypto_cash_usd: float
    pairs_cash_usd: float
    momentum_cash_usd: float
    central_cash_usd: float
    peak_nav_usd: float
    holdings: tuple[Holding, ...] = ()
    usdt_to_usd: float = 1.0
    fx_to_usd: tuple[tuple[str, float], ...] = (("USD", 1.0),)
    fx_as_of: str | None = None
    valuation_note: str = "USDT valued at USD 1 by explicit paper-account convention"

    def __post_init__(self):
        date(self.as_of)
        for name in ("crypto_cash_usd", "pairs_cash_usd", "momentum_cash_usd", "central_cash_usd"):
            finite(getattr(self, name), name, 0)
        finite(self.peak_nav_usd, "peak NAV", 1e-12)
        finite(self.usdt_to_usd, "USDT conversion", 1e-12)
        if self.fx_as_of is not None:
            date(self.fx_as_of)
        if len(dict(self.fx_to_usd)) != len(self.fx_to_usd) or dict(self.fx_to_usd).get("USD") != 1:
            raise ValueError("FX quotes must be unique with USD=1")
        for currency, rate in self.fx_to_usd:
            finite(rate, currency + " FX conversion", 1e-12)
        identities = [(h.pm, h.group, h.symbol) for h in self.holdings]
        if len(set(identities)) != len(identities) or any(h.opened_on and h.opened_on > self.as_of for h in self.holdings):
            raise ValueError("duplicate holdings or future opening session")

    @classmethod
    def initial(cls, config, as_of):
        return cls(as_of, config.crypto_budget_usd, config.pairs_budget_usd,
                   config.momentum_reserve_usd, config.central_cash_usd, config.initial_nav_usd)

    def group_holdings(self, pm, group):
        return tuple(h for h in self.holdings if (h.pm, h.group) == (pm, group))

    def units(self, pm, group, symbol):
        return next((h.units for h in self.group_holdings(pm, group) if h.symbol == symbol), 0.0)

    def fx(self, currency):
        if currency != "USD" and self.fx_as_of != self.as_of:
            raise ValueError("non-USD pairs require FX quotes dated at the fund as_of")
        if currency not in dict(self.fx_to_usd):
            raise ValueError(f"missing {currency} to USD conversion")
        return dict(self.fx_to_usd)[currency]


@dataclass(frozen=True)
class TargetLeg:
    symbol: str
    units: float
    price_usd: float

    def __post_init__(self):
        if not self.symbol:
            raise ValueError("empty target symbol")
        finite(self.units, "target signed units")
        finite(self.price_usd, "USD reference price", 1e-12)


@dataclass(frozen=True)
class TargetGroup:
    pm: str
    group: str
    as_of: str
    signal_session: str
    legs: tuple[TargetLeg, ...]
    reason: str
    hedge_beta: float | None = None
    actionable: bool = True

    def __post_init__(self):
        date(self.as_of)
        date(self.signal_session)
        if self.signal_session > self.as_of or not self.group or self.pm not in ("crypto", "pairs"):
            raise ValueError("invalid target identity or future signal session")
        if not self.legs or len({l.symbol for l in self.legs}) != len(self.legs):
            raise ValueError("target group needs unique legs")
        if self.pm == "crypto" and (len(self.legs) != 1 or self.legs[0].units < 0):
            raise ValueError("Crypto PM target must be one long/cash leg")
        if self.pm == "pairs":
            if len(self.legs) != 2 or self.hedge_beta is None:
                raise ValueError("pair targets must carry both legs and their hedge beta")
            finite(self.hedge_beta, "hedge beta")
            if any(l.units != 0 for l in self.legs) and self.actionable:
                first, second = (l.units * l.price_usd for l in self.legs)
                if abs(first) < 1e-12 or not math.isclose(second, -self.hedge_beta * first, abs_tol=1e-6, rel_tol=1e-8):
                    raise ValueError("pair target legs do not preserve the signed dollar hedge ratio")

    @property
    def gross_usd(self):
        return sum(abs(l.units * l.price_usd) for l in self.legs)

    @property
    def identity(self):
        return fingerprint(self)


@dataclass(frozen=True)
class PMProposal:
    pm: str
    status: str
    groups: tuple[TargetGroup, ...]
    diagnostics: dict
    evidence_sha256: str

    def __post_init__(self):
        if self.pm not in ("crypto", "pairs") or self.status not in ("READY", "INPUT_HOLD"):
            raise ValueError("invalid PM proposal")
        if any(g.pm != self.pm for g in self.groups) or len({g.group for g in self.groups}) != len(self.groups):
            raise ValueError("PM group identities must be unique and match their owner")
        # Enforce finite, serializable evidence before it reaches AI or persistence.
        fingerprint(json_value(self.diagnostics))
