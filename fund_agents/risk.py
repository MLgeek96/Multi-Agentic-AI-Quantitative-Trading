"""Final fund veto and common scaling that cannot separate linked pair legs."""

from dataclasses import replace

from typing import Any

from .evidence import fingerprint, json_value

from .models import FundConfig, FundSnapshot, PMProposal, PhantomBook, TargetLeg


ENVELOPE_MULTIPLIERS: dict[str, float] = {
    "conservative": 0.75,
    "standard": 1.00,
    "aggressive": 1.00,
}


class FundRisk:
    """Independent fund-level risk gate with tiered drawdown throttling and shadow accounting."""

    def __init__(self, config: FundConfig) -> None:
        self.config = config

    def review(
        self,
        proposals: tuple[PMProposal, ...],
        snapshot: FundSnapshot,
        previous: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cfg = self.config
        previous = previous or {"peak_nav_usd": snapshot.peak_nav_usd, "breaker_latched": False, "last_session": None}
        if previous["last_session"] and snapshot.as_of < previous["last_session"]:
            raise ValueError("fund dates cannot run backwards; use a separate account for replay")
        if {p.pm for p in proposals} != {"pairs"} or len(proposals) != 1:
            raise ValueError("the coordinator requires exactly one Pairs PM proposal")
        decision: dict[str, Any] = {
            "as_of": snapshot.as_of, "account_key": cfg.account_key, "status": "INPUT_HOLD",
            "snapshot_sha256": fingerprint(snapshot),
            "approved_groups": [], "reviews": [], "metrics": {},
            "state": dict(previous, last_session=snapshot.as_of), "alerts": [],
        }
        if any(p.status != "READY" for p in proposals):
            decision["alerts"] = [p.pm + ": INPUT_HOLD" for p in proposals if p.status != "READY"]
            decision["decision_id"] = fingerprint(decision)
            return decision
        groups = tuple(g for p in proposals for g in p.groups)
        if any(g.as_of != snapshot.as_of for g in groups):
            raise ValueError("every PM target must use the fund valuation date")
        prices = {(g.pm, g.group, l.symbol): l.price_usd for g in groups for l in g.legs}
        if any((h.pm, h.group, h.symbol) not in prices for h in snapshot.holdings):
            raise ValueError("holdings have no audited PM reference price")
        navs = {pm: getattr(snapshot, pm + "_cash_usd") + sum(h.units * prices[(h.pm, h.group, h.symbol)]
                 for h in snapshot.holdings if h.pm == pm) for pm in ("pairs",)}
        nav = sum(navs.values()) + snapshot.central_cash_usd + snapshot.momentum_cash_usd
        if nav <= 0 or any(v <= 0 for v in navs.values()):
            raise ValueError("fund and connected sleeve NAVs must be positive")
        peak = max(previous["peak_nav_usd"], snapshot.peak_nav_usd, nav)
        drawdown = 1.0 - nav / peak
        latched = previous["breaker_latched"] or drawdown >= cfg.maximum_drawdown
        soft_throttle = (not latched) and (drawdown >= cfg.soft_drawdown)
        decision["state"] = {"peak_nav_usd": peak, "breaker_latched": latched, "last_session": snapshot.as_of}
        decision["metrics"] = {"marked_nav_usd": nav,
                               "pairs_nav_usd": navs["pairs"], "momentum_cash_usd": snapshot.momentum_cash_usd,
                               "central_cash_usd": snapshot.central_cash_usd, "filled_orders": 0, "realized_pnl": None}
        original = groups
        if latched:
            decision["alerts"].append("FUND_DRAWDOWN_BREAKER_LATCHED")
            groups = tuple(replace(g, legs=tuple(replace(l, units=0.) for l in g.legs),
                                   reason="Fund drawdown exit request") if g.actionable else g for g in groups)
        elif soft_throttle:
            decision["alerts"].append("SOFT_DRAWDOWN_THROTTLE")
        fixed = [g for g in groups if not g.actionable]
        active = [g for g in groups if g.actionable]
        fixed_gross = sum(g.gross_usd for g in fixed)
        active_gross = sum(g.gross_usd for g in active)
        envelope_mult = ENVELOPE_MULTIPLIERS[cfg.risk_envelope]
        effective_fund_gross = cfg.maximum_fund_gross * envelope_mult * (cfg.soft_drawdown_scale if soft_throttle else 1.0)
        gross_label = "fund gross (soft drawdown throttle)" if soft_throttle else "fund gross"
        limits = [(gross_label, effective_fund_gross * nav - fixed_gross, active_gross)]
        symbols = {l.symbol for g in groups for l in g.legs}
        for symbol in symbols:
            fixed_name = sum(abs(l.units * l.price_usd) for g in fixed for l in g.legs if l.symbol == symbol)
            active_name = sum(abs(l.units * l.price_usd) for g in active for l in g.legs if l.symbol == symbol)
            limits.append((symbol + " gross across pair groups", cfg.maximum_name_gross * nav - fixed_name, active_name))
        fee = cfg.fee_buffer_bps / 10_000
        for pm in ("pairs",):
            fixed_pm = sum(g.gross_usd for g in fixed if g.pm == pm)
            active_pm = sum(g.gross_usd for g in active if g.pm == pm)
            current_active_gross = sum(abs(snapshot.units(g.pm, g.group, l.symbol) * l.price_usd)
                                       for g in active if g.pm == pm for l in g.legs)
            budget = min(navs[pm], getattr(cfg, pm + "_budget_usd")) * (1 - cfg.collateral_buffer)
            # Fees use an upper bound on target-to-current turnover. Short sale
            # proceeds never add to the unlevered collateral mandate.
            limits.append((pm + " collateral and fee reserve", budget - fixed_pm - fee * current_active_gross,
                           active_pm * (1 + fee)))
        if any(room < -1e-6 for _, room, _ in limits):
            decision["status"] = "RISK_VETO"
            decision["alerts"].append("Existing non-actionable exposure or exit fee reserve exceeds a limit")
            decision["decision_id"] = fingerprint(decision)
            return decision
        factor = min([1.] + [max(0., room) / gross for _, room, gross in limits if gross > 0])
        reasons = [name for name, room, gross in limits if gross > 0 and room / gross < 1 - 1e-10]
        for before, requested in zip(original, groups):
            approved = replace(requested, legs=tuple(TargetLeg(l.symbol, l.units * factor, l.price_usd)
                                                     for l in requested.legs)) if requested.actionable else requested
            outcome = "MARKET_CLOSED" if not approved.actionable else ("EXIT_REQUEST" if latched else ("REDUCE" if factor < 1 - 1e-10 else "PASS"))
            decision["reviews"].append({"proposed": json_value(before), "approved": json_value(approved),
                                         "outcome": outcome, "scale": factor if approved.actionable else 1.,
                                         "reasons": reasons if approved.actionable else ["No trade on a closed market"]})
            decision["approved_groups"].append(json_value(approved))
        gross = sum(sum(abs(l["units"] * l["price_usd"]) for l in g["legs"]) for g in decision["approved_groups"])
        net = sum(sum(l["units"] * l["price_usd"] for l in g["legs"]) for g in decision["approved_groups"])
        proposed_gross = sum(g.gross_usd for g in original)
        sleeve_throttled = {
            pm: max(
                0.0,
                sum(g.gross_usd for g in original if g.pm == pm)
                - sum(sum(abs(l["units"] * l["price_usd"]) for l in g["legs"]) for g in decision["approved_groups"] if g["pm"] == pm),
            )
            for pm in ("pairs",)
        }
        decision["phantom_book"] = json_value(
            PhantomBook(
                proposed_gross_usd=proposed_gross,
                approved_gross_usd=gross,
                throttled_gross_usd=max(0.0, proposed_gross - gross),
                preserved_buffer_usd=max(0.0, nav - gross),
                envelope_tier=cfg.risk_envelope,
                soft_throttle_active=soft_throttle,
                sleeve_throttled_usd=sleeve_throttled,
            )
        )
        decision["metrics"].update(target_gross_usd=gross, target_net_usd=net, target_gross_fraction=gross / nav)
        decision["status"] = "BREAKER_LATCHED" if latched else "REVIEWED"
        decision["decision_id"] = fingerprint(decision)
        return decision
