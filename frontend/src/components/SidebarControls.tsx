import { Download, FileSpreadsheet } from "lucide-react";
import { useState } from "react";
import clsx from "clsx";
import { api } from "../api/client";
import { useExperiment } from "../context/ExperimentContext";
import type { Sensitivity } from "../types/api";
import { fmtKbps, Spinner, WarningBanner } from "./ui";

const LEVELS: Sensitivity[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const SIZE_PRESETS = [
  { label: "512 B", value: 512 },
  { label: "10 KB", value: 10_000 },
  { label: "50 KB", value: 50_000 },
  { label: "1 MB", value: 1_000_000 },
];

export default function SidebarControls() {
  const {
    conditions, updateConditions, preset, applyPreset, scenarios, workloads, hysteresisEnabled, setHysteresisEnabled,
    reportRequest,
  } = useExperiment();
  const [busy, setBusy] = useState<"pdf" | "csv" | null>(null);
  const [error, setError] = useState("");

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
    <aside className="flex w-full shrink-0 flex-col gap-4 border-b border-acid-muted bg-charcoal/70 p-4 lg:h-full lg:w-72 lg:overflow-y-auto lg:border-b-0 lg:border-r">
      <div>
        <label htmlFor="preset" className="field-label">Scenario or workload</label>
        <select id="preset" className="control" value={preset} onChange={(e) => applyPreset(e.target.value)}>
          <option value="custom">Custom</option>
          <optgroup label="Round 1 scenarios">
            {scenarios?.scenarios.map((s) => <option key={s.name} value={`scenario:${s.name}`}>{s.name}</option>)}
          </optgroup>
          <optgroup label="HPC/QC workloads">
            {workloads?.workloads.map((w) => <option key={w.id} value={`workload:${w.id}`}>{w.name}</option>)}
          </optgroup>
        </select>
      </div>

      <fieldset>
        <legend className="field-label">Data sensitivity</legend>
        <div className="grid grid-cols-2 gap-1.5">
          {LEVELS.map((level) => (
            <button
              key={level}
              type="button"
              aria-pressed={conditions.sensitivity === level}
              onClick={() => updateConditions({ sensitivity: level })}
              className={clsx(
                "rounded-lg border px-2 py-1.5 text-xs font-medium transition-colors",
                conditions.sensitivity === level
                  ? "border-acid bg-acid text-obsidian"
                  : "border-acid-muted text-ink-body hover:bg-charcoal-hover",
              )}
            >
              {level}
            </button>
          ))}
        </div>
      </fieldset>

      <Slider
        id="lifetime" label="Confidentiality lifetime" min={0} max={30} step={0.5}
        value={conditions.lifetime_years} display={`${conditions.lifetime_years} years`}
        onChange={(v) => updateConditions({ lifetime_years: v })}
      />
      <Slider
        id="latency" label="Latency budget" min={1} max={500} step={1}
        value={conditions.latency_budget_ms} display={`${conditions.latency_budget_ms} ms`}
        onChange={(v) => updateConditions({ latency_budget_ms: v })}
      />
      <Slider
        id="bandwidth" label="Available bandwidth" min={100} max={100_000} step={100}
        value={conditions.bandwidth_kbps} display={fmtKbps(conditions.bandwidth_kbps)}
        onChange={(v) => updateConditions({ bandwidth_kbps: v })}
      />

      <div>
        <label htmlFor="payload" className="field-label">Payload size (bytes)</label>
        <input
          id="payload" type="number" min={0} max={100_000_000} className="control font-mono"
          value={conditions.data_bytes}
          onChange={(e) => updateConditions({ data_bytes: Math.max(0, Math.floor(Number(e.target.value) || 0)) })}
        />
        <div className="mt-1.5 flex flex-wrap gap-1">
          {SIZE_PRESETS.map((size) => (
            <button
              key={size.value}
              type="button"
              onClick={() => updateConditions({ data_bytes: size.value })}
              className={clsx(
                "rounded-full border px-2 py-0.5 text-xs",
                conditions.data_bytes === size.value ? "border-acid text-acid" : "border-white/15 text-ink-muted hover:text-ink",
              )}
            >
              {size.label}
            </button>
          ))}
        </div>
      </div>

      <label className="flex items-start gap-2 text-sm text-ink-body">
        <input
          type="checkbox" className="mt-0.5 accent-[#C4F135]" checked={hysteresisEnabled}
          onChange={(e) => setHysteresisEnabled(e.target.checked)}
        />
        <span>
          Hysteresis
          <span className="block text-xs text-ink-muted">Hold the mode until a change persists across evaluations.</span>
        </span>
      </label>

      <div className="mt-auto flex flex-col gap-2 border-t border-white/10 pt-4">
        <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => void exportReport("pdf")}>
          {busy === "pdf" ? <Spinner /> : <Download size={15} aria-hidden="true" />} Download PDF Report
        </button>
        <button type="button" className="btn" disabled={busy !== null} onClick={() => void exportReport("csv")}>
          {busy === "csv" ? <Spinner /> : <FileSpreadsheet size={15} aria-hidden="true" />} Export CSV Telemetry
        </button>
        {error && <WarningBanner>{error}</WarningBanner>}
      </div>
    </aside>
  );
}

function Slider({ id, label, min, max, step, value, display, onChange }: {
  id: string;
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  display: string;
  onChange: (value: number) => void;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="field-label">{label}</label>
        <span className="font-mono text-xs text-acid">{display}</span>
      </div>
      <input
        id={id} type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
