"""FastAPI backend for AdaptiveCrypt. Run with: uvicorn api.main:app --reload --port 8000"""
import platform
import sys
import threading
from dataclasses import asdict, replace

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from benchmarking.run_benchmarks import run_all
from crypto_suite import pqc
from crypto_suite.handshake import authenticated_handshake
from crypto_suite.suite import secure_roundtrip
from decision_engine.config import load_config, merge_config
from decision_engine.explain import explain_decision, generate_sensitivity_grid
from decision_engine.hysteresis import replay_trace
from decision_engine.policy import Conditions, decide, load_profile
from reporting.generator import generate_csv_report, generate_pdf_report
from simulation import dataset_loader
from simulation.network import overhead_breakdown
from simulation.scenarios import SCENARIOS, TIMELINE
from simulation.sessions import simulate_session
from simulation.workloads import WORKLOADS, WORKLOADS_BY_ID, WorkloadProfile

from . import schemas as s

app = FastAPI(title="AdaptiveCrypt API", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

_benchmark_lock = threading.Lock()
# Replay defaults sit near the HYBRID/CLASSICAL boundary, so bandwidth changes can flip the mode.
_REPLAY_BASE = Conditions("MEDIUM", 5.0, 20.0, 300.0, 10_000)


def _profile() -> dict:
    try:
        return load_profile()
    except FileNotFoundError:
        raise HTTPException(503, "No benchmark profile yet. Run: python -m benchmarking.run_benchmarks") from None


def _conditions(model: s.ConditionsModel) -> Conditions:
    return Conditions(**model.model_dump())


def _config(override: s.PolicyOverride | None) -> dict:
    config = merge_config(load_config(), override.model_dump(exclude_none=True) if override else None)
    if config["thresholds"]["t_low"] >= config["thresholds"]["t_high"]:
        raise HTTPException(422, "t_low must be below t_high.")
    return config


def _decision_payload(c: Conditions, profile: dict, config: dict) -> dict:
    explained = explain_decision(c, profile, config)
    d = explained["decision"]
    rows = [overhead_breakdown(m, c, profile) for m in profile["modes"]]
    return {
        **{k: v for k, v in d.to_dict().items()},
        "within_budget": {r["mode"]: r["total_ms"] <= c.latency_budget_ms for r in rows},
        "overhead_breakdown": [{**r, "within_budget": r["total_ms"] <= c.latency_budget_ms} for r in rows],
        "factor_contributions": explained["factors"],
        "contributions_sum": explained["contributions_sum"],
        "data_origin": "DETERMINISTIC_POLICY",
    }


@app.get("/api/health", response_model=s.HealthResponse)
def health():
    try:
        load_profile()
        loaded = True
    except FileNotFoundError:
        loaded = False
    return {
        "status": "ok",
        "pqc_backend": pqc.BACKEND,
        "pqc_fallback": pqc.IS_FALLBACK,
        "host_os": platform.platform(),
        "host_cpu": platform.processor() or "unknown",
        "python_version": sys.version.split()[0],
        "benchmarks_loaded": loaded,
    }


@app.get("/api/benchmarks", response_model=s.BenchmarkProfileResponse)
def get_benchmarks():
    return _profile()


@app.post("/api/benchmarks/run", response_model=s.BenchmarkProfileResponse)
def run_benchmarks(req: s.RunBenchmarkRequest):
    if not _benchmark_lock.acquire(blocking=False):
        raise HTTPException(409, "A benchmark run is already in progress.")
    try:
        return run_all(req.runs, req.warmup)
    finally:
        _benchmark_lock.release()


@app.post("/api/decide", response_model=s.DecisionResponse)
def post_decide(req: s.DecisionRequest):
    return _decision_payload(_conditions(req.conditions), _profile(), _config(req.policy_override))


@app.get("/api/scenarios", response_model=s.ScenariosResponse)
def get_scenarios():
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = None
    items = []
    for name in TIMELINE:
        c = SCENARIOS[name]
        d = decide(c, profile) if profile else None
        items.append({"name": name, "conditions": asdict(c), "mode": d.mode if d else None, "net": d.net if d else None})
    return {"scenarios": items, "timeline": TIMELINE}


@app.post("/api/crypto/roundtrip", response_model=s.RoundtripResponse)
def crypto_roundtrip(req: s.RoundtripRequest):
    plaintext = (req.sample_text * req.repeat).encode()
    if len(plaintext) > 50_000_000:
        raise HTTPException(422, "Payload is limited to 50 MB.")
    return {**secure_roundtrip(req.mode, plaintext), "data_origin": "MEASURED_LOCAL_CRYPTO"}


@app.get("/api/policy/config", response_model=s.PolicyConfigResponse)
def policy_config():
    return load_config()


@app.post("/api/policy/sensitivity-map", response_model=s.SensitivityMapResponse)
def sensitivity_map(req: s.SensitivityMapRequest):
    grid = generate_sensitivity_grid(_conditions(req.conditions), _profile(), req.lat_steps, req.bw_steps,
                                     _config(req.policy_override))
    return {**grid, "data_origin": "DETERMINISTIC_POLICY"}


@app.post("/api/crypto/handshake", response_model=s.HandshakeResponse)
def crypto_handshake(req: s.HandshakeRequest):
    return authenticated_handshake(req.mode, req.use_socket, req.tamper_target)


def _workload_payload(w: WorkloadProfile, profile: dict | None) -> dict:
    return {
        "id": w.id, "name": w.name, "description": w.description, "citation": w.citation,
        "conditions": asdict(w.conditions), "num_messages": w.num_messages,
        "rekey_interval_messages": w.rekey_interval_messages,
        "default_simulation": simulate_session(w, profile) if profile else None,
    }


@app.get("/api/workloads", response_model=s.WorkloadsResponse)
def get_workloads():
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = None
    return {"workloads": [_workload_payload(w, profile) for w in WORKLOADS]}


@app.post("/api/workloads/simulate-session", response_model=s.SessionSimResponse)
def simulate(req: s.SessionSimRequest):
    if req.workload_id:
        if req.workload_id not in WORKLOADS_BY_ID:
            raise HTTPException(404, f"Unknown workload: {req.workload_id}")
        base = WORKLOADS_BY_ID[req.workload_id]
    elif req.conditions:
        base = WorkloadProfile("custom", "Custom conditions", "", "", _conditions(req.conditions), 100, 50)
    else:
        raise HTTPException(422, "Provide workload_id or conditions.")
    if req.conditions:
        base = replace(base, conditions=_conditions(req.conditions))
    workload = replace(base, num_messages=req.num_messages or base.num_messages,
                       rekey_interval_messages=req.rekey_interval or base.rekey_interval_messages)
    return simulate_session(workload, _profile(), req.include_auth_handshake)


@app.get("/api/datasets/summary", response_model=s.DatasetsSummaryResponse)
def datasets_summary():
    return {"datasets": dataset_loader.datasets_summary(), "search_paths": dataset_loader.search_paths()}


@app.post("/api/datasets/replay", response_model=s.DatasetReplayResponse)
def datasets_replay(req: s.DatasetReplayRequest):
    profile = _profile()
    base = _conditions(req.conditions) if req.conditions else _REPLAY_BASE
    try:
        trace = dataset_loader.load_replay_trace(req.dataset_name, req.max_steps)
    except dataset_loader.DatasetUnavailableError as exc:
        raise HTTPException(404, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(422, f"Dataset does not match the expected schema: missing {exc}") from exc
    if not trace:
        raise HTTPException(422, "The dataset produced no usable samples.")
    for sample in trace:
        if sample["latency_budget_ms"] is None:  # packet captures carry no budget, so use the base one
            sample["latency_budget_ms"] = base.latency_budget_ms
    result = replay_trace(trace, base, profile, req.persistence_samples, req.net_margin, req.ewma_alpha)
    return {**result, "dataset_name": req.dataset_name, "data_origin": "EXTERNAL_DATASET_TRACE"}


def _report_args(req: s.ReportRequest) -> dict:
    if req.workload_id and req.workload_id not in WORKLOADS_BY_ID:
        raise HTTPException(404, f"Unknown workload: {req.workload_id}")
    return {
        "conditions": _conditions(req.conditions),
        "workload_id": req.workload_id,
        "handshake_result": req.handshake_result.model_dump() if req.handshake_result else None,
        "profile": _profile(),
    }


@app.post("/api/reports/pdf")
def report_pdf(req: s.ReportRequest):
    return Response(generate_pdf_report(**_report_args(req)), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="AdaptiveCrypt_Report.pdf"'})


@app.post("/api/reports/csv")
def report_csv(req: s.ReportRequest):
    return Response(generate_csv_report(**_report_args(req)), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="AdaptiveCrypt_Telemetry.csv"'})
