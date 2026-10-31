"""Signed per-factor contributions and the 2D latency/bandwidth decision map (Upgrade A)."""
from dataclasses import replace

from .config import load_config
from .policy import Conditions, compute_scores, decide

MODE_CODES = {"CLASSICAL": 0, "HYBRID": 1, "QUANTUM_SAFE": 2}


def explain_decision(c: Conditions, profile: dict, config: dict | None = None) -> dict:
    """Decomposes net into additive terms: C_sens + C_life + C_lat + C_bw == net."""
    config = config or load_config()
    w = config["weights"]
    s = compute_scores(c, config)
    decision = decide(c, profile, config)
    rows = [
        ("sensitivity", c.sensitivity, s["sens"], w["sens"], +1, "Data sensitivity"),
        ("lifetime", c.lifetime_years, s["life"], w["life"], +1, "Confidentiality lifetime"),
        ("latency", c.latency_budget_ms, s["lat_p"], w["lat"], -1, "Latency budget"),
        ("bandwidth", c.bandwidth_kbps, s["bw_p"], w["bw"], -1, "Available bandwidth"),
    ]
    factors = []
    for factor, raw, score, weight, sign, label in rows:
        contribution = sign * weight * score
        direction = "toward_pqc" if contribution > 0 else "toward_classical" if contribution < 0 else "neutral"
        pushed = "post-quantum" if sign > 0 else "classical"
        factors.append({
            "factor": factor,
            "raw_value": raw,
            "normalized_score": score,
            "weight": weight,
            "signed_contribution": contribution,
            "direction": direction,
            "summary_text": f"{label} pushed {contribution:+.1f} toward {pushed}.",
        })
    total = sum(f["signed_contribution"] for f in factors)
    assert abs(total - decision.net) < 1e-6
    return {"decision": decision, "factors": factors, "contributions_sum": total}


def _log_space(lo: float, hi: float, steps: int) -> list[float]:
    if steps == 1:
        return [lo]
    ratio = (hi / lo) ** (1.0 / (steps - 1))
    return [lo * ratio ** i for i in range(steps - 1)] + [hi]


def generate_sensitivity_grid(c: Conditions, profile: dict, lat_steps: int = 30, bw_steps: int = 30,
                              config: dict | None = None) -> dict:
    """Sweeps log-spaced latency [1, 500] ms and bandwidth [100, 100000] kbps. cells[i][j] is lat i, bw j."""
    config = config or load_config()
    lat_values = _log_space(1.0, 500.0, lat_steps)
    bw_values = _log_space(100.0, 100_000.0, bw_steps)
    cells = []
    for lat in lat_values:
        row = []
        for bw in bw_values:
            d = decide(replace(c, latency_budget_ms=lat, bandwidth_kbps=bw), profile, config)
            row.append({"lat_ms": lat, "bw_kbps": bw, "mode": d.mode, "mode_code": MODE_CODES[d.mode],
                        "net": d.net, "downgraded": d.downgraded})
        cells.append(row)
    return {"lat_values": lat_values, "bw_values": bw_values, "cells": cells}
