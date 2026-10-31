import { AlertTriangle, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import type { Mode } from "../types/api";

export const MODE_META: Record<Mode, { label: string; color: string; shape: string }> = {
  CLASSICAL: { label: "CLASSICAL", color: "#38BDF8", shape: "circle" },
  QUANTUM_SAFE: { label: "QUANTUM-SAFE", color: "#C4F135", shape: "square" },
  HYBRID: { label: "HYBRID", color: "#FACC15", shape: "triangle" },
};
export const MODES: Mode[] = ["CLASSICAL", "QUANTUM_SAFE", "HYBRID"];

export const CHART = {
  grid: "rgba(255, 255, 255, 0.07)",
  axis: "#8B948F",
  tooltip: {
    backgroundColor: "#171C19",
    border: "1px solid rgba(196, 241, 53, 0.35)",
    borderRadius: 8,
    fontSize: 12,
    color: "#FFFFFF",
  },
  tooltipItem: { color: "#D1D5DB" },
  cursor: { fill: "rgba(255, 255, 255, 0.04)" },
};

export const fmtMs = (value: number) =>
  value >= 100 ? value.toFixed(1) : value >= 1 ? value.toFixed(2) : value.toFixed(3);
export const fmtInt = (value: number) => Math.round(value).toLocaleString("en-US");
export const fmtKbps = (value: number) =>
  value >= 1000 ? `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)} Mbps` : `${Math.round(value)} kbps`;

export function Card({ title, subtitle, children, className = "" }: {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && <h2 className="text-sm">{title}</h2>}
      {subtitle && <p className="mt-1 text-xs text-ink-muted">{subtitle}</p>}
      <div className={title || subtitle ? "mt-3" : ""}>{children}</div>
    </section>
  );
}

export function ModeSwatch({ mode }: { mode: Mode }) {
  const { color, shape } = MODE_META[mode];
  if (shape === "triangle") {
    return (
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" className="inline-block">
        <path d="M5 0 L10 10 L0 10 Z" fill={color} />
      </svg>
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`inline-block h-2.5 w-2.5 ${shape === "circle" ? "rounded-full" : "rounded-sm"}`}
      style={{ backgroundColor: color }}
    />
  );
}

/** Line-chart marker whose shape, not only its color, identifies the mode. */
export function ModeDot({ cx, cy, mode }: { cx?: number; cy?: number; mode: Mode }) {
  if (cx === undefined || cy === undefined) return null;
  const { color, shape } = MODE_META[mode];
  const common = { fill: color, stroke: "#121614", strokeWidth: 1.5 };
  if (shape === "triangle") return <path d={`M${cx} ${cy - 6} L${cx + 6} ${cy + 5} L${cx - 6} ${cy + 5} Z`} {...common} />;
  if (shape === "square") return <rect x={cx - 4.5} y={cy - 4.5} width={9} height={9} rx={1.5} {...common} />;
  return <circle cx={cx} cy={cy} r={4.5} {...common} />;
}

export function ModeLabel({ mode }: { mode: Mode }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <ModeSwatch mode={mode} />
      {MODE_META[mode].label}
    </span>
  );
}

export function ModeLegend() {
  return (
    <div className="flex flex-wrap gap-4 text-xs text-ink-body">
      {MODES.map((mode) => (
        <ModeLabel key={mode} mode={mode} />
      ))}
    </div>
  );
}

export function WarningBanner({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="flex gap-2 rounded-lg border border-cyber-coral/50 bg-cyber-coral/10 p-2.5 text-sm text-ink-body">
      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-cyber-coral" aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export function Metric({ label, value, unit }: { label: string; value: ReactNode; unit?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-obsidian p-2.5">
      <div className="text-xs text-ink-muted">{label}</div>
      <div className="mt-0.5 font-mono text-sm text-ink [overflow-wrap:anywhere]">
        {value}
        {unit && <span className="ml-1 text-xs text-ink-muted">{unit}</span>}
      </div>
    </div>
  );
}

export function Origin({ value }: { value: string }) {
  return <span className="rounded border border-white/15 px-1.5 py-0.5 font-mono text-[10px] text-ink-muted">{value}</span>;
}

export function Spinner() {
  return <Loader2 size={15} className="animate-spin" aria-hidden="true" />;
}
