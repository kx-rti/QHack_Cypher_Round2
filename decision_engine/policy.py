"""Deterministic adaptive policy (Cypher.pdf, pp. 12-13, 15). Pure logic: no crypto imports.

The latency feasibility check reflects Rallis et al. (2025, Items 8-10, p. 2): communication
latency in hybrid feedback loops can negate quantum speedup gains.
"""
import json
import os
from dataclasses import asdict, dataclass, field
from math import log

from simulation.network import overhead_ms

from .config import load_config

PROFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "benchmarking", "results.json")
_DOWNGRADE_WARNING = "Downgraded for performance. Re-key with PQC when conditions improve."


@dataclass
class Conditions:
    sensitivity: str  # LOW | MEDIUM | HIGH | CRITICAL
    lifetime_years: float  # how long the data must stay secret
    latency_budget_ms: float  # max extra delay security may add
    bandwidth_kbps: float
    data_bytes: int = 10_000


@dataclass
class Decision:
    mode: str
    need: float
    pressure: float
    net: float
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    estimates_ms: dict = field(default_factory=dict)
    floor_applied: bool = False
    downgraded: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def load_profile(path: str | None = None) -> dict:
    with open(path or PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def compute_scores(c: Conditions, config: dict) -> dict:
    """Normalized 0-100 inputs plus the need, pressure and net scores."""
    w = config["weights"]
    sens = float(config["sensitivity_levels"][c.sensitivity])
    life = clamp(c.lifetime_years / 15.0 * 100.0)
    lat_p = clamp(100.0 * log(500.0 / max(c.latency_budget_ms, 1e-6)) / log(100.0))  # <=5 ms: 100, >=500 ms: 0
    bw_p = clamp(100.0 * log(100_000.0 / max(c.bandwidth_kbps, 1e-6)) / log(1000.0))  # <=100 kbps: 100, >=100 Mbps: 0
    need = w["sens"] * sens + w["life"] * life
    pressure = w["lat"] * lat_p + w["bw"] * bw_p
    return {"sens": sens, "life": life, "lat_p": lat_p, "bw_p": bw_p,
            "need": need, "pressure": pressure, "net": need - pressure}


def safety_floor_applies(c: Conditions, config: dict) -> bool:
    floor = config["safety_floor"]
    return c.sensitivity in floor["min_sensitivity"] and c.lifetime_years >= floor["min_lifetime_years"]


def decide(c: Conditions, profile: dict, config: dict | None = None) -> Decision:
    config = config or load_config()
    t_high, t_low = config["thresholds"]["t_high"], config["thresholds"]["t_low"]
    s = compute_scores(c, config)
    need, pressure, net = s["need"], s["pressure"], s["net"]

    d = Decision("HYBRID", need, pressure, net)
    d.estimates_ms = {m: overhead_ms(m, c, profile) for m in profile["modes"]}
    d.reasons.append(f"Security need {need:.0f} vs performance pressure {pressure:.0f} (net {net:+.1f}).")
    if net >= t_high:
        d.mode = "QUANTUM_SAFE"
        d.reasons.append("Security need clearly exceeds performance pressure.")
    elif net <= t_low:
        d.mode = "CLASSICAL"
        d.reasons.append("Performance pressure clearly exceeds security need.")
    else:
        d.reasons.append("Security and performance are balanced, so combine both.")

    floor = safety_floor_applies(c, config)
    if floor and d.mode == "CLASSICAL":
        d.mode = "HYBRID"
        d.floor_applied = True
        d.reasons.append("Safety floor: sensitive, long-lived data is never sent classical-only.")

    if d.mode != "CLASSICAL" and d.estimates_ms[d.mode] > c.latency_budget_ms:
        if floor:
            d.floor_applied = True
            d.warnings.append(
                f"{d.mode} needs ~{d.estimates_ms[d.mode]:.1f} ms but budget is {c.latency_budget_ms:g} ms. "
                "Keeping it because of the safety floor; consider relaxing the latency budget.")
        else:
            d.mode = "CLASSICAL"
            d.downgraded = True
            d.reasons.append("Feasibility check: post-quantum setup would exceed the latency budget on this link.")
            d.warnings.append(_DOWNGRADE_WARNING)
    elif d.mode == "CLASSICAL" and d.estimates_ms["HYBRID"] > c.latency_budget_ms:
        # The score alone chose CLASSICAL, but the demo must still surface that PQC would not fit (Cypher.pdf, p. 16).
        d.reasons.append(
            f"Post-quantum setup would not fit either: HYBRID needs ~{d.estimates_ms['HYBRID']:.1f} ms "
            f"against a {c.latency_budget_ms:g} ms budget.")
        d.warnings.append(_DOWNGRADE_WARNING)
    return d
