import { Download, FileSpreadsheet, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { Card, CHART, fmtInt, fmtKbps, fmtMs, Metric, MODE_META, ModeLabel, ModeLegend, MODES, Origin, Spinner, WarningBanner } from "../components/ui";
import { useExperiment } from "../context/ExperimentContext";
import type { BenchmarkProfileResponse, DatasetsSummaryResponse, Mode } from "../types/api";

export default function BenchmarksReportsPage() {
  const { profile } = useExperiment();
  return (
    <>
      <BenchmarkControls />
      {profile && <HandshakeBench profile={profile} />}
      {profile && <SignatureBench profile={profile} />}
      <ReportStudio />
      <DatasetInventory />
    </>
  );
}

function BenchmarkControls() {
  const { profile, setProfile, refreshBenchmarkViews } = useExperiment();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      setProfile(await api.runBenchmarks(40, 5));
      await refreshBenchmarkViews();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Local hardware benchmark suite">
      {profile ? (
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="PQC backend" value={profile.pqc_backend} />
          <Metric label="Host" value={profile.host_metadata.platform} />
          <Metric label="CPU" value={profile.host_metadata.processor} />
          <Metric label="Measured" value={`${profile.host_metadata.timestamp} (Python ${profile.host_metadata.python_version})`} />
        </div>
      ) : (
        <p className="text-sm text-ink-muted">No results yet. Run the benchmark to measure this machine.</p>
      )}
      <button type="button" className="btn btn-primary mt-3" onClick={() => void run()} disabled={busy}>
        {busy ? <Spinner /> : <RefreshCw size={15} aria-hidden="true" />}
        {busy ? "Measuring, this can take several seconds" : "Re-Run Local Benchmarks"}
      </button>
      {error && <div className="mt-3"><WarningBanner>{error}</WarningBanner></div>}
    </Card>
  );
}

