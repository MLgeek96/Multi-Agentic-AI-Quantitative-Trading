"""Walk-forward two-state HMM regime strategy for crypto futures research.

The implementation intentionally depends only on NumPy and pandas.  Regime
probabilities are filtered using observations available at each daily close;
portfolio weights are shifted by one day before returns are earned.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class HMMRegimeConfig:
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    initial_equity: float = 100_000.0
    hmm_training_days: int = 730
    hmm_minimum_training_days: int = 365
    hmm_retrain_days: int = 30
    hmm_iterations: int = 100
    hmm_tolerance: float = 1e-5
    feature_volatility_window: int = 20
    regime_probability_buffer: float = 0.05
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    sma_fast: int = 20
    sma_slow: int = 100
    rsi_period: int = 14
    rsi_long_threshold: float = 55.0
    rsi_short_threshold: float = 45.0
    momentum_minimum_votes: int = 2
    bollinger_window: int = 20
    bollinger_standard_deviations: float = 2.0
    mean_reversion_exit_z: float = 0.25
    risk_volatility_window: int = 30
    target_annual_volatility: float = 0.20
    maximum_asset_weight: float = 0.50
    maximum_gross_exposure: float = 1.0
    covariance_window: int = 60
    fee_bps: float = 10.0

    def validate(self) -> None:
        if len(self.symbols) < 2 or len(set(self.symbols)) != len(self.symbols):
            raise ValueError("symbols must contain at least two unique instruments")
        if self.hmm_minimum_training_days < 60:
            raise ValueError("hmm_minimum_training_days must be at least 60")
        if self.hmm_training_days < self.hmm_minimum_training_days:
            raise ValueError("hmm_training_days must be >= hmm_minimum_training_days")
        if self.hmm_retrain_days < 1:
            raise ValueError("hmm_retrain_days must be positive")
        if not 0 <= self.regime_probability_buffer < 0.5:
            raise ValueError("regime_probability_buffer must be in [0, 0.5)")
        if not 1 <= self.momentum_minimum_votes <= 3:
            raise ValueError("momentum_minimum_votes must be between 1 and 3")
        if not 0 < self.maximum_asset_weight <= self.maximum_gross_exposure:
            raise ValueError("maximum_asset_weight must be positive and no larger than gross exposure")
        if self.fee_bps < 0:
            raise ValueError("fee_bps cannot be negative")


@dataclass(frozen=True)
class GaussianHMM2:
    """Fitted two-state Gaussian HMM with diagonal covariance matrices."""

    start_probability: np.ndarray
    transition: np.ndarray
    means: np.ndarray
    variances: np.ndarray
    location: np.ndarray
    scale: np.ndarray
    high_volatility_state: int
    log_likelihood: float
    iterations: int

    @classmethod
    def fit(
        cls,
        observations: np.ndarray,
        *,
        volatility_dimensions: Iterable[int],
        maximum_iterations: int = 100,
        tolerance: float = 1e-5,
    ) -> "GaussianHMM2":
        values = np.asarray(observations, dtype=float)
        if values.ndim != 2 or len(values) < 20:
            raise ValueError("observations must be a two-dimensional array with at least 20 rows")
        if not np.isfinite(values).all():
            raise ValueError("observations contain non-finite values")
        dimensions = tuple(int(value) for value in volatility_dimensions)
        if not dimensions or min(dimensions) < 0 or max(dimensions) >= values.shape[1]:
            raise ValueError("volatility_dimensions must reference at least one observation column")

        location = values.mean(axis=0)
        scale = values.std(axis=0, ddof=0)
        scale = np.where(scale < 1e-8, 1.0, scale)
        standardized = (values - location) / scale

        magnitude = np.mean(np.abs(standardized[:, dimensions]), axis=1)
        split = float(np.median(magnitude))
        labels = (magnitude > split).astype(int)
        if labels.min() == labels.max():
            labels[len(labels) // 2 :] = 1
        means = np.vstack(
            [standardized[labels == state].mean(axis=0) for state in range(2)]
        )
        overall_variance = np.maximum(standardized.var(axis=0), 1e-3)
        variances = np.vstack(
            [
                np.maximum(standardized[labels == state].var(axis=0), overall_variance * 0.05)
                for state in range(2)
            ]
        )
        start_probability = np.array([0.5, 0.5], dtype=float)
        transition = np.array([[0.97, 0.03], [0.03, 0.97]], dtype=float)
        previous_likelihood = -np.inf
        iterations = 0

        for iteration in range(1, maximum_iterations + 1):
            log_emission = _log_gaussian_density(standardized, means, variances)
            log_alpha, likelihood = _forward_log(
                log_emission, start_probability, transition
            )
            log_beta = _backward_log(log_emission, transition)
            gamma = np.exp(log_alpha + log_beta - likelihood)
            gamma /= np.maximum(gamma.sum(axis=1, keepdims=True), 1e-300)

            transition_counts = np.zeros((2, 2), dtype=float)
            log_transition = np.log(np.maximum(transition, 1e-300))
            for row in range(len(standardized) - 1):
                log_xi = (
                    log_alpha[row, :, None]
                    + log_transition
                    + log_emission[row + 1, None, :]
                    + log_beta[row + 1, None, :]
                    - likelihood
                )
                transition_counts += np.exp(log_xi)

            start_probability = np.maximum(gamma[0], 1e-6)
            start_probability /= start_probability.sum()
            transition_counts += 1e-3
            transition = transition_counts / transition_counts.sum(axis=1, keepdims=True)
            state_weight = np.maximum(gamma.sum(axis=0), 1e-8)
            means = (gamma.T @ standardized) / state_weight[:, None]
            residual = standardized[:, None, :] - means[None, :, :]
            variances = (
                np.sum(gamma[:, :, None] * residual * residual, axis=0)
                / state_weight[:, None]
            )
            variances = np.maximum(variances, 1e-3)
            iterations = iteration
            if np.isfinite(previous_likelihood) and abs(likelihood - previous_likelihood) <= (
                tolerance * (1.0 + abs(previous_likelihood))
            ):
                break
            previous_likelihood = likelihood

        state_return_variance = variances[:, dimensions].mean(axis=1)
        high_state = int(np.argmax(state_return_variance))
        final_log_emission = _log_gaussian_density(standardized, means, variances)
        _, final_likelihood = _forward_log(
            final_log_emission, start_probability, transition
        )
        return cls(
            start_probability=start_probability,
            transition=transition,
            means=means,
            variances=variances,
            location=location,
            scale=scale,
            high_volatility_state=high_state,
            log_likelihood=final_likelihood,
            iterations=iterations,
        )

    def filter_probabilities(self, observations: np.ndarray) -> np.ndarray:
        values = np.asarray(observations, dtype=float)
        standardized = (values - self.location) / self.scale
        log_emission = _log_gaussian_density(standardized, self.means, self.variances)
        probabilities = np.empty((len(values), 2), dtype=float)
        previous: np.ndarray | None = None
        for row, log_likelihood in enumerate(log_emission):
            previous = self.filter_one(
                values[row], previous, log_emission_likelihood=log_likelihood
            )
            probabilities[row] = previous
        return probabilities

    def filter_one(
        self,
        observation: np.ndarray,
        previous_probability: np.ndarray | None,
        *,
        log_emission_likelihood: np.ndarray | None = None,
    ) -> np.ndarray:
        if log_emission_likelihood is None:
            standardized = (np.asarray(observation, dtype=float) - self.location) / self.scale
            log_emission_likelihood = _log_gaussian_density(
                standardized[None, :], self.means, self.variances
            )[0]
        prior = (
            self.start_probability
            if previous_probability is None
            else np.asarray(previous_probability, dtype=float) @ self.transition
        )
        log_posterior = np.log(np.maximum(prior, 1e-300)) + log_emission_likelihood
        normalizer = float(_logsumexp(log_posterior))
        if not np.isfinite(normalizer):
            return np.array([0.5, 0.5], dtype=float)
        return np.exp(log_posterior - normalizer)


def load_daily_futures(path: str | Path) -> pd.DataFrame:
    """Load hourly normalized candles and return complete UTC daily bars."""

    path = Path(path)
    frame = pd.read_csv(path, parse_dates=["open_time"])
    required = {"open_time", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True)
    frame = frame.sort_values("open_time", kind="stable").drop_duplicates("open_time")
    frame = frame.set_index("open_time")
    numeric = ["open", "high", "low", "close", "volume"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    daily = frame.resample("1D", closed="left", label="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        source_bar_count=("close", "count"),
    )
    daily.loc[daily["source_bar_count"].ne(24), numeric] = np.nan
    return daily


def build_regime_features(
    closes: pd.DataFrame,
    *,
    volatility_window: int,
    macro_features: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Create stationary return/volatility observations for the HMM.

    ``macro_features`` must already contain stationary values such as equity
    returns or yield changes.  Callers should lag them to match publication
    timing before passing them here.
    """

    closes = closes.astype(float).sort_index()
    log_returns = np.log(closes).diff()
    rolling_volatility = log_returns.rolling(volatility_window).std(ddof=0) * sqrt(365)
    features = pd.concat(
        [
            log_returns.rename(columns=lambda value: f"return_{value}"),
            np.log(rolling_volatility.clip(lower=1e-8)).rename(
                columns=lambda value: f"log_vol_{value}"
            ),
        ],
        axis=1,
    )
    if macro_features is not None:
        macro = macro_features.astype(float).sort_index().add_prefix("macro_")
        features = features.join(macro, how="left")
    return features.replace([np.inf, -np.inf], np.nan).dropna()


