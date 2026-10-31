"""Pydantic v2 request and response models. frontend/src/types/api.ts mirrors this file."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["CLASSICAL", "QUANTUM_SAFE", "HYBRID"]
Sensitivity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
TamperTarget = Literal["none", "server_pk", "ciphertext", "signature"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConditionsModel(StrictModel):
    sensitivity: Sensitivity
    lifetime_years: float = Field(ge=0, le=100)
    latency_budget_ms: float = Field(gt=0, le=100_000)
    bandwidth_kbps: float = Field(gt=0, le=100_000_000)
    data_bytes: int = Field(default=10_000, ge=0, le=10_000_000_000)


class WeightsOverride(StrictModel):
    sens: float | None = Field(default=None, ge=0, le=1)
    life: float | None = Field(default=None, ge=0, le=1)
    lat: float | None = Field(default=None, ge=0, le=1)
    bw: float | None = Field(default=None, ge=0, le=1)


class ThresholdsOverride(StrictModel):
    t_high: float | None = Field(default=None, ge=-100, le=100)
    t_low: float | None = Field(default=None, ge=-100, le=100)


class SafetyFloorOverride(StrictModel):
    min_sensitivity: list[Sensitivity] | None = None
    min_lifetime_years: float | None = Field(default=None, ge=0, le=100)


class PolicyOverride(StrictModel):
    weights: WeightsOverride | None = None
    thresholds: ThresholdsOverride | None = None
    safety_floor: SafetyFloorOverride | None = None


class HealthResponse(StrictModel):
    status: str
    pqc_backend: str
    pqc_fallback: bool
    host_os: str
    host_cpu: str
    python_version: str
    benchmarks_loaded: bool


class ModeBenchmark(StrictModel):
    handshake_ms_median: float
    handshake_ms_mean: float
    handshake_ms_p95: float
    handshake_bytes: int
    runs: int


class AesBenchmark(StrictModel):
    mb_per_s: float
    payload_bytes: int
    ciphertext_overhead_bytes: int
    runs: int


class TimingStats(StrictModel):
    median: float
    mean: float
    p95: float


class SignatureBenchmark(StrictModel):
    public_key_bytes: int
    signature_bytes: int
    keygen_ms: TimingStats
    sign_ms: TimingStats
    verify_ms: TimingStats
    runs: int


class HostMetadata(StrictModel):
    platform: str
    processor: str
    python_version: str
    timestamp: str


class BenchmarkProfileResponse(StrictModel):
    pqc_backend: str
    host_metadata: HostMetadata
    modes: dict[str, ModeBenchmark]
    aes: AesBenchmark
    signatures: dict[str, SignatureBenchmark]
    auth_handshake: dict[str, ModeBenchmark]
    data_origin: str


class RunBenchmarkRequest(StrictModel):
    runs: int = Field(default=40, ge=5, le=500)
    warmup: int = Field(default=5, ge=0, le=50)


class DecisionRequest(StrictModel):
    conditions: ConditionsModel
    policy_override: PolicyOverride | None = None


class OverheadRow(StrictModel):
    mode: str
    handshake_ms: float
    wire_transfer_ms: float
    aes_ms: float
    total_ms: float
    handshake_bytes: int
    within_budget: bool


class FactorContribution(StrictModel):
    factor: str
    raw_value: str | float
    normalized_score: float
    weight: float
    signed_contribution: float
    direction: str
    summary_text: str


class DecisionResponse(StrictModel):
    mode: Mode
    need: float
    pressure: float
    net: float
    reasons: list[str]
    warnings: list[str]
    estimates_ms: dict[str, float]
    within_budget: dict[str, bool]
    overhead_breakdown: list[OverheadRow]
    factor_contributions: list[FactorContribution]
    contributions_sum: float
    floor_applied: bool
    downgraded: bool
    data_origin: str


class ScenarioItem(StrictModel):
    name: str
    conditions: ConditionsModel
    mode: Mode | None
    net: float | None


class ScenariosResponse(StrictModel):
    scenarios: list[ScenarioItem]
    timeline: list[str]


class RoundtripRequest(StrictModel):
    mode: Mode
    sample_text: str = Field(default="sample HPC-QC payload ", max_length=10_000)
    repeat: int = Field(default=100, ge=1, le=100_000)


class RoundtripResponse(StrictModel):
    mode: Mode
    handshake_ms: float
    handshake_bytes: int
    encrypt_ms: float
    decrypt_ms: float
    plaintext_bytes: int
    ciphertext_bytes: int
    overhead_bytes: int
    ciphertext_preview_hex: str
    correct: bool
    pqc_backend: str
    data_origin: str


class PolicyConfigResponse(StrictModel):
    sensitivity_levels: dict[str, float]
    weights: dict[str, float]
    thresholds: dict[str, float]
    safety_floor: dict[str, list[str] | float]
    hysteresis: dict[str, float]


class SensitivityMapRequest(StrictModel):
    conditions: ConditionsModel
    lat_steps: int = Field(default=25, ge=2, le=60)
    bw_steps: int = Field(default=25, ge=2, le=60)
    policy_override: PolicyOverride | None = None


class SensitivityCell(StrictModel):
    lat_ms: float
    bw_kbps: float
    mode: Mode
    mode_code: int
    net: float
    downgraded: bool


class SensitivityMapResponse(StrictModel):
    lat_values: list[float]
    bw_values: list[float]
    cells: list[list[SensitivityCell]]
    data_origin: str


class HandshakeRequest(StrictModel):
    mode: Mode
    use_socket: bool = True
    tamper_target: TamperTarget = "none"


class WireItem(StrictModel):
    component: str
    field: str
    bytes: int


class HandshakeStep(StrictModel):
    actor: str
    action: str
    status: str
    wire_bytes: int
    detail: str


class HandshakeResponse(StrictModel):
    success: bool
    mode: Mode
    transport: str
    elapsed_ms: float
    total_wire_bytes: int
    wire_breakdown: list[WireItem]
    transcript_sha256: str
    client_key_fp: str
    server_key_fp: str
    keys_match: bool
    steps_log: list[HandshakeStep]
    tamper_target: TamperTarget
    tamper_applied: bool
    error_message: str
    pqc_backend: str
    data_origin: str


class SessionModeMetrics(StrictModel):
    handshakes: int
    total_overhead_ms: float
    amortized_overhead_ms_per_msg: float
    total_crypto_wire_bytes: int
    amortized_wire_bytes_per_msg: float


class CurvePoint(StrictModel):
    n: int
    CLASSICAL: float
    QUANTUM_SAFE: float
    HYBRID: float


class SessionSimResponse(StrictModel):
    workload_id: str
    workload_name: str
    num_messages: int
    rekey_interval_messages: int
    include_authenticated_handshake: bool
    modes: dict[str, SessionModeMetrics]
    amortization_curve: list[CurvePoint]
    recommended_mode: Mode
    data_origin: str


class WorkloadItem(StrictModel):
    id: str
    name: str
    description: str
    citation: str
    conditions: ConditionsModel
    num_messages: int
    rekey_interval_messages: int
    default_simulation: SessionSimResponse | None


class WorkloadsResponse(StrictModel):
    workloads: list[WorkloadItem]


class SessionSimRequest(StrictModel):
    workload_id: str | None = None
    conditions: ConditionsModel | None = None
    num_messages: int | None = Field(default=None, ge=1, le=1_000_000)
    rekey_interval: int | None = Field(default=None, ge=1, le=1_000_000)
    include_auth_handshake: bool = False


class DatasetEntry(StrictModel):
    id: str
    archive: str
    member: str
    note: str
    data_origin: str
    available: bool
    excluded: bool
    error: str
    summary: dict


class DatasetsSummaryResponse(StrictModel):
    datasets: list[DatasetEntry]
    search_paths: list[str]


class DatasetReplayRequest(StrictModel):
    dataset_name: Literal["wireshark_midterm53", "cloud_tasks", "vmcloud_trace"]
    persistence_samples: int = Field(default=3, ge=1, le=10)
    net_margin: float = Field(default=8.0, ge=0, le=100)
    ewma_alpha: float = Field(default=0.3, gt=0, lt=1)
    conditions: ConditionsModel | None = None
    max_steps: int = Field(default=300, ge=10, le=2000)


class ReplayStep(StrictModel):
    timestamp: float
    bandwidth_kbps: float
    ewma_bandwidth_kbps: float
    latency_budget_ms: float
    reactive_mode: Mode
    hysteresis_mode: Mode


class DatasetReplayResponse(StrictModel):
    dataset_name: str
    steps: list[ReplayStep]
    reactive_switches: int
    hysteresis_switches: int
    flapping_reduction_pct: float
    reactive_budget_violations: int
    hysteresis_budget_violations: int
    forecast_mae_kbps: float
    naive_mae_kbps: float
    data_origin: str


class ReportRequest(StrictModel):
    conditions: ConditionsModel
    workload_id: str | None = None
    handshake_result: HandshakeResponse | None = None
