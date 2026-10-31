import clsx from "clsx";
import { useEffect, useState } from "react";
import { CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { Card, CHART, fmtInt, fmtKbps, fmtMs, Metric, MODE_META, ModeDot, ModeLabel, ModeLegend, MODES, Origin, Spinner, WarningBanner } from "../components/ui";
import { useExperiment } from "../context/ExperimentContext";
import type { DatasetReplayResponse, Mode, ReplayDataset, ReplayStep, SessionSimResponse } from "../types/api";

export default function WorkloadsDatasetsPage() {
  return (
    <>
      <WorkloadCards />
      <SessionSimulator />
      <ReplayPanel />
    </>
  );
}

function WorkloadCards() {
  const { workloads, activeWorkloadId, applyPreset } = useExperiment();
  return (
    <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-5">
      {workloads?.workloads.map((w) => (
        <section key={w.id} className={clsx("card flex flex-col", activeWorkloadId === w.id && "border-acid shadow-glow")}>
          <h2 className="text-xs">{w.name}</h2>
          <p className="mt-1.5 text-xs">{w.description}</p>
          <p className="mt-1.5 font-mono text-[11px] text-ink-muted">
            {w.conditions.sensitivity}, {w.conditions.lifetime_years} y, {w.conditions.latency_budget_ms} ms, {fmtKbps(w.conditions.bandwidth_kbps)}, {fmtInt(w.conditions.data_bytes)} B
          </p>
          <p className="mt-1.5 flex-1 text-[11px] italic text-ink-muted">{w.citation}</p>
          {w.default_simulation && (
            <div className="mt-2 text-xs text-ink">Recommended: <ModeLabel mode={w.default_simulation.recommended_mode} /></div>
          )}
          <button type="button" className="btn mt-2 py-1 text-xs" onClick={() => applyPreset(`workload:${w.id}`)}>
            Load profile
          </button>
        </section>
      ))}
    </div>
  );
}

function SessionSimulator() {
  const { activeWorkloadId, workloads, conditions } = useExperiment();
  const [messages, setMessages] = useState(100);
  const [rekey, setRekey] = useState(50);
  const [auth, setAuth] = useState(false);
  const [result, setResult] = useState<SessionSimResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const workload = workloads?.workloads.find((w) => w.id === activeWorkloadId);
    if (workload) {
      setMessages(workload.num_messages);
      setRekey(Math.max(10, workload.rekey_interval_messages));
    }
  }, [activeWorkloadId, workloads]);

  useEffect(() => {
    let current = true;
    const timer = window.setTimeout(async () => {
      try {
        const response = await api.simulateSession({
          workload_id: activeWorkloadId,
          conditions: activeWorkloadId ? undefined : conditions,
          num_messages: messages,
          rekey_interval: rekey,
          include_auth_handshake: auth,
        });
        if (current) {
          setResult(response);
          setError("");
        }
      } catch (e) {
        if (current) setError((e as Error).message);
      }
    }, 150);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [activeWorkloadId, conditions, messages, rekey, auth]);

  return (
    <Card
      title="Session simulator and amortization"
      subtitle={result ? `${result.workload_name}. Measured handshake costs and a simulated link.` : undefined}
    >
      <div className="grid gap-3 md:grid-cols-3">
        <div>
          <div className="flex justify-between">
            <label htmlFor="sim-n" className="field-label">Session messages (N)</label>
            <span className="font-mono text-xs text-acid">{messages}</span>
          </div>
          <input id="sim-n" type="range" min={1} max={500} value={messages} onChange={(e) => setMessages(Number(e.target.value))} />
        </div>
        <div>
          <div className="flex justify-between">
            <label htmlFor="sim-r" className="field-label">Re-key interval (R)</label>
            <span className="font-mono text-xs text-acid">{rekey}</span>
          </div>
          <input id="sim-r" type="range" min={10} max={250} value={rekey} onChange={(e) => setRekey(Number(e.target.value))} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="accent-[#C4F135]" checked={auth} onChange={(e) => setAuth(e.target.checked)} />
          Include authenticated handshake cost
        </label>
      </div>
      {error && <div className="mt-3"><WarningBanner>{error}</WarningBanner></div>}
      {result && (
        <div className="mt-3 grid gap-4 2xl:grid-cols-5">
          <div className="2xl:col-span-3">
            <div className="mb-1 text-xs text-ink-muted">Amortized overhead per message (ms/msg, log scale)</div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={result.amortization_curve} margin={{ top: 6, right: 12, left: 0, bottom: 14 }}>
                  <CartesianGrid stroke={CHART.grid} vertical={false} />
                  <XAxis dataKey="n" stroke={CHART.axis} tick={{ fontSize: 11 }} label={{ value: "Number of session messages (N)", position: "insideBottom", offset: -8, fill: CHART.axis, fontSize: 11 }} />
                  <YAxis
                    scale="log" allowDataOverflow stroke={CHART.axis} tick={{ fontSize: 11 }} tickFormatter={(v: number) => fmtMs(v)} width={52}
                    domain={[(min: number) => min * 0.6, (max: number) => max * 1.4]}
                  />
                  <Tooltip
                    contentStyle={CHART.tooltip} itemStyle={CHART.tooltipItem}
                    labelFormatter={(n) => `N = ${n}`}
                    formatter={(value: number, name) => [`${fmtMs(value)} ms/msg`, MODE_META[name as Mode].label]}
                  />
                  {MODES.map((mode) => (
                    // HYBRID and QUANTUM-SAFE often nearly coincide; the dash keeps both visible.
                    <Line key={mode} type="monotone" dataKey={mode} stroke={MODE_META[mode].color} strokeWidth={2} isAnimationActive={false}
                      strokeDasharray={mode === "HYBRID" ? "6 5" : undefined}
                      dot={(props: { key?: string; cx?: number; cy?: number }) => <ModeDot key={props.key} cx={props.cx} cy={props.cy} mode={mode} />} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <ModeLegend />
          </div>
          <div className="overflow-x-auto 2xl:col-span-2">
            <table className="data-table">
              <thead><tr><th>Mode</th><th>Handshakes</th><th>Total ms</th><th>ms/msg</th><th>Bytes/msg</th></tr></thead>
              <tbody>
                {MODES.map((mode) => {
                  const m = result.modes[mode];
                  return (
                    <tr key={mode}>
                      <td><ModeLabel mode={mode} /></td>
                      <td>{m.handshakes}</td>
                      <td>{fmtMs(m.total_overhead_ms)}</td>
                      <td>{fmtMs(m.amortized_overhead_ms_per_msg)}</td>
                      <td>{m.amortized_wire_bytes_per_msg.toFixed(1)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="mt-2"><Origin value={result.data_origin} /></div>
          </div>
        </div>
      )}
    </Card>
  );
}

function ReplayPanel() {
  const [dataset, setDataset] = useState<ReplayDataset>("wireshark_midterm53");
  const [persistence, setPersistence] = useState(3);
  const [alpha, setAlpha] = useState(0.3);
  const [result, setResult] = useState<DatasetReplayResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await api.replay({ dataset_name: dataset, persistence_samples: persistence, net_margin: 8, ewma_alpha: alpha }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Dataset telemetry replay" subtitle="External traces drive the simulated link. They are not AdaptiveCrypt benchmarks.">
      <div className="grid gap-3 md:grid-cols-3">
        <div>
          <label htmlFor="replay-set" className="field-label">Trace</label>
          <select id="replay-set" className="control" value={dataset} onChange={(e) => setDataset(e.target.value as ReplayDataset)}>
            <option value="wireshark_midterm53">Midterm_53_group.csv (Wireshark capture)</option>
            <option value="cloud_tasks">cloud.csv (task log)</option>
            <option value="vmcloud_trace">vmCloud_data.csv (VM telemetry)</option>
          </select>
        </div>
        <div>
          <div className="flex justify-between">
            <label htmlFor="replay-k" className="field-label">Hysteresis persistence (k)</label>
            <span className="font-mono text-xs text-acid">{persistence}</span>
          </div>
          <input id="replay-k" type="range" min={1} max={5} value={persistence} onChange={(e) => setPersistence(Number(e.target.value))} />
        </div>
        <div>
          <div className="flex justify-between">
            <label htmlFor="replay-a" className="field-label">EWMA alpha</label>
            <span className="font-mono text-xs text-acid">{alpha.toFixed(1)}</span>
          </div>
          <input id="replay-a" type="range" min={0.1} max={0.9} step={0.1} value={alpha} onChange={(e) => setAlpha(Number(e.target.value))} />
        </div>
      </div>
      <button type="button" className="btn btn-primary mt-3" onClick={() => void run()} disabled={busy}>
        {busy && <Spinner />} Replay Trace
      </button>
      {error && <div className="mt-3"><WarningBanner>{error}</WarningBanner></div>}
      {result && <ReplayResult result={result} />}
    </Card>
  );
}

function ReplayResult({ result }: { result: DatasetReplayResponse }) {
  return (
    <div className="mt-4 space-y-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Metric label="Reactive switches" value={result.reactive_switches} />
        <Metric label="Hysteresis switches" value={result.hysteresis_switches} />
        <Metric label="Flapping reduction" value={result.flapping_reduction_pct.toFixed(1)} unit="%" />
        <Metric label="Forecast error vs. last-value" value={`${fmtInt(result.forecast_mae_kbps)} / ${fmtInt(result.naive_mae_kbps)}`} unit="kbps" />
        <Metric label="Reactive budget violations" value={result.reactive_budget_violations} />
        <Metric label="Hysteresis budget violations" value={result.hysteresis_budget_violations} />
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={result.steps} margin={{ top: 6, right: 12, left: 8, bottom: 0 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="timestamp" stroke={CHART.axis} tick={{ fontSize: 11 }} minTickGap={40} />
            <YAxis stroke={CHART.axis} tick={{ fontSize: 11 }} tickFormatter={(v: number) => fmtKbps(v)} width={68} />
            <Tooltip
              contentStyle={CHART.tooltip} itemStyle={CHART.tooltipItem}
              formatter={(value: number, name) => [fmtKbps(value), name]}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="bandwidth_kbps" name="Observed bandwidth" stroke="#D1D5DB" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="ewma_bandwidth_kbps" name="EWMA + trend forecast" stroke="#C4F135" strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ModeStrip label="Reactive" steps={result.steps} field="reactive_mode" />
      <ModeStrip label="Hysteresis + EWMA" steps={result.steps} field="hysteresis_mode" />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-4">
          <ModeLegend />
          <span className="text-xs text-ink-muted">HYBRID segments are striped.</span>
        </div>
        <Origin value={result.data_origin} />
      </div>
    </div>
  );
}

function ModeStrip({ label, steps, field }: { label: string; steps: ReplayStep[]; field: "reactive_mode" | "hysteresis_mode" }) {
  return (
    <div>
      <div className="mb-1 text-xs text-ink-muted">{label} mode over time</div>
      <div className="flex h-4 overflow-hidden rounded" role="img" aria-label={`${label} mode for each sample`}>
        {steps.map((step, index) => (
          <div
            key={index}
            title={`t=${step.timestamp}: ${MODE_META[step[field]].label}`}
            className={clsx("min-w-0 flex-1", step[field] === "HYBRID" && "texture-hybrid")}
            style={{ backgroundColor: MODE_META[step[field]].color }}
          />
        ))}
      </div>
    </div>
  );
}