def walk_forward_regime_probabilities(
    features: pd.DataFrame,
    config: HMMRegimeConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Filter high-volatility probabilities with periodic trailing refits."""

    config.validate()
    return_dimensions = [
        position for position, column in enumerate(features.columns) if column.startswith("return_")
    ]
    if not return_dimensions:
        raise ValueError("features must contain return_ columns")
    output = pd.DataFrame(
        index=features.index,
        columns=["high_volatility_probability", "regime", "model_refit"],
        dtype=object,
    )
    diagnostics: list[dict[str, object]] = []
    model: GaussianHMM2 | None = None
    posterior: np.ndarray | None = None
    last_refit_position: int | None = None
    active_regime: str | None = None

    for position in range(config.hmm_minimum_training_days - 1, len(features)):
        refit = model is None or position - int(last_refit_position) >= config.hmm_retrain_days
        if refit:
            start = max(0, position - config.hmm_training_days + 1)
            training = features.iloc[start : position + 1]
            model = GaussianHMM2.fit(
                training.to_numpy(dtype=float),
                volatility_dimensions=return_dimensions,
                maximum_iterations=config.hmm_iterations,
                tolerance=config.hmm_tolerance,
            )
            posterior = model.filter_probabilities(training.to_numpy(dtype=float))[-1]
            last_refit_position = position
            high = model.high_volatility_state
            diagnostics.append(
                {
                    "refit_date": features.index[position],
                    "training_start": training.index[0],
                    "training_observations": len(training),
                    "iterations": model.iterations,
                    "log_likelihood": model.log_likelihood,
                    "high_volatility_state": high,
                    "high_state_persistence": model.transition[high, high],
                    "low_state_persistence": model.transition[1 - high, 1 - high],
                }
            )
        else:
            assert model is not None
            posterior = model.filter_one(
                features.iloc[position].to_numpy(dtype=float), posterior
            )

        assert model is not None and posterior is not None
        probability = float(posterior[model.high_volatility_state])
        upper = 0.5 + config.regime_probability_buffer
        lower = 0.5 - config.regime_probability_buffer
        if active_regime is None:
            active_regime = "high_volatility" if probability >= 0.5 else "low_volatility"
        elif probability >= upper:
            active_regime = "high_volatility"
        elif probability <= lower:
            active_regime = "low_volatility"
        output.loc[features.index[position]] = [probability, active_regime, refit]

    output["high_volatility_probability"] = pd.to_numeric(
        output["high_volatility_probability"], errors="coerce"
    )
    output["model_refit"] = output["model_refit"].fillna(False).astype(bool)
    return output.dropna(subset=["regime"]), pd.DataFrame.from_records(diagnostics)


def build_strategy_signals(
    closes: pd.DataFrame,
    regimes: pd.DataFrame,
    config: HMMRegimeConfig,
) -> pd.DataFrame:
    """Apply momentum in high vol and Bollinger mean reversion in low vol."""

    config.validate()
    closes = closes.astype(float).sort_index()
    result_records: list[dict[str, object]] = []
    indicator_frames: dict[str, pd.DataFrame] = {}
    for symbol in config.symbols:
        close = closes[symbol]
        ema_fast = close.ewm(span=config.macd_fast, adjust=False).mean()
        ema_slow = close.ewm(span=config.macd_slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=config.macd_signal, adjust=False).mean()
        sma_fast = close.rolling(config.sma_fast).mean()
        sma_slow = close.rolling(config.sma_slow).mean()
        rsi = _rsi(close, config.rsi_period)
        middle = close.rolling(config.bollinger_window).mean()
        deviation = close.rolling(config.bollinger_window).std(ddof=0)
        z_score = (close - middle) / deviation.replace(0.0, np.nan)
        votes = pd.DataFrame(index=close.index)
        votes["macd_vote"] = np.sign(macd - macd_signal)
        votes["sma_vote"] = np.sign(sma_fast - sma_slow)
        votes["rsi_vote"] = np.select(
            [rsi >= config.rsi_long_threshold, rsi <= config.rsi_short_threshold],
            [1, -1],
            default=0,
        )
        positive = votes.eq(1).sum(axis=1)
        negative = votes.eq(-1).sum(axis=1)
        momentum_signal = pd.Series(
            np.select(
                [
                    (positive >= config.momentum_minimum_votes) & (positive > negative),
                    (negative >= config.momentum_minimum_votes) & (negative > positive),
                ],
                [1, -1],
                default=0,
            ),
            index=close.index,
        )
        indicator_frames[symbol] = pd.DataFrame(
            {
                "close": close,
                "macd": macd,
                "macd_signal_line": macd_signal,
                "sma_fast": sma_fast,
                "sma_slow": sma_slow,
                "rsi": rsi,
                "bollinger_middle": middle,
                "bollinger_z": z_score,
                "momentum_signal": momentum_signal,
            }
        )

    common_index = closes.index.intersection(regimes.index)
    mean_reversion_positions = {symbol: 0 for symbol in config.symbols}
    previous_regime: str | None = None
    for date in common_index:
        regime = str(regimes.at[date, "regime"])
        if regime != "low_volatility" or previous_regime != "low_volatility":
            mean_reversion_positions = {symbol: 0 for symbol in config.symbols}
        for symbol in config.symbols:
            indicators = indicator_frames[symbol].loc[date]
            if regime == "high_volatility":
                strategy = "momentum"
                signal = int(indicators["momentum_signal"])
            else:
                strategy = "mean_reversion"
                z_score = float(indicators["bollinger_z"])
                current = mean_reversion_positions[symbol]
                if np.isfinite(z_score):
                    if z_score <= -config.bollinger_standard_deviations:
                        current = 1
                    elif z_score >= config.bollinger_standard_deviations:
                        current = -1
                    elif current == 1 and z_score >= -config.mean_reversion_exit_z:
                        current = 0
                    elif current == -1 and z_score <= config.mean_reversion_exit_z:
                        current = 0
                else:
                    current = 0
                mean_reversion_positions[symbol] = current
                signal = current
            result_records.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "regime": regime,
                    "high_volatility_probability": regimes.at[
                        date, "high_volatility_probability"
                    ],
                    "model_refit": regimes.at[date, "model_refit"],
                    "strategy": strategy,
                    "signal": signal,
                    **indicators.to_dict(),
                }
            )
        previous_regime = regime
    return pd.DataFrame.from_records(result_records)


def build_target_weights(
    closes: pd.DataFrame,
    signals: pd.DataFrame,
    config: HMMRegimeConfig,
) -> pd.DataFrame:
    """Build signed inverse-volatility weights with gross and risk caps."""

    returns = closes.pct_change()
    annualized_volatility = returns.rolling(config.risk_volatility_window).std(ddof=1) * sqrt(365)
    signal_matrix = signals.pivot(index="date", columns="symbol", values="signal").reindex(
        index=closes.index, columns=list(config.symbols)
    )
    weights = pd.DataFrame(0.0, index=closes.index, columns=list(config.symbols))
    for date in closes.index:
        directions = pd.to_numeric(signal_matrix.loc[date], errors="coerce").fillna(0.0)
        volatility = annualized_volatility.loc[date]
        active = directions.ne(0) & volatility.gt(0) & np.isfinite(volatility)
        if not active.any():
            continue
        # Fractional signals are used by the staged grid proxy.  Binary signals
        # retain the original behavior: one active asset receives at most one
        # asset cap and two active assets can use the full gross budget.
        desired_gross = min(
            config.maximum_gross_exposure,
            config.maximum_asset_weight * float(directions[active].abs().sum()),
        )
        scores = (directions[active].abs() / volatility[active]).astype(float)
        absolute = _capped_allocations(
            scores,
            total=desired_gross,
            cap=config.maximum_asset_weight,
        )
        proposed = pd.Series(0.0, index=weights.columns)
        proposed.loc[absolute.index] = absolute * np.sign(directions.loc[absolute.index])
        sample = returns.loc[:date, list(config.symbols)].dropna().iloc[-config.covariance_window :]
        if len(sample) >= 20 and config.target_annual_volatility > 0:
            covariance = sample.cov().to_numpy(dtype=float) * 365.0
            vector = proposed.to_numpy(dtype=float)
            predicted = sqrt(max(float(vector @ covariance @ vector), 0.0))
            if predicted > config.target_annual_volatility:
                proposed *= config.target_annual_volatility / predicted
        weights.loc[date] = proposed
    return weights


def backtest_regime_strategy(
    closes: pd.DataFrame,
    signals: pd.DataFrame,
    config: HMMRegimeConfig,
) -> pd.DataFrame:
    """Apply close-known target weights to the next daily return."""

    closes = closes.loc[:, list(config.symbols)].astype(float).sort_index()
    target = build_target_weights(closes, signals, config)
    returns = closes.pct_change().fillna(0.0)
    applied = target.shift(1).fillna(0.0)
    turnover = applied.diff().abs().sum(axis=1)
    if len(turnover):
        turnover.iloc[0] = float(applied.iloc[0].abs().sum())
    gross_return = (applied * returns).sum(axis=1)
    transaction_cost = turnover * config.fee_bps / 10_000.0
    net_return = gross_return - transaction_cost
    equity = config.initial_equity * (1.0 + net_return).cumprod()
    peak = equity.cummax()
    portfolio = pd.DataFrame(
        {
            "gross_return": gross_return,
            "transaction_cost_return": transaction_cost,
            "net_return": net_return,
            "equity": equity,
            "drawdown": equity / peak - 1.0,
            "turnover": turnover,
            "gross_exposure": applied.abs().sum(axis=1),
            "net_exposure": applied.sum(axis=1),
            "btc_benchmark": config.initial_equity
            * (1.0 + returns[config.symbols[0]]).cumprod(),
            "equal_weight_benchmark": config.initial_equity
            * (1.0 + returns.mean(axis=1)).cumprod(),
        },
        index=closes.index,
    )
    for symbol in config.symbols:
        portfolio[f"target_weight_{symbol}"] = target[symbol]
        portfolio[f"applied_weight_{symbol}"] = applied[symbol]
    return portfolio


def performance_metrics(
    portfolio: pd.DataFrame,
    *,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> dict[str, object]:
    """Calculate metrics for a half-open period, rebased at its first row."""

    start_timestamp = _utc(start)
    end_timestamp = _utc(end)
    sample = portfolio.loc[(portfolio.index >= start_timestamp) & (portfolio.index < end_timestamp)]
    if sample.empty:
        raise ValueError(f"No portfolio observations between {start} and {end}")
    daily = sample["net_return"].astype(float)
    curve = (1.0 + daily).cumprod()
    drawdown = curve / curve.cummax() - 1.0
    total_return = float(curve.iloc[-1] - 1.0)
    standard_deviation = float(daily.std(ddof=1))
    years = len(sample) / 365.0
    annualized_return = float((1.0 + total_return) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    sharpe = (
        float(daily.mean() / standard_deviation * sqrt(365))
        if standard_deviation > 0
        else 0.0
    )
    downside = float(daily.clip(upper=0.0).std(ddof=1))
    sortino = float(daily.mean() / downside * sqrt(365)) if downside > 0 else 0.0
    btc = sample["btc_benchmark"].astype(float)
    equal = sample["equal_weight_benchmark"].astype(float)
    return {
        "observations": len(sample),
        "actual_start": sample.index[0].date().isoformat(),
        "actual_end": sample.index[-1].date().isoformat(),
        "total_return": total_return,
        "annualized_return": annualized_return,
        "annualized_volatility": standard_deviation * sqrt(365),
        "sharpe_ratio_zero_risk_free": sharpe,
        "sortino_ratio_zero_target": sortino,
        "maximum_drawdown": float(drawdown.min()),
        "daily_win_rate": float(daily.gt(0).mean()),
        "average_daily_turnover": float(sample["turnover"].mean()),
        "total_transaction_cost_return": float(sample["transaction_cost_return"].sum()),
        "average_gross_exposure": float(sample["gross_exposure"].mean()),
        "average_net_exposure": float(sample["net_exposure"].mean()),
        "btc_benchmark_return": float(btc.iloc[-1] / btc.iloc[0] - 1.0),
        "equal_weight_benchmark_return": float(equal.iloc[-1] / equal.iloc[0] - 1.0),
    }


def _capped_allocations(scores: pd.Series, *, total: float, cap: float) -> pd.Series:
    allocations = pd.Series(0.0, index=scores.index)
    remaining = scores[scores.gt(0)].astype(float).copy()
    remaining_total = float(total)
    while len(remaining) and remaining_total > 1e-12:
        proposed = remaining_total * remaining / remaining.sum()
        capped = proposed[proposed > cap + 1e-12]
        if capped.empty:
            allocations.loc[proposed.index] += proposed
            break
        for symbol in capped.index:
            available = max(0.0, cap - allocations[symbol])
            addition = min(available, remaining_total)
            allocations[symbol] += addition
            remaining_total -= addition
            remaining = remaining.drop(symbol)
    return allocations


def _rsi(close: pd.Series, period: int) -> pd.Series:
    difference = close.diff()
    gain = difference.clip(lower=0.0)
    loss = -difference.clip(upper=0.0)
    average_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss.replace(0.0, np.nan)
    value = 100.0 - 100.0 / (1.0 + relative_strength)
    return value.where(average_loss.ne(0.0), 100.0)


def _log_gaussian_density(
    values: np.ndarray, means: np.ndarray, variances: np.ndarray
) -> np.ndarray:
    residual = values[:, None, :] - means[None, :, :]
    return -0.5 * np.sum(
        np.log(2.0 * np.pi * variances)[None, :, :] + residual * residual / variances[None, :, :],
        axis=2,
    )


def _logsumexp(values: np.ndarray, axis: int | None = None) -> np.ndarray:
    maximum = np.max(values, axis=axis, keepdims=True)
    result = maximum + np.log(np.sum(np.exp(values - maximum), axis=axis, keepdims=True))
    return np.squeeze(result, axis=axis) if axis is not None else result.squeeze()


def _forward_log(
    log_emission: np.ndarray,
    start_probability: np.ndarray,
    transition: np.ndarray,
) -> tuple[np.ndarray, float]:
    log_transition = np.log(np.maximum(transition, 1e-300))
    log_alpha = np.empty_like(log_emission)
    log_alpha[0] = np.log(np.maximum(start_probability, 1e-300)) + log_emission[0]
    for row in range(1, len(log_emission)):
        log_alpha[row] = log_emission[row] + _logsumexp(
            log_alpha[row - 1, :, None] + log_transition, axis=0
        )
    return log_alpha, float(_logsumexp(log_alpha[-1]))


def _backward_log(log_emission: np.ndarray, transition: np.ndarray) -> np.ndarray:
    log_transition = np.log(np.maximum(transition, 1e-300))
    log_beta = np.zeros_like(log_emission)
    for row in range(len(log_emission) - 2, -1, -1):
        log_beta[row] = _logsumexp(
            log_transition + log_emission[row + 1, None, :] + log_beta[row + 1, None, :],
            axis=1,
        )
    return log_beta


def _utc(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tz is None else timestamp.tz_convert("UTC")
