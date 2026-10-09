"""Small validated local configuration; no live execution option."""

from dataclasses import dataclass, fields
import json
from pathlib import Path

from .models import number

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AgentConfig:
    mode: str = "research"
    account_key: str = "crypto-research"
    execution_mode: str = "record_only"
    strategy_mode: str = "adaptive_trend"
    initial_equity_usdt: float = 100_000.0
    maximum_asset_weight: float = 0.4
    maximum_gross_exposure: float = 0.8
    cash_buffer: float = 0.02
    fee_buffer_bps: float = 15.0
    maximum_adv_participation: float = 0.001
    liquidity_days: int = 30
    maximum_drawdown: float = 0.25
    stop_loss_fraction: float = 0.1
    take_profit_fraction: float = 0.2
    hmm_training_days: int = 365
    daily_config_path: str = "config/daily_portfolio.json"
    state_path: str = "runtime/crypto_agents.sqlite"
    report_directory: str = "runs/agents"

    def __post_init__(self):
        if self.mode not in ("demo", "research") or self.execution_mode != "record_only":
            raise ValueError("only local demo/research and record_only execution are supported")
        if self.strategy_mode not in ("adaptive_trend", "hmm_experts") or not self.account_key:
            raise ValueError("invalid strategy or account key")
        for key in ("maximum_asset_weight", "maximum_gross_exposure", "maximum_adv_participation", "maximum_drawdown", "stop_loss_fraction"):
            value = getattr(self, key)
            number(value, key, 1e-12)
            if value > 1:
                raise ValueError(f"{key} cannot exceed one")
        number(self.cash_buffer, "cash_buffer")
        if self.cash_buffer >= 1:
            raise ValueError("cash buffer must be below one")
        number(self.fee_buffer_bps, "fee buffer")
        number(self.take_profit_fraction, "take profit", 1e-12)
        number(self.initial_equity_usdt, "initial_equity", 1e-12)
        if self.maximum_asset_weight > self.maximum_gross_exposure:
            raise ValueError("per-asset limit must not exceed gross limit")
        for name, lower in (("liquidity_days", 2), ("hmm_training_days", 60)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < lower:
                raise ValueError(f"{name} must be an integer >= {lower}")

    def path(self, name: str) -> Path:
        value = Path(getattr(self, name))
        return value if value.is_absolute() else ROOT / value


def load_config(path: str | Path) -> AgentConfig:
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    unknown = set(values) - {f.name for f in fields(AgentConfig)}
    if unknown:
        raise ValueError(f"unknown agent config fields: {sorted(unknown)}")
    return AgentConfig(**values)
