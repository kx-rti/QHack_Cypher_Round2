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

// 1. Check runtime localStorage override (so user can configure without rebuilding)
// 2. Check Vite build-time environment variable
// 3. Default to empty string (which uses relative paths for Vercel rewrites / Vite dev proxy)
function getBaseUrl(): string {
  try {
    const saved = localStorage.getItem("ADAPTIVECRYPT_BACKEND_URL");
    if (saved && saved.trim()) return saved.trim().replace(/\/+$/, "");
  } catch {
    // ignore
  }
  return (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");
}

function toUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const base = getBaseUrl();
  return `${base}${path.startsWith("/") ? "" : "/"}${path}`;
}

async function failure(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    if (response.status >= 500) message = "The backend is not reachable. Verify your backend server is running.";
  }
  return new ApiError(response.status, message);
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  const url = toUrl(path);
  try {
    response = await fetch(url, init);
  } catch (err) {
    const attemptedUrl = url.startsWith("http") ? url : `${window.location.origin}${url}`;
    throw new ApiError(0, `Cannot reach backend at ${attemptedUrl}. Check Render deployment or set Backend URL.`);
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
  getBaseUrl,
  setBaseUrl: (url: string) => {
    localStorage.setItem("ADAPTIVECRYPT_BACKEND_URL", url.trim().replace(/\/+$/, ""));
  },
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
