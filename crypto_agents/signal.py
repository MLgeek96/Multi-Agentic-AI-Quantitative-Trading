"""Trend, mean-reversion and defensive specialists; calculations stay in Python."""

import math

from crypto_quant.daily_portfolio import fit_adaptive_trend

from .models import BlendedSignal, ExpertSignal


class SignalAgent:
    def __init__(self, daily_config):
        self.config = daily_config

    def generate(self, market, portfolio):
        cfg, result = self.config, []
        closes = market.closes()
        required = max(cfg.parameter_training_days + max(s for _, s in cfg.parameter_grid) + 5,
                       cfg.covariance_window_days + 5)
        for symbol in cfg.symbols:
            series = closes[symbol].iloc[-required:]
            if series.isna().any() or len(series) < required:
                result.extend(ExpertSignal(symbol, expert, None, None, "incomplete model history")
                              for expert in ("trend", "mean_revert", "crisis"))
                continue
            model = fit_adaptive_trend(series, cfg.parameter_grid, training_days=cfg.parameter_training_days,
                                      fee_bps=cfg.fee_bps, volatility_window=cfg.volatility_window_days,
                                      minimum_training_sharpe=cfg.minimum_training_sharpe, signal_model=cfg.signal_model,
                                      bollinger_window=cfg.bollinger_window, bollinger_standard_deviations=cfg.bollinger_standard_deviations,
                                      rsi_period=cfg.rsi_period, rsi_long_minimum=cfg.rsi_long_minimum, rsi_long_maximum=cfg.rsi_long_maximum)
            vol = float(model["annualized_volatility"])
            vol = vol if math.isfinite(vol) and vol > 0 else None
            parameters = tuple((k, float(v) if math.isfinite(float(v)) else None) for k, v in model.items())
            result.append(ExpertSignal(symbol, "trend", float(model["signal"]), vol,
                                      "adaptive SMA with trailing training-Sharpe gate", parameters))
            window = series.iloc[-cfg.bollinger_window:]
            deviation = float(window.std(ddof=0))
            z = float((series.iloc[-1] - window.mean()) / deviation) if deviation > 0 else None
            # Current holdings establish the simple entry/exit state; no invented fills.
            mr = None if z is None else float(z < 0.25 if portfolio.units(symbol) > 0 else z < -cfg.bollinger_standard_deviations)
            result.append(ExpertSignal(symbol, "mean_revert", mr, vol, "Bollinger lower-band entry; exit near middle band (research)",
                                      (("z_score", z),)))
            result.append(ExpertSignal(symbol, "crisis", 0.0, vol, "defensive cash specialist; no crisis inference implied"))
        return tuple(result)


def blend(signals, regime):
    weights, result = dict(regime.routing), []
    for symbol in sorted({s.symbol for s in signals}):
        experts = [s for s in signals if s.symbol == symbol]
        if len(experts) != 3 or {s.expert for s in experts} != set(weights):
            raise ValueError("exactly one signal per specialist per symbol is required")
        active = [s for s in experts if weights[s.expert] > 0]
        unknown = any(s.exposure is None or s.annualized_volatility is None for s in active)
        exposure = None if unknown else sum(weights[s.expert] * s.exposure for s in active)
        result.append(BlendedSignal(symbol, exposure, active[0].annualized_volatility if not unknown else None))
    return tuple(result)
