"""Propose fractional-unit Spot intents from capped inverse-volatility targets."""

from crypto_quant.daily_portfolio import capped_inverse_volatility_weights

from .models import OrderIntent, fingerprint


class PositionAgent:
    def __init__(self, config, daily_config):
        self.config, self.daily = config, daily_config

    def propose(self, signals, market, portfolio):
        # Whole-portfolio hold: unknown input never becomes a liquidation request.
        if any(s.exposure is None or s.annualized_volatility is None for s in signals):
            return (), None
        models = {s.symbol: {"signal": int(s.exposure > 0), "annualized_volatility": s.annualized_volatility} for s in signals}
        cfg = self.daily
        weights = capped_inverse_volatility_weights(models, market.closes().pct_change(fill_method=None),
                                                    max_asset_weight=cfg.max_asset_weight,
                                                    target_annual_volatility=cfg.target_annual_volatility,
                                                    covariance_window=cfg.covariance_window_days)
        weights = {s.symbol: weights[s.symbol] * s.exposure for s in signals}
        equity = portfolio.equity(market)
        source = fingerprint((market, portfolio, self.config, cfg.symbols, cfg.parameter_grid,
                              cfg.target_annual_volatility, cfg.max_asset_weight, weights))
        intents = []
        for symbol in cfg.symbols:
            price = market.dataset(symbol).bars[-1].close
            delta = equity * weights[symbol] / price - portfolio.units(symbol)
            if abs(delta) * price > 1e-6:
                intents.append(OrderIntent.create(market.as_of, symbol, "BUY" if delta > 0 else "SELL", abs(delta), price,
                                                  source, "volatility-scaled target rebalance"))
        return tuple(intents), weights