function HandshakeBench({ profile }: { profile: BenchmarkProfileResponse }) {
  const stats = [
    { name: "Median", key: "handshake_ms_median" },
    { name: "Mean", key: "handshake_ms_mean" },
    { name: "p95", key: "handshake_ms_p95" },
  ] as const;
  const data = stats.map((s) => ({
    name: s.name,
    ...Object.fromEntries(MODES.map((m) => [m, profile.modes[m][s.key]])),
  }));
  return (
    <Card title="Key establishment" subtitle={`${profile.modes.CLASSICAL.runs} runs per mode. AES-256-GCM: ${fmtInt(profile.aes.mb_per_s)} MB/s, ${profile.aes.ciphertext_overhead_bytes} B overhead per message.`}>
      <div className="grid gap-4 2xl:grid-cols-2">
        <div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} barGap={2} margin={{ top: 18, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <pattern id="hybrid-texture" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                    <rect width="5" height="5" fill={MODE_META.HYBRID.color} />
                    <rect width="1.5" height="5" fill="#0B0D0C" fillOpacity="0.5" />
                  </pattern>
                </defs>
                <CartesianGrid stroke={CHART.grid} vertical={false} />
                <XAxis dataKey="name" stroke={CHART.axis} tick={{ fontSize: 11 }} />
                <YAxis stroke={CHART.axis} tick={{ fontSize: 11 }} width={48} label={{ value: "ms", angle: -90, position: "insideLeft", fill: CHART.axis, fontSize: 11 }} />
                <Tooltip contentStyle={CHART.tooltip} itemStyle={CHART.tooltipItem} cursor={CHART.cursor}
                  formatter={(value: number, name) => [`${fmtMs(value)} ms`, MODE_META[name as Mode].label]} />
                {MODES.map((mode) => (
                  <Bar key={mode} dataKey={mode} fill={mode === "HYBRID" ? "url(#hybrid-texture)" : MODE_META[mode].color} radius={[4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false}>
                    <LabelList dataKey={mode} position="top" fill="#FFFFFF" fontSize={10} formatter={(v: number) => fmtMs(v)} />
                  </Bar>
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
          <ModeLegend />
        </div>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Mode</th><th>Median ms</th><th>Mean ms</th><th>p95 ms</th><th>Wire bytes</th><th>Auth median ms</th><th>Auth bytes</th></tr></thead>
            <tbody>
              {MODES.map((mode) => {
                const m = profile.modes[mode];
                const a = profile.auth_handshake[mode];
                return (
                  <tr key={mode}>
                    <td><ModeLabel mode={mode} /></td>
                    <td>{fmtMs(m.handshake_ms_median)}</td>
                    <td>{fmtMs(m.handshake_ms_mean)}</td>
                    <td>{fmtMs(m.handshake_ms_p95)}</td>
                    <td>{fmtInt(m.handshake_bytes)}</td>
                    <td>{fmtMs(a.handshake_ms_median)}</td>
                    <td>{fmtInt(a.handshake_bytes)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="mt-2"><Origin value={profile.data_origin} /></div>
        </div>
      </div>
    </Card>
  );
}

function SignatureBench({ profile }: { profile: BenchmarkProfileResponse }) {
  const ed = profile.signatures["Ed25519"];
  const dsa = profile.signatures["ML-DSA-65"];
  const data = (["keygen_ms", "sign_ms", "verify_ms"] as const).map((op) => ({
    name: op.replace("_ms", ""),
    Ed25519: ed[op].median,
    "ML-DSA-65": dsa[op].median,
  }));
  return (
    <Card title="Signatures: Ed25519 vs. ML-DSA-65" subtitle={`Median of ${ed.runs} runs.`}>
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} barGap={2} margin={{ top: 18, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="name" stroke={CHART.axis} tick={{ fontSize: 11 }} />
              <YAxis stroke={CHART.axis} tick={{ fontSize: 11 }} width={48} label={{ value: "ms", angle: -90, position: "insideLeft", fill: CHART.axis, fontSize: 11 }} />
              <Tooltip contentStyle={CHART.tooltip} itemStyle={CHART.tooltipItem} cursor={CHART.cursor} formatter={(value: number) => `${fmtMs(value)} ms`} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Ed25519" fill="#38BDF8" radius={[4, 4, 0, 0]} maxBarSize={40} isAnimationActive={false}>
                <LabelList dataKey="Ed25519" position="top" fill="#FFFFFF" fontSize={10} formatter={(v: number) => fmtMs(v)} />
              </Bar>
              <Bar dataKey="ML-DSA-65" fill="#C4F135" radius={[4, 4, 0, 0]} maxBarSize={40} isAnimationActive={false}>
                <LabelList dataKey="ML-DSA-65" position="top" fill="#FFFFFF" fontSize={10} formatter={(v: number) => fmtMs(v)} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Scheme</th><th>Public key</th><th>Signature</th><th>Keygen ms</th><th>Sign ms</th><th>Verify ms</th></tr></thead>
            <tbody>
              {Object.entries(profile.signatures).map(([name, sig]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{fmtInt(sig.public_key_bytes)} B</td>
                  <td>{fmtInt(sig.signature_bytes)} B</td>
                  <td>{fmtMs(sig.keygen_ms.median)}</td>
                  <td>{fmtMs(sig.sign_ms.median)}</td>
                  <td>{fmtMs(sig.verify_ms.median)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  );
}

function ReportStudio() {
  const { conditions, decision, displayedMode, activeWorkloadId, handshakeResult, reportRequest, workloads } = useExperiment();
  const [busy, setBusy] = useState<"pdf" | "csv" | null>(null);
  const [error, setError] = useState("");
  const workload = workloads?.workloads.find((w) => w.id === activeWorkloadId);

  const exportReport = async (kind: "pdf" | "csv") => {
    setBusy(kind);
    setError("");
    try {
      await (kind === "pdf" ? api.downloadPdf(reportRequest) : api.downloadCsv(reportRequest));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card title="Report generation studio" subtitle="Reports are generated from the current state below and the measured profile.">
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <Metric label="Conditions" value={`${conditions.sensitivity}, ${conditions.lifetime_years} y, ${conditions.latency_budget_ms} ms, ${fmtKbps(conditions.bandwidth_kbps)}`} />
        <Metric label="Mode" value={displayedMode ? <ModeLabel mode={displayedMode} /> : "None"} />
        <Metric label="Net score" value={decision ? `${decision.net >= 0 ? "+" : ""}${decision.net.toFixed(2)}` : "None"} />
        <Metric label="Workload" value={workload?.name ?? "None selected"} />
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        {handshakeResult
          ? `Includes your last ${MODE_META[handshakeResult.mode].label} handshake (${handshakeResult.success ? "verified" : "rejected"}).`
          : "No handshake run yet; the report will run a real HYBRID in-memory handshake."}
      </p>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <button type="button" className="btn btn-primary py-3" onClick={() => void exportReport("pdf")} disabled={busy !== null}>
          {busy === "pdf" ? <Spinner /> : <Download size={16} aria-hidden="true" />} Formatted PDF Technical Report
        </button>
        <button type="button" className="btn py-3" onClick={() => void exportReport("csv")} disabled={busy !== null}>
          {busy === "csv" ? <Spinner /> : <FileSpreadsheet size={16} aria-hidden="true" />} CSV Telemetry Dataset
        </button>
      </div>
      {error && <div className="mt-3"><WarningBanner>{error}</WarningBanner></div>}
    </Card>
  );
}

function DatasetInventory() {
  const [data, setData] = useState<DatasetsSummaryResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.datasets().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  const missing = data?.datasets.filter((d) => !d.available).length ?? 0;
  return (
    <Card title="Dataset provenance and inventory" subtitle="External data only. Never presented as AdaptiveCrypt's own cryptographic benchmarks.">
      {error && <WarningBanner>{error}</WarningBanner>}
      {!data && !error && <div className="flex items-center gap-2 text-sm text-ink-muted"><Spinner /> Inspecting archives</div>}
      {missing > 0 && (
        <div className="mb-3">
          <WarningBanner>
            {missing} of {data?.datasets.length} archives are not on this machine, so their data is unavailable. Place them in one of: {data?.search_paths.join("; ")}
          </WarningBanner>
        </div>
      )}
      {data && (
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>File</th><th>Archive</th><th>Status</th><th>Handling</th></tr></thead>
            <tbody>
              {data.datasets.map((d) => (
                <tr key={d.id}>
                  <td>{d.member}</td>
                  <td>{d.archive}</td>
                  <td className="whitespace-nowrap">{d.excluded ? "Excluded" : d.available ? "Loaded" : "Not found"}</td>
                  <td className="!font-sans">{d.note}{d.error && !d.error.includes("not found") ? ` ${d.error}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
