"""Anti-flapping controller and bandwidth forecaster (Upgrade A).

Forecasting informs inputs only; the deterministic policy still decides (Cypher.pdf, Sec. 12.5, p. 16).
"""
from dataclasses import replace

from .config import load_config
from .policy import Conditions, decide, safety_floor_applies


def _boundary_margin(current: str, candidate: str, net: float, config: dict) -> float:
    """How far net sits past the threshold separating current from candidate."""
    t_high, t_low = config["thresholds"]["t_high"], config["thresholds"]["t_low"]
    if candidate == "QUANTUM_SAFE":
        return net - t_high
    if candidate == "CLASSICAL":
        return t_low - net
    return t_high - net if current == "QUANTUM_SAFE" else net - t_low


class HysteresisController:
    """A candidate mode must persist for several samples before it replaces the current mode."""

    def __init__(self, profile: dict, persistence_samples: int = 3, net_margin: float = 8.0,
                 config: dict | None = None):
        self.profile = profile
        self.persistence_samples = max(1, persistence_samples)
        self.net_margin = net_margin
        self.config = config or load_config()
        self.current_mode: str | None = None
        self.candidate_mode: str | None = None
        self.streak = 0
        self.history: list[dict] = []

    def _commit(self, mode: str, reason: str, sample: dict) -> None:
        self.current_mode = mode
        self.candidate_mode = None
        self.streak = 0
        sample.update(switched=True, switch_reason=reason)

    def step(self, c: Conditions) -> dict:
        d = decide(c, self.profile, self.config)
        sample = {"proposed_mode": d.mode, "net": d.net, "switched": False, "switch_reason": ""}

        if self.current_mode is None:
            self._commit(d.mode, "initial mode", sample)
        elif d.mode == self.current_mode:
            self.candidate_mode, self.streak = None, 0
        elif safety_floor_applies(c, self.config) and self.current_mode == "CLASSICAL":
            self._commit(d.mode, "safety floor (immediate)", sample)
        else:
            self.streak = self.streak + 1 if d.mode == self.candidate_mode else 1
            self.candidate_mode = d.mode
            if self.persistence_samples > 1:
                if self.streak >= self.persistence_samples:
                    self._commit(d.mode, f"persisted {self.streak} samples", sample)
            elif d.downgraded or _boundary_margin(self.current_mode, d.mode, d.net, self.config) >= self.net_margin:
                self._commit(d.mode, "net margin exceeded", sample)

        sample["mode"] = self.current_mode
        sample["streak"] = self.streak
        self.history.append(sample)
        return sample


class EWMAForecaster:
    """B_hat(t+1) = alpha * B(t) + (1 - alpha) * B_hat(t)."""

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.level: float | None = None

    def update(self, value: float) -> float:
        self.level = value if self.level is None else self.alpha * value + (1 - self.alpha) * self.level
        return self.level


def _linear_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x_mean, y_mean = (n - 1) / 2.0, sum(values) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    return numerator / sum((i - x_mean) ** 2 for i in range(n))


def predict_next_bandwidth_kbps(history: list[float], alpha: float = 0.3, trend_window: int = 5) -> float:
    """EWMA level plus the least-squares slope of the most recent samples; floored at 1 kbps."""
    if not history:
        raise ValueError("history must not be empty")
    forecaster = EWMAForecaster(alpha)
    for value in history:
        forecaster.update(value)
    return max(1.0, forecaster.level + _linear_slope(history[-trend_window:]))


def replay_trace(samples: list[dict], base: Conditions, profile: dict, persistence_samples: int = 3,
                 net_margin: float = 8.0, ewma_alpha: float = 0.3, config: dict | None = None) -> dict:
    """Compares Reactive switching with Hysteresis + EWMA forecasting over a bandwidth trace.

    Neither policy sees the current sample: reactive uses the last observed value, the other uses a
    forecast built from the same history. Each mode is then scored against the actual bandwidth.
    """
    config = config or load_config()
    controller = HysteresisController(profile, persistence_samples, net_margin, config)
    history: list[float] = []
    steps = []
    reactive_prev = None
    reactive_switches = hysteresis_switches = 0
    reactive_violations = hysteresis_violations = 0
    forecast_error = naive_error = 0.0
    scored = 0

    for sample in samples:
        actual = max(float(sample["bandwidth_kbps"]), 1.0)
        budget = float(sample["latency_budget_ms"])
        last = history[-1] if history else actual
        forecast = predict_next_bandwidth_kbps(history, ewma_alpha) if history else actual

        reactive = decide(replace(base, bandwidth_kbps=last, latency_budget_ms=budget), profile, config)
        managed = controller.step(replace(base, bandwidth_kbps=forecast, latency_budget_ms=budget))

        truth = decide(replace(base, bandwidth_kbps=actual, latency_budget_ms=budget), profile, config)
        reactive_violations += truth.estimates_ms[reactive.mode] > budget
        hysteresis_violations += truth.estimates_ms[managed["mode"]] > budget

        if reactive_prev is not None and reactive.mode != reactive_prev:
            reactive_switches += 1
        if managed["switched"] and steps:
            hysteresis_switches += 1
        reactive_prev = reactive.mode

        if history:
            forecast_error += abs(forecast - actual)
            naive_error += abs(last - actual)
            scored += 1

        steps.append({
            "timestamp": sample["timestamp"],
            "bandwidth_kbps": actual,
            "ewma_bandwidth_kbps": forecast,
            "latency_budget_ms": budget,
            "reactive_mode": reactive.mode,
            "hysteresis_mode": managed["mode"],
        })
        history.append(actual)

    reduction = 100.0 * (reactive_switches - hysteresis_switches) / reactive_switches if reactive_switches else 0.0
    return {
        "steps": steps,
        "reactive_switches": reactive_switches,
        "hysteresis_switches": hysteresis_switches,
        "flapping_reduction_pct": reduction,
        "reactive_budget_violations": reactive_violations,
        "hysteresis_budget_violations": hysteresis_violations,
        "forecast_mae_kbps": forecast_error / scored if scored else 0.0,
        "naive_mae_kbps": naive_error / scored if scored else 0.0,
    }
