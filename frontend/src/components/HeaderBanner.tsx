import { ShieldCheck } from "lucide-react";
import { useExperiment } from "../context/ExperimentContext";

export default function HeaderBanner() {
  const { health, healthError } = useExperiment();
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-acid-muted bg-obsidian/90 px-4 py-3">
      <div className="flex items-center gap-3">
        <ShieldCheck className="text-acid" size={26} aria-hidden="true" />
        <div>
          <h1 className="text-lg leading-tight">
            Adaptive<span className="text-acid">Crypt</span>
          </h1>
          <p className="text-xs text-ink-muted">Adaptive post-quantum security for low-latency hybrid computing</p>
        </div>
      </div>
      <div className="flex max-w-xl flex-wrap justify-end gap-2 text-xs">
        {healthError ? (
          <span className="rounded border border-cyber-coral/50 px-2 py-1 text-cyber-coral">Backend offline</span>
        ) : (
          health && (
            <>
              <span className="rounded border border-acid-muted px-2 py-1 font-mono text-ink-body">
                PQC: {health.pqc_fallback ? "kyber-py / dilithium-py" : health.pqc_backend}
              </span>
              <span className="rounded border border-white/15 px-2 py-1 text-ink-muted">Crypto measured locally</span>
              <span className="rounded border border-white/15 px-2 py-1 text-ink-muted">Network simulated</span>
              {health.pqc_fallback && (
                <span className="rounded border border-cyber-amber/50 px-2 py-1 text-cyber-amber">
                  Educational backend: not constant-time hardened, timings indicative only
                </span>
              )}
            </>
          )
        )}
      </div>
    </header>
  );
}
