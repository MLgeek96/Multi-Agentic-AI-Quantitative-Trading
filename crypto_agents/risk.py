"""Independent veto, conservative sizing, stop requests and persistent breaker."""

from .models import OrderIntent, OrderReview, RiskDecision, RiskState, fingerprint


class RiskAgent:
    def __init__(self, config):
        self.config = config

    def review(self, proposed, market, portfolio, previous, cycle_id):
        cfg = self.config
        previous = previous or RiskState(portfolio.peak_equity_usdt)
        if previous.last_session and market.as_of < previous.last_session:
            raise ValueError("account sessions cannot run backwards; use a separate account key for replay")
        if market.as_of != portfolio.as_of:
            raise ValueError("market and portfolio sessions differ")
        state = RiskState(previous.peak_equity_usdt, previous.breaker_latched, market.as_of)
        alerts, reviews = [], []
        if not market.quality_pass:
            alerts.append("DATA_QUALITY_VETO")
            reviews = [OrderReview(i, "REJECT", None, ("data quality failed",)) for i in proposed]
            return RiskDecision(cycle_id, market.as_of, cfg.account_key, tuple(reviews), state, tuple(alerts), None)
        equity = portfolio.equity(market)
        if equity <= 0:
            raise ValueError("portfolio equity must be positive")
        peak = max(previous.peak_equity_usdt, portfolio.peak_equity_usdt, equity)
        latched = previous.breaker_latched or (1 - equity / peak >= cfg.maximum_drawdown)
        state = RiskState(peak, latched, market.as_of)
        if latched:
            alerts.append("DRAWDOWN_BREAKER_LATCHED")

        proposals = list(proposed)
        exits = {}
        for holding in portfolio.holdings:
            price = market.dataset(holding.symbol).bars[-1].close
            pnl = price / holding.entry_price - 1
            reason = "drawdown exit request" if latched else (
                "stop-loss exit request" if pnl <= -cfg.stop_loss_fraction else (
                    "take-profit exit request" if pnl >= cfg.take_profit_fraction else None))
            if reason and holding.units > 0:
                exits[holding.symbol] = OrderIntent.create(market.as_of, holding.symbol, "SELL", holding.units, price,
                                                          fingerprint((market, portfolio, cfg, reason)), reason)
                alerts.append(f"{holding.symbol}: {reason}")
        overridden = [i for i in proposals if i.symbol in exits]
        reviews.extend(OrderReview(i, "REJECT", None, ("superseded by risk exit request",)) for i in overridden)
        proposals = [i for i in proposals if i.symbol not in exits] + list(exits.values())
        # No imaginary sale proceeds. Buys must fit supplied cash even if sells
        # are also approved. Sale confirmations belong to a future fill adapter.
        quantities = {d.symbol: portfolio.units(d.symbol) for d in market.datasets}
        cash_budget = max(0.0, portfolio.cash_usdt - equity * cfg.cash_buffer)
        seen = set()
        for intent in sorted(proposals, key=lambda i: (i.side != "SELL", i.symbol, i.intent_id)):
            reasons = []
            if intent.symbol not in quantities or intent.as_of != market.as_of or intent.symbol in seen:
                reviews.append(OrderReview(intent, "REJECT", None, ("unknown symbol, mismatched session or duplicate proposal",)))
                continue
            seen.add(intent.symbol)
            dataset = market.dataset(intent.symbol)
            price = dataset.bars[-1].close
            if intent.reference_price != price:
                reviews.append(OrderReview(intent, "REJECT", None, ("reference price differs from audited snapshot",)))
                continue
            prior = dataset.bars[:-1][-cfg.liquidity_days:]
            if len(prior) < cfg.liquidity_days:
                reviews.append(OrderReview(intent, "REJECT", None, ("insufficient trailing liquidity history",)))
                continue
            adv = sum(b.quote_volume for b in prior) / len(prior)
            allowed = min(intent.units, adv * cfg.maximum_adv_participation / price)
            if allowed < intent.units:
                reasons.append("trailing-ADV participation limit")
            if intent.side == "SELL":
                allowed = min(allowed, quantities[intent.symbol])
                if allowed < intent.units and "trailing-ADV participation limit" not in reasons:
                    reasons.append("available units limit")
                quantities[intent.symbol] -= allowed
            else:
                if latched or intent.symbol in exits:
                    allowed = 0.0
                    reasons.append("risk breaker or exit suppresses buys")
                marked = quantities[intent.symbol] * price
                gross = sum(quantities[s] * market.dataset(s).bars[-1].close for s in quantities)
                name_room = max(0.0, cfg.maximum_asset_weight * equity - marked) / price
                gross_room = max(0.0, cfg.maximum_gross_exposure * equity - gross) / price
                cash_room = cash_budget / (price * (1 + cfg.fee_buffer_bps / 10_000))
                cap = min(name_room, gross_room, cash_room)
                if cap < allowed:
                    reasons.append("name/gross/cash limit including fee buffer")
                allowed = min(allowed, cap)
                quantities[intent.symbol] += allowed
                cash_budget -= allowed * price * (1 + cfg.fee_buffer_bps / 10_000)
            if allowed * price <= 1e-6:
                reviews.append(OrderReview(intent, "REJECT", None, tuple(reasons or ["no available budget or liquidity"])))
            elif allowed < intent.units:
                reviews.append(OrderReview(intent, "REDUCE", intent.resized(allowed), tuple(reasons)))
            else:
                reviews.append(OrderReview(intent, "PASS", intent, ("within configured research limits",)))
        return RiskDecision(cycle_id, market.as_of, cfg.account_key, tuple(reviews), state, tuple(alerts), equity)
