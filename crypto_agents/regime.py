"""Baseline routing or optional prior-trained two-state HMM experiment."""

from math import isfinite
import pandas as pd

from crypto_quant.hmm_regime import GaussianHMM2, build_regime_features

from .models import RegimeEstimate, fingerprint


class RegimeAgent:
    def __init__(self, config):
        self.config = config

    def estimate(self, market):
        if self.config.strategy_mode == "adaptive_trend":
            return RegimeEstimate(market.as_of, (("trend", 1.0), ("mean_revert", 0.0), ("crisis", 0.0)),
                                  "baseline-policy; regime model disabled")
        features = build_regime_features(market.closes(), volatility_window=20)
        stamp = pd.Timestamp(market.as_of, tz="UTC")
        training = features.loc[features.index < stamp].iloc[-self.config.hmm_training_days:]
        if len(training) < self.config.hmm_training_days or stamp not in features.index:
            raise ValueError("insufficient prior HMM history")
        dimensions = [i for i, name in enumerate(training.columns) if name.startswith("return_")]
        model = GaussianHMM2.fit(training.to_numpy(), volatility_dimensions=dimensions, maximum_iterations=60)
        previous = model.filter_probabilities(training.to_numpy())[-1]
        posterior = model.filter_one(features.loc[stamp].to_numpy(), previous)
        high = float(posterior[model.high_volatility_state])
        if not isfinite(high) or not 0 <= high <= 1:
            raise ValueError("invalid regime probability")
        model_id = fingerprint({"means": model.means.tolist(), "variances": model.variances.tolist(),
                                "transition": model.transition.tolist(), "start": model.start_probability.tolist(),
                                "location": model.location.tolist(), "scale": model.scale.tolist(),
                                "training": training.to_json(date_format="iso"), "features": list(training.columns)})
        return RegimeEstimate(market.as_of, (("trend", high), ("mean_revert", 1 - high), ("crisis", 0.0)),
                              "GaussianHMM2-volatility", training.index[-1].date().isoformat(), high, model_id,
                              "High-vol -> trend, low-vol -> mean-revert is an unvalidated research mapping; neither is a crisis label")
