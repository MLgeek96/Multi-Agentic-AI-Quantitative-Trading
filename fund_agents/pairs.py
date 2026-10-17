"""Adapt the teammate's quantitative engine into a daily Pairs PM."""

import math

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from .evidence import fingerprint

from .models import PMProposal, TargetGroup, TargetLeg, date
from .strategy import strategy_evidence
from .vendor.pairs_trading.forecasting_engine import ForecastingEngine
from .vendor.pairs_trading.pair_selection import PairSelector


def clean_evidence(value):
    """Undefined model diagnostics are null, never invented zero metrics."""
    if isinstance(value, dict):
        return {k: clean_evidence(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_evidence(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


class PairsPM:
    def __init__(self, config):
        self.config = config
        self.engine = ForecastingEngine(entry_z=config.entry_z, exit_z=config.exit_z,
                                        stop_loss_z=config.stop_z, kalman_q=config.kalman_q,
                                        kalman_r=config.kalman_r)

    def propose(self, prices, snapshot, *, source_sha256):
        cfg, as_of = self.config, date(snapshot.as_of)
        try:
            strategy = strategy_evidence(cfg)
            if not isinstance(prices.index, pd.DatetimeIndex) or prices.index.tz is not None:
                raise ValueError("pairs prices need timezone-free exchange session dates")
            if prices.index.hasnans or prices.index.has_duplicates or not prices.index.is_monotonic_increasing or any(prices.index != prices.index.normalize()):
                raise ValueError("pairs session dates must be valid, unique, ordered and at midnight")
            if prices.columns.has_duplicates:
                raise ValueError("pairs price columns must be unique")
            selected = prices.loc[prices.index <= as_of]
            if selected.empty:
                raise ValueError("no pairs prices at or before as_of")
            allowed = {(spec.key, symbol) for spec in cfg.pairs for symbol in (spec.asset1, spec.asset2)}
            if any((h.group, h.symbol) not in allowed for h in snapshot.holdings if h.pm == "pairs"):
                raise ValueError("pair holdings are outside the configured mandate")
            groups, updates = [], []
            for spec in cfg.pairs:
                calendar = xcals.get_calendar(spec.calendar, start=str((selected.index[0] - pd.Timedelta(days=14)).date()),
                                              end=str((as_of + pd.Timedelta(days=32)).date()))
                expected = calendar.date_to_session(as_of, direction="previous")
                columns = [spec.asset1, spec.asset2]
                if any(symbol not in selected for symbol in columns):
                    raise ValueError(f"{spec.key}: missing price column")
                pair = selected[columns].loc[:expected]
                first = pair.dropna().index.min()
                if pd.isna(first):
                    raise ValueError(f"{spec.key}: no common prices")
                sessions = calendar.sessions_in_range(first, expected)
                pair = pair.reindex(sessions)
                values = pair.to_numpy(dtype=float)
                if len(pair) < cfg.pair_minimum_rows or not np.isfinite(values).all() or (values <= 0).any():
                    raise ValueError(f"{spec.key}: insufficient, missing or invalid session prices; no gap filling")
                fx = snapshot.fx(spec.currency)
                current = {symbol: snapshot.units("pairs", spec.key, symbol) for symbol in columns}
                holdings = snapshot.group_holdings("pairs", spec.key)
                if bool(current[spec.asset1]) != bool(current[spec.asset2]):
                    raise ValueError(f"{spec.key}: supplied account has an unhedged single leg")
                opened = {h.opened_on for h in holdings if h.units != 0}
                if len(opened) > 1:
                    raise ValueError(f"{spec.key}: pair legs have different opening sessions")
                if opened and not calendar.is_session(pd.Timestamp(next(iter(opened)))):
                    raise ValueError(f"{spec.key}: opened_on is not an exchange session")
                position = int(np.sign(current[spec.asset1]))
                result = self.engine.update_pair_state_and_forecast(pair[spec.asset1], pair[spec.asset2],
                                                                   spec.key, current_position=position)
                beta = result["beta_kalman"]
                if not all(math.isfinite(result[key]) for key in ("beta_kalman", "z_score", "std_t", "spread_t")) or abs(beta) < 1e-8:
                    raise ValueError(f"{spec.key}: unavailable hedge ratio or Kalman signal")
                # Upstream labels these as residual forecasts but subtracts the
                # price-regression intercept a second time in expected_z.
                forecasts = result["forecast_df"].copy()
                forecasts["expected_z"] = forecasts["expected_spread"] / result["std_t"]
                ou_valid = all(math.isfinite(result[k]) and result[k] > 0 for k in ("ou_theta", "ou_half_life"))
                qualification = None
                if cfg.require_formation_qualification:
                    if cfg.formation_end >= str(expected.date()):
                        raise ValueError("formation_end must precede the inference session")
                    formation = pair.loc[:cfg.formation_end]
                    if len(formation) < cfg.pair_minimum_rows:
                        raise ValueError(f"{spec.key}: insufficient frozen formation history")
                    selector = PairSelector(adf_pvalue_threshold=cfg.formation_adf_pvalue,
                                            min_correlation=cfg.formation_min_correlation,
                                            min_half_life=cfg.formation_min_half_life,
                                            max_half_life=cfg.formation_max_half_life)
                    qualification = selector.evaluate_pair(formation, spec.asset1, spec.asset2)
                    if qualification is None:
                        raise ValueError(f"{spec.key}: formation screening needs at least 100 common sessions")
                target, reason = result["target_position"], result["rationale"]
                closed = expected != as_of
                if not position and abs(result["z_score"]) >= cfg.stop_z:
                    target, reason = 0, "Extreme spread divergence blocks a new entry"
                if not position and (not ou_valid or (qualification is not None and not qualification["qualified"])):
                    target, reason = 0, "New entry blocked by OU or frozen formation health check"
                held_sessions = 0
                holding_limit = cfg.max_holding_sessions
                entry_half_life = None
                if position:
                    held_sessions = len(calendar.sessions_in_range(next(iter(opened)), expected)) - 1
                    # Freeze the time-stop estimate at the confirmed opening
                    # session so subsequent estimates cannot extend a trade.
                    entry = pair.loc[:next(iter(opened))]
                    if len(entry) < cfg.pair_minimum_rows:
                        raise ValueError(f"{spec.key}: insufficient history at confirmed entry session")
                    entry_state = self.engine.update_pair_state_and_forecast(entry[spec.asset1], entry[spec.asset2],
                                                                            spec.key, current_position=position)
                    entry_half_life = entry_state["ou_half_life"]
                    if math.isfinite(entry_half_life) and entry_half_life > 0:
                        holding_limit = min(holding_limit, max(1, math.ceil(cfg.holding_half_life_multiplier * entry_half_life)))
                    if held_sessions >= holding_limit:
                        target, reason = 0, "Maximum holding sessions reached"
                if closed:
                    # A nontrading equity day is a valuation only. Never replay
                    # Friday's entry as a fresh weekend trade.
                    units = current
                    reason = "Market closed; retain confirmed holdings and their last actual session"
                else:
                    gross = cfg.pairs_budget_usd * cfg.pairs_gross_fraction / len(cfg.pairs)
                    notional1 = target * gross / (1 + abs(beta))
                    units = {spec.asset1: notional1 / (float(pair.iloc[-1, 0]) * fx),
                             spec.asset2: -beta * notional1 / (float(pair.iloc[-1, 1]) * fx)}
                    if beta < 0 and target:
                        reason = f"{result['signal']}; retain signed beta={beta:.6f}; target legs have the same sign"
                legs = tuple(TargetLeg(symbol, float(units[symbol]), float(pair[symbol].iloc[-1]) * fx) for symbol in columns)
                group = TargetGroup("pairs", spec.key, snapshot.as_of, str(expected.date()), legs, reason,
                                    beta, actionable=not closed)
                groups.append(group)
                updates.append(clean_evidence({
                    "pair": spec.key, "signal_session": str(expected.date()),
                    "session_close_utc": calendar.session_close(expected).isoformat(),
                    "market_closed": closed, "calendar": spec.calendar, "quote_currency": spec.currency,
                    "fx_to_usd": fx, "rows": len(pair), "z_score": result["z_score"],
                    "beta_kalman": beta, "spread": result["spread_t"], "spread_std": result["std_t"],
                    "ou_theta": result["ou_theta"], "ou_half_life": result["ou_half_life"],
                    "ou_forecast_available": ou_valid, "current_position": position,
                    "target_position": position if closed else target, "held_sessions": held_sessions,
                    "holding_limit_sessions": holding_limit, "entry_ou_half_life": entry_half_life,
                    "signal": ("MARKET CLOSED" if closed else "HEALTH OR TIME STOP OVERRIDE" if target != result["target_position"] else result["signal"]),
                    "upstream_signal": result["signal"],
                    "rationale": reason, "formation_end": cfg.formation_end if qualification is not None else None,
                    "formation": qualification, "forecasts": forecasts.to_dict("records") if ou_valid else [],
                    "target_gross_usd": group.gross_usd}))
            diagnostics = {"pairs": updates, "source_sha256": source_sha256, "strategy": strategy,
                           "data_basis": "SYNTHETIC_DEMO" if cfg.mode == "demo" else "HISTORICAL_RESEARCH",
                           "formation_policy": "frozen formation gate" if cfg.require_formation_qualification else "disabled for synthetic demonstration",
                           "price_basis": "Supplied close matrix; adjusted history is signal research, not a verified executable quote"}
            return PMProposal("pairs", "READY", tuple(groups), diagnostics, fingerprint(diagnostics))
        except (ValueError, KeyError, TypeError, IndexError, np.linalg.LinAlgError) as exc:
            diagnostics = {"error": str(exc), "source_sha256": source_sha256}
            return PMProposal("pairs", "INPUT_HOLD", (), diagnostics, fingerprint(diagnostics))
