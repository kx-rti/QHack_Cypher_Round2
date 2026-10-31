import clsx from "clsx";
import { CheckCircle2, Pause, Play, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import ModeBadgeCard from "../components/ModeBadgeCard";
import { Card, CHART, fmtInt, fmtMs, Metric, MODE_META, ModeLabel, Origin, Spinner, WarningBanner } from "../components/ui";
import { useExperiment } from "../context/ExperimentContext";
import type { RoundtripResponse } from "../types/api";

const STEP_MS = 2600;

export default function CommandCenterPage() {
  return (
    <>
      <div className="grid gap-4 xl:grid-cols-2">
        <ModeBadgeCard />
        <WhyCard />
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <OverheadCard />
        <RoundtripCard />
      </div>
      <TimelineCard />
    </>
  );
}

function WhyCard() {
  const { decision, decisionError, history } = useExperiment();
  return (
    <Card title="Why this mode?">
      {decisionError && <WarningBanner>{decisionError}</WarningBanner>}
      {decision && (
        <>
          <ul className="list-disc space-y-1 pl-4 text-sm">
            {decision.reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
          {decision.warnings.length > 0 && (
            <div className="mt-3 space-y-2">
              {decision.warnings.map((warning) => <WarningBanner key={warning}>{warning}</WarningBanner>)}
            </div>
          )}
          <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-white/10 pt-3 text-xs">
            {decision.factor_contributions.map((f) => (
              <div key={f.factor} className="flex justify-between">
                <span className="capitalize text-ink-muted">{f.factor}</span>
                <span className="font-mono text-ink">{f.signed_contribution >= 0 ? "+" : ""}{f.signed_contribution.toFixed(1)}</span>
              </div>
            ))}
          </div>
          {history.length > 1 && (
            <p className="mt-3 text-xs text-ink-muted">
              Recent modes: {history.slice(0, 5).map((h) => MODE_META[h.mode].label).join(" ← ")}
            </p>
          )}
        </>
      )}
    </Card>
  );
}

function OverheadCard() {
  const { decision, conditions } = useExperiment();
  const rows = decision?.overhead_breakdown ?? [];
  const data = rows.map((r) => ({ ...r, name: MODE_META[r.mode].label }));
  const top = Math.max(conditions.latency_budget_ms, ...rows.map((r) => r.total_ms)) * 1.2 || 1;
  return (
    <Card
      title="Estimated security overhead"
      subtitle="Measured crypto time plus simulated transfer time. Dashed line: latency budget."
      className="xl:col-span-2"
    >
      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 18, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="name" stroke={CHART.axis} tick={{ fontSize: 11 }} />
            <YAxis stroke={CHART.axis} tick={{ fontSize: 11 }} domain={[0, top]} tickFormatter={(v: number) => fmtMs(v)} width={52} />
            <Tooltip
              contentStyle={CHART.tooltip} itemStyle={CHART.tooltipItem} cursor={CHART.cursor}
              formatter={(value: number) => [`${fmtMs(value)} ms`, "Total overhead"]}
            />
            <ReferenceLine y={conditions.latency_budget_ms} stroke="#F87171" strokeDasharray="4 4" label={{ value: `Budget ${conditions.latency_budget_ms} ms`, fill: "#D1D5DB", fontSize: 11, position: "insideTopRight" }} />
            <Bar dataKey="total_ms" radius={[4, 4, 0, 0]} maxBarSize={56} isAnimationActive={false}>
              {data.map((r) => <Cell key={r.mode} fill={MODE_META[r.mode].color} />)}
              <LabelList dataKey="total_ms" position="top" fill="#FFFFFF" fontSize={11} formatter={(v: number) => fmtMs(v)} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Mode</th><th>Handshake ms</th><th>Transfer ms</th><th>AES ms</th><th>Total ms</th><th>Wire bytes</th><th>Budget</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.mode}>
                <td><ModeLabel mode={r.mode} /></td>
                <td>{fmtMs(r.handshake_ms)}</td>
                <td>{fmtMs(r.wire_transfer_ms)}</td>
                <td>{fmtMs(r.aes_ms)}</td>
                <td>{fmtMs(r.total_ms)}</td>
                <td>{fmtInt(r.handshake_bytes)}</td>
                <td>
                  <span className={clsx("inline-flex items-center gap-1", r.within_budget ? "text-acid" : "text-cyber-coral")}>
                    {r.within_budget ? <CheckCircle2 size={13} aria-hidden="true" /> : <XCircle size={13} aria-hidden="true" />}
                    {r.within_budget ? "Within" : "Over"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function RoundtripCard() {
  const { displayedMode } = useExperiment();
  const [result, setResult] = useState<RoundtripResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    if (!displayedMode) return;
    setBusy(true);
    setError("");
    try {
      setResult(await api.roundtrip(displayedMode));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Live cryptographic execution" subtitle="Runs a real key establishment and AES-256-GCM encrypt and decrypt.">
      <button type="button" className="btn btn-primary w-full" disabled={busy || !displayedMode} onClick={() => void run()}>
        {busy && <Spinner />} Run Real Encryption in Selected Mode
      </button>
      {error && <div className="mt-3"><WarningBanner>{error}</WarningBanner></div>}
      {result && (
        <div className="mt-3 space-y-2">
          <div className={clsx("flex items-center gap-2 text-sm font-medium", result.correct ? "text-acid" : "text-cyber-coral")}>
            {result.correct ? <CheckCircle2 size={16} aria-hidden="true" /> : <XCircle size={16} aria-hidden="true" />}
            Decrypted correctly: {result.correct ? "TRUE" : "FALSE"}
          </div>
          <div className="text-xs text-ink-muted">Mode: {MODE_META[result.mode].label}</div>
          <div className="grid grid-cols-2 gap-2">
            <Metric label="Handshake" value={fmtMs(result.handshake_ms)} unit="ms" />
            <Metric label="Wire bytes" value={fmtInt(result.handshake_bytes)} unit="B" />
            <Metric label="Encrypt" value={fmtMs(result.encrypt_ms)} unit="ms" />
            <Metric label="Decrypt" value={fmtMs(result.decrypt_ms)} unit="ms" />
            <Metric label="Plaintext" value={fmtInt(result.plaintext_bytes)} unit="B" />
            <Metric label="Ciphertext" value={fmtInt(result.ciphertext_bytes)} unit="B" />
          </div>
          <Metric label="Ciphertext preview (first 32 bytes)" value={result.ciphertext_preview_hex} />
          <Origin value={result.data_origin} />
        </div>
      )}
    </Card>
  );
}

function TimelineCard() {
  const { scenarios, setConditions, applyPreset } = useExperiment();
  const [active, setActive] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const items = scenarios?.scenarios ?? [];

  const select = (index: number) => {
    setActive(index);
    applyPreset(`scenario:${items[index].name}`);
    setConditions(items[index].conditions);
  };

  useEffect(() => {
    if (!playing || items.length === 0) return;
    const timer = window.setTimeout(() => {
      const next = active === null ? 0 : active + 1;
      if (next >= items.length) setPlaying(false);
      else select(next);
    }, active === null ? 0 : STEP_MS);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, active, items.length]);

  const toggle = () => {
    if (!playing && active === items.length - 1) setActive(null);
    setPlaying(!playing);
  };

  return (
    <Card title="Adaptive switching timeline" subtitle="Conditions change over time; the engine recomputes the mode at each step.">
      <button type="button" className="btn mb-3" onClick={toggle} disabled={items.length === 0}>
        {playing ? <Pause size={15} aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}
        {playing ? "Pause" : "Play Adaptive Timeline"}
      </button>
      <ol className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {items.map((item, index) => (
          <li key={item.name}>
            <button
              type="button"
              onClick={() => { setPlaying(false); select(index); }}
              aria-current={active === index ? "step" : undefined}
              className={clsx(
                "h-full w-full rounded-xl border p-3 text-left transition-colors hover:bg-charcoal-hover",
                active === index ? "border-acid bg-charcoal-hover shadow-glow" : "border-white/10",
              )}
            >
              <div className="text-sm font-medium text-ink">{item.name}</div>
              <div className="mt-1 font-mono text-xs text-ink-muted">
                {item.conditions.sensitivity}, {item.conditions.lifetime_years} y, {item.conditions.latency_budget_ms} ms, {fmtInt(item.conditions.bandwidth_kbps)} kbps
              </div>
              <div className="mt-2 text-xs text-ink">
                {item.mode ? <ModeLabel mode={item.mode} /> : "No benchmark profile"}
                {item.net !== null && <span className="ml-2 font-mono text-ink-muted">net {item.net >= 0 ? "+" : ""}{item.net.toFixed(1)}</span>}
              </div>
            </button>
          </li>
        ))}
      </ol>
    </Card>
  );
}
