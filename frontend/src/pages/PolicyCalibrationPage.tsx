import clsx from "clsx";
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { Card, CHART, fmtKbps, fmtMs, MODE_META, ModeLabel, ModeLegend, Origin, WarningBanner } from "../components/ui";
import { useExperiment } from "../context/ExperimentContext";
import type { SensitivityCell, SensitivityMapResponse } from "../types/api";

interface Tunable {
  w_sens: number;
  w_life: number;
  w_lat: number;
  w_bw: number;
  t_high: number;
  t_low: number;
}

const SLIDERS: { key: keyof Tunable; label: string; min: number; max: number; step: number }[] = [
  { key: "w_sens", label: "w_sens (sensitivity)", min: 0, max: 1, step: 0.05 },
  { key: "w_life", label: "w_life (lifetime)", min: 0, max: 1, step: 0.05 },
  { key: "w_lat", label: "w_lat (latency)", min: 0, max: 1, step: 0.05 },
  { key: "w_bw", label: "w_bw (bandwidth)", min: 0, max: 1, step: 0.05 },
  { key: "t_high", label: "T_HIGH", min: 0, max: 60, step: 1 },
  { key: "t_low", label: "T_LOW", min: -60, max: 0, step: 1 },
];

export default function PolicyCalibrationPage() {
  const { config, setPolicyOverride, decision, conditions, policyOverride } = useExperiment();
  const defaults = useMemo<Tunable | null>(
    () =>
      config && {
        w_sens: config.weights.sens,
        w_life: config.weights.life,
        w_lat: config.weights.lat,
        w_bw: config.weights.bw,
        t_high: config.thresholds.t_high,
        t_low: config.thresholds.t_low,
      },
    [config],
  );
  const [values, setValues] = useState<Tunable | null>(null);
  const current = values ?? defaults;

  const change = (key: keyof Tunable, value: number) => {
    if (!current) return;
    const next = { ...current, [key]: value };
    setValues(next);
    setPolicyOverride({
      weights: { sens: next.w_sens, life: next.w_life, lat: next.w_lat, bw: next.w_bw },
      thresholds: { t_high: next.t_high, t_low: next.t_low },
    });
  };

  const reset = () => {
    setValues(null);
    setPolicyOverride(undefined);
  };

  const data = (decision?.factor_contributions ?? []).map((f) => ({
    name: f.factor.charAt(0).toUpperCase() + f.factor.slice(1),
    value: f.signed_contribution,
    summary: f.summary_text,
  }));
  const reach = Math.ceil((Math.max(10, ...data.map((d) => Math.abs(d.value))) * 1.2) / 10) * 10;

  return (
    <>
      <div className="grid gap-4 xl:grid-cols-5">
        <Card title="Policy calibration" subtitle="Starts from decision_engine/policy.yaml. Changes apply to this session only." className="xl:col-span-2">
          <div className="space-y-3">
            {current && SLIDERS.map((s) => (
              <div key={s.key}>
                <div className="flex justify-between">
                  <label htmlFor={s.key} className="field-label">{s.label}</label>
                  <span className="font-mono text-xs text-acid">{current[s.key].toFixed(s.step < 1 ? 2 : 0)}</span>
                </div>
                <input
                  id={s.key} type="range" min={s.min} max={s.max} step={s.step} value={current[s.key]}
                  onChange={(e) => change(s.key, Number(e.target.value))}
                />
              </div>
            ))}
          </div>
          <button type="button" className="btn mt-4 w-full" onClick={reset} disabled={!policyOverride}>
            Reset to Canonical Defaults
          </button>
        </Card>
        <Card title="Signed factor contributions" subtitle="Positive bars push toward post-quantum modes, negative bars toward classical." className="xl:col-span-3">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" margin={{ left: 16, right: 36, top: 4, bottom: 4 }}>
                <CartesianGrid stroke={CHART.grid} horizontal={false} />
                <XAxis type="number" domain={[-reach, reach]} ticks={[-reach, -reach / 2, 0, reach / 2, reach]} stroke={CHART.axis} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" stroke={CHART.axis} tick={{ fontSize: 12 }} width={78} />
                <Tooltip
                  contentStyle={CHART.tooltip} itemStyle={CHART.tooltipItem} cursor={CHART.cursor}
                  formatter={(value: number, _name, item) => [value.toFixed(2), item.payload.summary]}
                />
                <ReferenceLine x={0} stroke={CHART.axis} />
                <Bar dataKey="value" radius={4} isAnimationActive={false} maxBarSize={26}>
                  {data.map((d) => <Cell key={d.name} fill={d.value >= 0 ? "#C4F135" : "#38BDF8"} />)}
                  <LabelList dataKey="value" position="right" fill="#FFFFFF" fontSize={11} formatter={(v: number) => (v >= 0 ? "+" : "") + v.toFixed(1)} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {decision && (
            <p className="mt-2 font-mono text-xs text-ink-body">
              Sum of contributions {decision.contributions_sum >= 0 ? "+" : ""}{decision.contributions_sum.toFixed(2)} = net {decision.net >= 0 ? "+" : ""}{decision.net.toFixed(2)}
            </p>
          )}
        </Card>
      </div>
      <DecisionMap sensitivity={conditions.sensitivity} />
    </>
  );
}

