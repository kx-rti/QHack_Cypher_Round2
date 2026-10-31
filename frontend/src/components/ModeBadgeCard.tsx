import { Boxes, Layers, ShieldCheck } from "lucide-react";
import { useExperiment } from "../context/ExperimentContext";
import type { Mode } from "../types/api";
import { MODE_META } from "./ui";

const ICONS: Record<Mode, typeof Boxes> = { CLASSICAL: Boxes, QUANTUM_SAFE: ShieldCheck, HYBRID: Layers };

const DESCRIPTIONS: Record<Mode, string> = {
  CLASSICAL: "X25519 + HKDF-SHA256 + AES-256-GCM",
  QUANTUM_SAFE: "ML-KEM-768 + HKDF-SHA256 + AES-256-GCM",
  HYBRID: "X25519 + ML-KEM-768 + AES-256-GCM",
};

export default function ModeBadgeCard() {
  const { decision, displayedMode, hysteresisEnabled, hold, config } = useExperiment();
  if (!decision || !displayedMode) {
    return <section className="card text-sm text-ink-muted">Waiting for a decision from the backend.</section>;
  }
  const meta = MODE_META[displayedMode];
  const Icon = ICONS[displayedMode];
  const persistence = config?.hysteresis.persistence_samples ?? 3;
  return (
    <section className="card shadow-glow" aria-live="polite">
      <div className="flex items-start gap-4">
        <div className="rounded-xl border p-3" style={{ borderColor: `${meta.color}66` }}>
          <Icon size={36} style={{ color: meta.color }} aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wide text-ink-muted">Selected mode</div>
          <div className="font-display text-3xl font-bold uppercase tracking-wider text-ink">{meta.label}</div>
          <div className="mt-0.5 font-mono text-xs text-ink-muted">{DESCRIPTIONS[displayedMode]}</div>
        </div>
      </div>
      {hysteresisEnabled && hold.candidate && (
        <p className="mt-3 text-xs text-ink-body">
          Hysteresis is holding this mode. Policy proposes {MODE_META[hold.candidate].label} ({hold.streak} of {persistence} evaluations).
        </p>
      )}
      <div className="mt-4 space-y-3">
        <Score label="Security need" value={decision.need} max={100} color="#C4F135" />
        <Score label="Performance pressure" value={decision.pressure} max={100} color="#38BDF8" />
        <NetScore value={decision.net} />
      </div>
    </section>
  );
}

function Score({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs">
        <span className="text-ink-muted">{label}</span>
        <span className="font-mono text-ink">{value.toFixed(1)} / {max}</span>
      </div>
      <div className="mt-1 h-1.5 rounded-full bg-white/10">
        <div className="h-full rounded-full" style={{ width: `${Math.min(100, (value / max) * 100)}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function NetScore({ value }: { value: number }) {
  const clamped = Math.max(-100, Math.min(100, value));
  const width = Math.abs(clamped) / 2;
  return (
    <div>
      <div className="flex justify-between text-xs">
        <span className="text-ink-muted">Net score</span>
        <span className="font-mono text-ink">{value >= 0 ? "+" : ""}{value.toFixed(1)}</span>
      </div>
      <div className="relative mt-1 h-1.5 rounded-full bg-white/10">
        <div className="absolute left-1/2 top-[-2px] h-2.5 w-px bg-ink-muted" />
        <div
          className="absolute h-full rounded-full"
          style={{
            left: clamped >= 0 ? "50%" : `${50 - width}%`,
            width: `${width}%`,
            backgroundColor: clamped >= 0 ? "#C4F135" : "#38BDF8",
          }}
        />
      </div>
    </div>
  );
}
