"""Loads policy.yaml, falling back to the Round 1 defaults when the file is absent."""
import copy
import os

import yaml

POLICY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy.yaml")

DEFAULT_CONFIG = {
    "sensitivity_levels": {"LOW": 10, "MEDIUM": 45, "HIGH": 80, "CRITICAL": 100},
    "weights": {"sens": 0.6, "life": 0.4, "lat": 0.65, "bw": 0.35},
    "thresholds": {"t_high": 25.0, "t_low": -25.0},
    "safety_floor": {"min_sensitivity": ["HIGH", "CRITICAL"], "min_lifetime_years": 10.0},
    "hysteresis": {"persistence_samples": 3, "net_margin": 8.0, "ewma_alpha": 0.3},
}


def merge_config(base: dict, override: dict | None) -> dict:
    """Returns base with override's sections merged in; None values are ignored."""
    merged = copy.deepcopy(base)
    for section, values in (override or {}).items():
        if isinstance(values, dict) and isinstance(merged.get(section), dict):
            merged[section].update({k: v for k, v in values.items() if v is not None})
        elif values is not None:
            merged[section] = values
    return merged


def load_config(path: str = POLICY_PATH) -> dict:
    if not os.path.exists(path):
        return copy.deepcopy(DEFAULT_CONFIG)
    with open(path, encoding="utf-8") as f:
        return merge_config(DEFAULT_CONFIG, yaml.safe_load(f) or {})
