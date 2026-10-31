import { useExperiment } from "../context/ExperimentContext";
import { MODE_META } from "./ui";

export default function TickerFooter() {
  const { health, displayedMode } = useExperiment();
  const items = [
    "ADAPTIVECRYPT ENGINE",
    `PQC BACKEND: ${health ? (health.pqc_fallback ? "KYBER-PY / DILITHIUM-PY" : health.pqc_backend.toUpperCase()) : "UNKNOWN"}`,
    `LOCAL CRYPTO BENCHMARKS: ${health?.benchmarks_loaded ? "VERIFIED" : "NOT RUN"}`,
    "NETWORK MODEL: SIMULATED",
    `ACTIVE MODE: ${displayedMode ? MODE_META[displayedMode].label : "NONE"}`,
  ];
  const line = items.join("  ~  ");
  return (
    <footer className="overflow-hidden whitespace-nowrap border-t border-acid bg-acid py-1 font-mono text-xs font-medium text-obsidian" aria-label={items.join(", ")}>
      <div className="ticker-track inline-block" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className="px-4">{line}  ~</span>
        ))}
      </div>
    </footer>
  );
}
