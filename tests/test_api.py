import pytest
from fastapi.testclient import TestClient

from api.main import app
from decision_engine.policy import load_profile
from simulation import dataset_loader as dl
from tests.test_datasets import WIRESHARK, _write_zip

client = TestClient(app)
BALANCED = {"sensitivity": "MEDIUM", "lifetime_years": 5, "latency_budget_ms": 50, "bandwidth_kbps": 20000,
            "data_bytes": 10000}


def test_health():
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["benchmarks_loaded"] and body["pqc_backend"]


def test_benchmarks_returns_the_real_file_unchanged():
    assert client.get("/api/benchmarks").json() == load_profile()


def test_decide():
    body = client.post("/api/decide", json={"conditions": BALANCED}).json()
    assert body["mode"] == "HYBRID"
    assert abs(body["contributions_sum"] - body["net"]) < 1e-6
    assert len(body["overhead_breakdown"]) == 3 and body["data_origin"] == "DETERMINISTIC_POLICY"


def test_decide_with_policy_override():
    payload = {"conditions": BALANCED, "policy_override": {"thresholds": {"t_low": 10.0}}}
    assert client.post("/api/decide", json=payload).json()["mode"] == "CLASSICAL"


@pytest.mark.parametrize("payload", [
    {"conditions": {**BALANCED, "sensitivity": "EXTREME"}},
    {"conditions": {**BALANCED, "bandwidth_kbps": 0}},
    {"conditions": BALANCED, "unknown": 1},
    {"conditions": BALANCED, "policy_override": {"thresholds": {"t_high": -50.0, "t_low": 0.0}}},
])
def test_decide_rejects_invalid_input(payload):
    assert client.post("/api/decide", json=payload).status_code == 422


def test_scenarios():
    body = client.get("/api/scenarios").json()
    assert len(body["scenarios"]) == 4 and body["timeline"][0] == "1. Speed priority"
    assert [s["mode"] for s in body["scenarios"]] == ["CLASSICAL", "QUANTUM_SAFE", "HYBRID", "CLASSICAL"]


@pytest.mark.parametrize("mode,wire", [("CLASSICAL", 64), ("QUANTUM_SAFE", 2272), ("HYBRID", 2336)])
def test_roundtrip(mode, wire):
    body = client.post("/api/crypto/roundtrip", json={"mode": mode}).json()
    assert body["correct"] and body["handshake_bytes"] == wire
    assert body["ciphertext_bytes"] == body["plaintext_bytes"] + 28


def test_policy_config():
    assert client.get("/api/policy/config").json()["weights"]["lat"] == 0.65


def test_sensitivity_map():
    body = client.post("/api/policy/sensitivity-map",
                       json={"conditions": BALANCED, "lat_steps": 5, "bw_steps": 4}).json()
    assert len(body["cells"]) == 5 and len(body["cells"][0]) == 4


@pytest.mark.parametrize("use_socket", [True, False])
def test_handshake(use_socket):
    body = client.post("/api/crypto/handshake", json={"mode": "HYBRID", "use_socket": use_socket}).json()
    assert body["success"] and body["keys_match"]


def test_handshake_tamper_is_reported_with_200():
    response = client.post("/api/crypto/handshake", json={"mode": "HYBRID", "tamper_target": "signature"})
    assert response.status_code == 200
    body = response.json()
    assert not body["success"] and body["error_message"]
    assert body["client_key_fp"] == ""


def test_workloads():
    body = client.get("/api/workloads").json()
    assert len(body["workloads"]) == 5 and body["workloads"][0]["default_simulation"]


def test_simulate_session():
    response = client.post("/api/workloads/simulate-session",
                           json={"workload_id": "scientific", "num_messages": 25, "rekey_interval": 10,
                                 "include_auth_handshake": True})
    body = response.json()
    assert response.status_code == 200 and body["num_messages"] == 25 and body["modes"]["HYBRID"]["handshakes"] == 3


def test_simulate_session_validation():
    assert client.post("/api/workloads/simulate-session", json={}).status_code == 422
    assert client.post("/api/workloads/simulate-session", json={"workload_id": "nope"}).status_code == 404


def test_datasets_summary():
    body = client.get("/api/datasets/summary").json()
    assert {d["id"] for d in body["datasets"]} >= {"cloud", "wireshark", "ipasn"}


def test_replay_with_missing_archive_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "search_paths", lambda: [str(tmp_path)])
    response = client.post("/api/datasets/replay", json={"dataset_name": "wireshark_midterm53"})
    assert response.status_code == 404 and "not found" in response.json()["detail"]


def test_replay_with_archive(tmp_path, monkeypatch):
    _write_zip(str(tmp_path), "archive (5).zip", "Midterm_53_group.csv", WIRESHARK)
    monkeypatch.setattr(dl, "search_paths", lambda: [str(tmp_path)])
    body = client.post("/api/datasets/replay", json={"dataset_name": "wireshark_midterm53"}).json()
    assert len(body["steps"]) == 4 and body["data_origin"] == "EXTERNAL_DATASET_TRACE"


def test_reports():
    payload = {"conditions": BALANCED, "workload_id": "scientific"}
    pdf = client.post("/api/reports/pdf", json=payload)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert "AdaptiveCrypt_Report.pdf" in pdf.headers["content-disposition"]
    csv = client.post("/api/reports/csv", json=payload)
    assert csv.status_code == 200 and csv.text.startswith("section,item,metric")
    assert "AdaptiveCrypt_Telemetry.csv" in csv.headers["content-disposition"]


def test_report_accepts_handshake_result():
    hs = client.post("/api/crypto/handshake", json={"mode": "CLASSICAL", "use_socket": False}).json()
    response = client.post("/api/reports/pdf", json={"conditions": BALANCED, "handshake_result": hs})
    assert response.status_code == 200
