import type {
  BenchmarkProfileResponse,
  Conditions,
  DatasetReplayRequest,
  DatasetReplayResponse,
  DatasetsSummaryResponse,
  DecisionResponse,
  HandshakeResponse,
  HealthResponse,
  Mode,
  PolicyConfigResponse,
  PolicyOverride,
  ReportRequest,
  RoundtripResponse,
  ScenariosResponse,
  SensitivityMapResponse,
  SessionSimRequest,
  SessionSimResponse,
  TamperTarget,
  WorkloadsResponse,
} from "../types/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function failure(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    // Not JSON: usually the dev proxy reporting that the backend is down.
    if (response.status >= 500) message = "The backend is not reachable. Start it with uvicorn on port 8000.";
  }
  return new ApiError(response.status, message);
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, "The backend is not reachable. Start it with uvicorn on port 8000.");
  }
  if (!response.ok) throw await failure(response);
  return response;
}

async function get<T>(path: string): Promise<T> {
  return (await send(path)).json();
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await send(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  return response.json();
}

async function download(path: string, body: unknown, filename: string): Promise<void> {
  const response = await send(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  health: () => get<HealthResponse>("/api/health"),
  benchmarks: () => get<BenchmarkProfileResponse>("/api/benchmarks"),
  runBenchmarks: (runs: number, warmup: number) =>
    post<BenchmarkProfileResponse>("/api/benchmarks/run", { runs, warmup }),
  decide: (conditions: Conditions, policy_override?: PolicyOverride, signal?: AbortSignal) =>
    post<DecisionResponse>("/api/decide", { conditions, policy_override }, signal),
  scenarios: () => get<ScenariosResponse>("/api/scenarios"),
  roundtrip: (mode: Mode) => post<RoundtripResponse>("/api/crypto/roundtrip", { mode }),
  policyConfig: () => get<PolicyConfigResponse>("/api/policy/config"),
  sensitivityMap: (conditions: Conditions, policy_override: PolicyOverride | undefined, signal?: AbortSignal) =>
    post<SensitivityMapResponse>(
      "/api/policy/sensitivity-map",
      { conditions, lat_steps: 25, bw_steps: 25, policy_override },
      signal,
    ),
  handshake: (mode: Mode, use_socket: boolean, tamper_target: TamperTarget) =>
    post<HandshakeResponse>("/api/crypto/handshake", { mode, use_socket, tamper_target }),
  workloads: () => get<WorkloadsResponse>("/api/workloads"),
  simulateSession: (request: SessionSimRequest) =>
    post<SessionSimResponse>("/api/workloads/simulate-session", request),
  datasets: () => get<DatasetsSummaryResponse>("/api/datasets/summary"),
  replay: (request: DatasetReplayRequest) => post<DatasetReplayResponse>("/api/datasets/replay", request),
  downloadPdf: (request: ReportRequest) => download("/api/reports/pdf", request, "AdaptiveCrypt_Report.pdf"),
  downloadCsv: (request: ReportRequest) => download("/api/reports/csv", request, "AdaptiveCrypt_Telemetry.csv"),
};
