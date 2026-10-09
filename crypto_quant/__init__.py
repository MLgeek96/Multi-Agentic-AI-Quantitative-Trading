"""Research-only pattern and momentum strategies for cryptocurrency markets."""

from .pattern_momentum import (
    DEFAULT_CONFIGS,
    BacktestResult,
    StrategyConfig,
    backtest,
    build_candidates,
    build_structure_bars,
    load_ohlcv,
    performance_metrics,
    validate_audit_log,
)

__all__ = [
    "DEFAULT_CONFIGS",
    "BacktestResult",
    "StrategyConfig",
    "backtest",
    "build_candidates",
    "build_structure_bars",
    "load_ohlcv",
    "performance_metrics",
    "validate_audit_log",
]