function DecisionMap({ sensitivity }: { sensitivity: string }) {
  const { conditions, policyOverride } = useExperiment();
  const [map, setMap] = useState<SensitivityMapResponse | null>(null);
  const [error, setError] = useState("");
  const [hover, setHover] = useState<SensitivityCell | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        setMap(await api.sensitivityMap(conditions, policyOverride, controller.signal));
        setError("");
      } catch (e) {
        if ((e as Error).name !== "AbortError") setError((e as Error).message);
      }
    }, 150);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [conditions, policyOverride]);

  // Positions on the log axes used by the backend sweep: 1-500 ms and 100-100000 kbps.
  const x = (Math.log(Math.min(100_000, Math.max(100, conditions.bandwidth_kbps)) / 100) / Math.log(1000)) * 100;
  const y = (Math.log(Math.min(500, Math.max(1, conditions.latency_budget_ms))) / Math.log(500)) * 100;
  const size = map?.bw_values.length ?? 1;

  return (
    <Card
      title="Latency vs. bandwidth decision map"
      subtitle={`Selected mode at each operating point, for ${sensitivity} sensitivity and ${conditions.lifetime_years}-year lifetime. Both axes are log scale.`}
    >
      {error && <WarningBanner>{error}</WarningBanner>}
      {map && (
        <div className="flex flex-col gap-4 lg:flex-row">
          <div className="min-w-0 flex-1">
            <div className="flex">
              <div className="flex w-14 shrink-0 flex-col justify-between pr-2 text-right font-mono text-[10px] text-ink-muted">
                <span>500 ms</span><span>22 ms</span><span>1 ms</span>
              </div>
              <div className="relative flex-1" onMouseLeave={() => setHover(null)}>
                <div className="grid gap-px" style={{ gridTemplateColumns: `repeat(${size}, minmax(0, 1fr))` }}>
                  {[...map.cells].reverse().flatMap((row) =>
                    row.map((cell) => (
                      <div
                        key={`${cell.lat_ms}-${cell.bw_kbps}`}
                        onMouseEnter={() => setHover(cell)}
                        className={clsx("aspect-[5/2] rounded-[1px]", cell.downgraded && "hatched", cell.mode === "HYBRID" && "texture-hybrid")}
                        style={{ backgroundColor: MODE_META[cell.mode].color, opacity: hover === cell ? 1 : 0.82 }}
                      />
                    )),
                  )}
                </div>
                <div
                  className="pulse-crosshair pointer-events-none absolute h-4 w-4 rounded-full border-2 border-white bg-obsidian/40"
                  style={{ left: `${x}%`, bottom: `${y}%`, transform: "translate(-50%, 50%)" }}
                  aria-label="Current operating point"
                />
              </div>
            </div>
            <div className="ml-14 mt-1 flex justify-between font-mono text-[10px] text-ink-muted">
              <span>100 kbps</span><span>3.2 Mbps</span><span>100 Mbps</span>
            </div>
          </div>
          <div className="w-full shrink-0 space-y-3 lg:w-56">
            <ModeLegend />
            <div className="flex items-center gap-2 text-xs text-ink-body">
              <span className="texture-hybrid inline-block h-3 w-5 rounded-sm" style={{ backgroundColor: "#FACC15" }} />
              HYBRID cells are striped
            </div>
            <div className="flex items-center gap-2 text-xs text-ink-body">
              <span className="hatched inline-block h-3 w-5 rounded-sm" style={{ backgroundColor: "#38BDF8" }} />
              Downgraded by the feasibility check
            </div>
            <div className="flex items-center gap-2 text-xs text-ink-body">
              <span className="inline-block h-3 w-3 rounded-full border-2 border-white" /> Current operating point
            </div>
            <div className="min-h-[92px] rounded-lg border border-white/10 bg-obsidian p-2.5 text-xs">
              {hover ? (
                <div className="space-y-0.5">
                  <ModeLabel mode={hover.mode} />
                  <div className="font-mono text-ink-body">Budget {fmtMs(hover.lat_ms)} ms</div>
                  <div className="font-mono text-ink-body">Link {fmtKbps(hover.bw_kbps)}</div>
                  <div className="font-mono text-ink-body">Net {hover.net >= 0 ? "+" : ""}{hover.net.toFixed(1)}</div>
                  {hover.downgraded && <div className="text-ink-muted">Downgraded for feasibility</div>}
                </div>
              ) : (
                <span className="text-ink-muted">Hover a cell to inspect it.</span>
              )}
            </div>
            <Origin value={map.data_origin} />
          </div>
        </div>
      )}
    </Card>
  );
}
