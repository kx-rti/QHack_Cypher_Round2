// Mirrors api/schemas.py one to one.
export type Mode = "CLASSICAL" | "QUANTUM_SAFE" | "HYBRID";
export type Sensitivity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type TamperTarget = "none" | "server_pk" | "ciphertext" | "signature";
export type ReplayDataset = "wireshark_midterm53" | "cloud_tasks" | "vmcloud_trace";

export interface Conditions {
  sensitivity: Sensitivity;
  lifetime_years: number;
  latency_budget_ms: number;
  bandwidth_kbps: number;
  data_bytes: number;
}

export interface PolicyOverride {
  weights?: { sens?: number; life?: number; lat?: number; bw?: number };
  thresholds?: { t_high?: number; t_low?: number };
  safety_floor?: { min_sensitivity?: Sensitivity[]; min_lifetime_years?: number };
}

export interface HealthResponse {
  status: string;
  pqc_backend: string;
  pqc_fallback: boolean;
  host_os: string;
  host_cpu: string;
  python_version: string;
  benchmarks_loaded: boolean;
}

export interface ModeBenchmark {
  handshake_ms_median: number;
  handshake_ms_mean: number;
  handshake_ms_p95: number;
  handshake_bytes: number;
  runs: number;
}

export interface AesBenchmark {
  mb_per_s: number;
  payload_bytes: number;
  ciphertext_overhead_bytes: number;
  runs: number;
}

export interface TimingStats {
  median: number;
  mean: number;
  p95: number;
}

export interface SignatureBenchmark {
  public_key_bytes: number;
  signature_bytes: number;
  keygen_ms: TimingStats;
  sign_ms: TimingStats;
  verify_ms: TimingStats;
  runs: number;
}

export interface HostMetadata {
  platform: string;
  processor: string;
  python_version: string;
  timestamp: string;
}

export interface BenchmarkProfileResponse {
  pqc_backend: string;
  host_metadata: HostMetadata;
  modes: Record<string, ModeBenchmark>;
  aes: AesBenchmark;
  signatures: Record<string, SignatureBenchmark>;
  auth_handshake: Record<string, ModeBenchmark>;
  data_origin: string;
}

export interface OverheadRow {
  mode: Mode;
  handshake_ms: number;
  wire_transfer_ms: number;
  aes_ms: number;
  total_ms: number;
  handshake_bytes: number;
  within_budget: boolean;
}

export interface FactorContribution {
  factor: string;
  raw_value: string | number;
  normalized_score: number;
  weight: number;
  signed_contribution: number;
  direction: string;
  summary_text: string;
}

export interface DecisionResponse {
  mode: Mode;
  need: number;
  pressure: number;
  net: number;
  reasons: string[];
  warnings: string[];
  estimates_ms: Record<string, number>;
  within_budget: Record<string, boolean>;
  overhead_breakdown: OverheadRow[];
  factor_contributions: FactorContribution[];
  contributions_sum: number;
  floor_applied: boolean;
  downgraded: boolean;
  data_origin: string;
}

export interface ScenarioItem {
  name: string;
  conditions: Conditions;
  mode: Mode | null;
  net: number | null;
}

export interface ScenariosResponse {
  scenarios: ScenarioItem[];
  timeline: string[];
}

export interface RoundtripResponse {
  mode: Mode;
  handshake_ms: number;
  handshake_bytes: number;
  encrypt_ms: number;
  decrypt_ms: number;
  plaintext_bytes: number;
  ciphertext_bytes: number;
  overhead_bytes: number;
  ciphertext_preview_hex: string;
  correct: boolean;
  pqc_backend: string;
  data_origin: string;
}

export interface PolicyConfigResponse {
  sensitivity_levels: Record<string, number>;
  weights: { sens: number; life: number; lat: number; bw: number };
  thresholds: { t_high: number; t_low: number };
  safety_floor: { min_sensitivity: Sensitivity[]; min_lifetime_years: number };
  hysteresis: { persistence_samples: number; net_margin: number; ewma_alpha: number };
}

export interface SensitivityCell {
  lat_ms: number;
  bw_kbps: number;
  mode: Mode;
  mode_code: number;
  net: number;
  downgraded: boolean;
}

export interface SensitivityMapResponse {
  lat_values: number[];
  bw_values: number[];
  cells: SensitivityCell[][];
  data_origin: string;
}

export interface WireItem {
  component: string;
  field: string;
  bytes: number;
}

export interface HandshakeStep {
  actor: string;
  action: string;
  status: string;
  wire_bytes: number;
  detail: string;
}

export interface HandshakeResponse {
  success: boolean;
  mode: Mode;
  transport: string;
  elapsed_ms: number;
  total_wire_bytes: number;
  wire_breakdown: WireItem[];
  transcript_sha256: string;
  client_key_fp: string;
  server_key_fp: string;
  keys_match: boolean;
  steps_log: HandshakeStep[];
  tamper_target: TamperTarget;
  tamper_applied: boolean;
  error_message: string;
  pqc_backend: string;
  data_origin: string;
}

export interface SessionModeMetrics {
  handshakes: number;
  total_overhead_ms: number;
  amortized_overhead_ms_per_msg: number;
  total_crypto_wire_bytes: number;
  amortized_wire_bytes_per_msg: number;
}

export interface CurvePoint {
  n: number;
  CLASSICAL: number;
  QUANTUM_SAFE: number;
  HYBRID: number;
}

export interface SessionSimResponse {
  workload_id: string;
  workload_name: string;
  num_messages: number;
  rekey_interval_messages: number;
  include_authenticated_handshake: boolean;
  modes: Record<Mode, SessionModeMetrics>;
  amortization_curve: CurvePoint[];
  recommended_mode: Mode;
  data_origin: string;
}

export interface WorkloadItem {
  id: string;
  name: string;
  description: string;
  citation: string;
  conditions: Conditions;
  num_messages: number;
  rekey_interval_messages: number;
  default_simulation: SessionSimResponse | null;
}

export interface WorkloadsResponse {
  workloads: WorkloadItem[];
}

export interface SessionSimRequest {
  workload_id?: string;
  conditions?: Conditions;
  num_messages?: number;
  rekey_interval?: number;
  include_auth_handshake: boolean;
}

export interface DatasetEntry {
  id: string;
  archive: string;
  member: string;
  note: string;
  data_origin: string;
  available: boolean;
  excluded: boolean;
  error: string;
  summary: Record<string, unknown>;
}

export interface DatasetsSummaryResponse {
  datasets: DatasetEntry[];
  search_paths: string[];
}

export interface DatasetReplayRequest {
  dataset_name: ReplayDataset;
  persistence_samples: number;
  net_margin: number;
  ewma_alpha: number;
  conditions?: Conditions;
}

export interface ReplayStep {
  timestamp: number;
  bandwidth_kbps: number;
  ewma_bandwidth_kbps: number;
  latency_budget_ms: number;
  reactive_mode: Mode;
  hysteresis_mode: Mode;
}

export interface DatasetReplayResponse {
  dataset_name: string;
  steps: ReplayStep[];
  reactive_switches: number;
  hysteresis_switches: number;
  flapping_reduction_pct: number;
  reactive_budget_violations: number;
  hysteresis_budget_violations: number;
  forecast_mae_kbps: number;
  naive_mae_kbps: number;
  data_origin: string;
}

export interface ReportRequest {
  conditions: Conditions;
  workload_id?: string;
  handshake_result?: HandshakeResponse;
}
