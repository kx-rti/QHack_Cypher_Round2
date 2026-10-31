import pytest

from decision_engine.config import DEFAULT_CONFIG, load_config, merge_config
from decision_engine.explain import explain_decision, generate_sensitivity_grid
from decision_engine.hysteresis import (EWMAForecaster, HysteresisController, predict_next_bandwidth_kbps,
                                        replay_trace)
from decision_engine.policy import Conditions, decide

FIXTURE = {  # test fixture, NOT a benchmark
    "modes": {"CLASSICAL": {"handshake_ms_median": 0.1, "handshake_bytes": 64},
              "QUANTUM_SAFE": {"handshake_ms_median": 0.2, "handshake_bytes": 2272},
              "HYBRID": {"handshake_ms_median": 0.3, "handshake_bytes": 2336}},
    "aes": {"mb_per_s": 1000}}

SPEED = Conditions("LOW", 0.1, 10, 10_000)
BALANCED = Conditions("MEDIUM", 5, 50, 20_000)
CONSTRAINED = Conditions("MEDIUM", 5, 20, 300)


def test_speed_priority():
    assert decide(SPEED, FIXTURE).mode == "CLASSICAL"


def test_max_security():
    assert decide(Conditions("CRITICAL", 25, 200, 100_000), FIXTURE).mode == "QUANTUM_SAFE"


def test_balanced():
    assert decide(BALANCED, FIXTURE).mode == "HYBRID"


def test_constrained():
    d = decide(CONSTRAINED, FIXTURE)
    assert d.mode == "CLASSICAL"
    assert any("Re-key with PQC" in w for w in d.warnings)


def test_safety_floor():
    d = decide(Conditions("HIGH", 15, 5, 100), FIXTURE)
    assert d.mode == "HYBRID" and d.warnings and d.floor_applied


def test_lowest_bandwidth_no_crash():
    assert decide(Conditions("MEDIUM", 1, 100, 100), FIXTURE).reasons


def test_zero_lifetime():
    # Cypher.pdf's test matrix lists CLASSICAL here, but its own formula gives need 6, pressure 0,
    # net +6, which is HYBRID. The formula is authoritative; see README "Specification corrections".
    d = decide(Conditions("LOW", 0, 500, 100_000), FIXTURE)
    assert d.need == pytest.approx(6.0)
    assert d.pressure == pytest.approx(0.0)
    assert d.mode == "HYBRID"


@pytest.mark.parametrize("conditions,need,pressure,net", [
    (SPEED, 6.27, 66.89, -60.62),  # the spec's table has 67.15 / -60.88; recomputed from its formula
    (Conditions("CRITICAL", 25, 200, 100_000), 100.0, 12.93, 87.07),
    (BALANCED, 40.33, 40.65, -0.32),
    (CONSTRAINED, 40.33, 74.87, -34.53),
    (Conditions("HIGH", 15, 5, 100), 88.0, 100.0, -12.0),
])
def test_hand_calculated_scores(conditions, need, pressure, net):
    d = decide(conditions, FIXTURE)
    assert d.need == pytest.approx(need, abs=0.01)
    assert d.pressure == pytest.approx(pressure, abs=0.01)
    assert d.net == pytest.approx(net, abs=0.01)


def test_every_decision_has_a_reason():
    for c in (SPEED, BALANCED, CONSTRAINED):
        assert decide(c, FIXTURE).reasons


def test_yaml_matches_round1_defaults():
    assert load_config() == DEFAULT_CONFIG


def test_config_missing_file_falls_back():
    assert load_config("does-not-exist.yaml") == DEFAULT_CONFIG


def test_policy_override_changes_decision():
    config = merge_config(load_config(), {"thresholds": {"t_low": -70.0}})
    assert decide(SPEED, FIXTURE, config).mode == "HYBRID"


def test_factor_contributions_sum_to_net():
    for c in (SPEED, BALANCED, CONSTRAINED, Conditions("CRITICAL", 25, 200, 100_000)):
        out = explain_decision(c, FIXTURE)
        assert abs(out["contributions_sum"] - out["decision"].net) < 1e-6
        assert len(out["factors"]) == 4


def test_sensitivity_grid_generation():
    grid = generate_sensitivity_grid(BALANCED, FIXTURE, lat_steps=40, bw_steps=40)
    assert len(grid["cells"]) == 40 and all(len(row) == 40 for row in grid["cells"])
    assert grid["lat_values"][0] == pytest.approx(1.0) and grid["lat_values"][-1] == pytest.approx(500.0)
    assert grid["bw_values"][0] == pytest.approx(100.0) and grid["bw_values"][-1] == pytest.approx(100_000.0)
    modes = {cell["mode"] for row in grid["cells"] for cell in row}
    assert {"CLASSICAL", "HYBRID"} <= modes
    assert all(cell["mode_code"] in (0, 1, 2) for row in grid["cells"] for cell in row)


def test_hysteresis_prevents_single_spike_flapping():
    controller = HysteresisController(FIXTURE, persistence_samples=3)
    controller.step(BALANCED)
    assert controller.current_mode == "HYBRID"
    controller.step(CONSTRAINED)  # a one-sample spike
    assert controller.current_mode == "HYBRID"
    controller.step(BALANCED)
    assert controller.current_mode == "HYBRID" and controller.streak == 0
    for _ in range(3):
        controller.step(CONSTRAINED)
    assert controller.current_mode == "CLASSICAL"


def test_hysteresis_safety_floor_switches_immediately():
    controller = HysteresisController(FIXTURE, persistence_samples=5)
    controller.step(CONSTRAINED)
    assert controller.current_mode == "CLASSICAL"
    controller.step(Conditions("CRITICAL", 20, 20, 300))
    assert controller.current_mode != "CLASSICAL"


def test_hysteresis_margin_rule_with_single_sample_persistence():
    controller = HysteresisController(FIXTURE, persistence_samples=1, net_margin=8.0)
    controller.step(BALANCED)
    controller.step(Conditions("MEDIUM", 5, 20, 900))  # past t_low by under 8 points: stays
    assert controller.current_mode == "HYBRID"
    controller.step(SPEED)  # net -60: well past the boundary
    assert controller.current_mode == "CLASSICAL"


def test_ewma_forecaster():
    forecaster = EWMAForecaster(alpha=0.5)
    assert forecaster.update(100.0) == 100.0
    assert forecaster.update(200.0) == pytest.approx(150.0)
    assert predict_next_bandwidth_kbps([1000.0] * 10) == pytest.approx(1000.0)
    assert predict_next_bandwidth_kbps([500.0, 400.0, 300.0, 200.0, 100.0]) >= 1.0
    with pytest.raises(ValueError):
        predict_next_bandwidth_kbps([])


def test_replay_trace_counts_switches():
    trace = [{"timestamp": float(i), "bandwidth_kbps": 300.0 if i % 2 else 20_000.0, "latency_budget_ms": 50.0}
             for i in range(40)]
    out = replay_trace(trace, Conditions("MEDIUM", 5, 50, 20_000), FIXTURE, persistence_samples=3)
    assert len(out["steps"]) == 40
    assert out["hysteresis_switches"] <= out["reactive_switches"]
