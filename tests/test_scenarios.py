import csv
import io
from dataclasses import replace

import pytest

from decision_engine.policy import decide, load_profile
from reporting.generator import generate_csv_report, generate_pdf_report
from simulation.scenarios import SCENARIOS, TIMELINE
from simulation.sessions import (AES_GCM_OVERHEAD_BYTES, CURVE_POINTS, aes_gcm_rekey_bound_seconds, num_handshakes,
                                 simulate_session)
from simulation.workloads import WORKLOADS, WORKLOADS_BY_ID


@pytest.fixture(scope="module")
def profile():
    return load_profile()


def test_benchmark_profile_is_real_and_complete(profile):
    assert {m: profile["modes"][m]["handshake_bytes"] for m in profile["modes"]} == {
        "CLASSICAL": 64, "QUANTUM_SAFE": 2272, "HYBRID": 2336}
    assert all(profile["modes"][m]["handshake_ms_median"] > 0 for m in profile["modes"])
    assert profile["aes"]["mb_per_s"] > 0
    assert profile["aes"]["ciphertext_overhead_bytes"] == 28
    assert profile["signatures"]["ML-DSA-65"]["signature_bytes"] == 3309
    assert profile["signatures"]["Ed25519"]["signature_bytes"] == 64
    assert profile["pqc_backend"] and profile["host_metadata"]["timestamp"]


def test_timeline_switches_at_least_3_times(profile):
    modes = [decide(SCENARIOS[name], profile).mode for name in TIMELINE]
    switches = sum(a != b for a, b in zip(modes, modes[1:]))
    assert switches >= 3
    assert modes == ["CLASSICAL", "QUANTUM_SAFE", "HYBRID", "CLASSICAL"]


def test_handshake_count_formula():
    assert num_handshakes(1, 50) == 1
    assert num_handshakes(50, 50) == 1
    assert num_handshakes(51, 50) == 2
    assert num_handshakes(100, 50) == 2


def test_rekey_time_bound_matches_ricci():
    assert aes_gcm_rekey_bound_seconds() == pytest.approx(515.39, abs=0.01)


def test_workload_profiles_and_session_amortization(profile):
    assert len(WORKLOADS) == 5
    for workload in WORKLOADS:
        session = simulate_session(workload, profile)
        assert session["data_origin"] == "SIMULATED_NETWORK_MODEL"
        assert set(session["modes"]) == {"CLASSICAL", "QUANTUM_SAFE", "HYBRID"}
        curve = {p["n"]: p for p in session["amortization_curve"]}
        assert sorted(curve) == list(CURVE_POINTS)
        for mode in session["modes"]:
            # Strictly decreasing only inside the first key's window. Each re-key adds one handshake
            # cost, so across re-keys the curve settles near hs/R rather than falling forever.
            inside = [curve[n][mode] for n in CURVE_POINTS if n <= workload.rekey_interval_messages]
            assert all(a > b for a, b in zip(inside, inside[1:]))
            assert curve[500][mode] < curve[1][mode]


def test_session_without_rekey_is_strictly_decreasing(profile):
    session = simulate_session(replace(WORKLOADS[0], rekey_interval_messages=10_000), profile)
    for mode in session["modes"]:
        values = [p[mode] for p in session["amortization_curve"]]
        assert all(a > b for a, b in zip(values, values[1:]))


def test_session_total_matches_formula(profile):
    w = WORKLOADS_BY_ID["scientific"]
    m = simulate_session(w, profile)["modes"]["HYBRID"]
    handshakes = num_handshakes(w.num_messages, w.rekey_interval_messages)
    assert m["handshakes"] == handshakes
    assert m["total_crypto_wire_bytes"] == handshakes * 2336 + w.num_messages * AES_GCM_OVERHEAD_BYTES


def test_authenticated_session_costs_more(profile):
    w = WORKLOADS_BY_ID["financial"]
    plain = simulate_session(w, profile)["modes"]["HYBRID"]
    auth = simulate_session(w, profile, include_authenticated_handshake=True)["modes"]["HYBRID"]
    assert auth["total_crypto_wire_bytes"] > plain["total_crypto_wire_bytes"]


def test_pdf_and_csv_report_generation(profile):
    conditions = WORKLOADS_BY_ID["healthcare"].conditions
    pdf = generate_pdf_report(conditions, "healthcare", profile=profile)
    assert pdf.startswith(b"%PDF-") and len(pdf) > 5_000

    text = generate_csv_report(conditions, "healthcare", profile=profile).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows and all(r["data_origin"] in ("MEASURED_LOCAL_CRYPTO", "SIMULATED_NETWORK_MODEL", "DETERMINISTIC_POLICY")
                        for r in rows)
    median = next(r for r in rows if r["item"] == "HYBRID" and r["metric"] == "handshake_ms_median")
    assert float(median["value"]) == pytest.approx(profile["modes"]["HYBRID"]["handshake_ms_median"])
    assert sum(r["section"] == "scenario_matrix" and r["metric"] == "mode" for r in rows) == 4
    assert len({r["item"] for r in rows if r["section"] == "session" and r["metric"] == "recommended_mode"}) == 5


def test_reports_never_use_the_test_fixture(profile):
    text = generate_csv_report(profile=profile).decode("utf-8")
    assert "fixture" not in text.lower()
