import { ShieldCheck, Settings } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import { useExperiment } from "../context/ExperimentContext";

export default function HeaderBanner() {
  const { health, healthError, refreshBenchmarkViews } = useExperiment();
  const [showConfig, setShowConfig] = useState(false);
  const [customUrl, setCustomUrl] = useState(api.getBaseUrl());

  const handleSaveUrl = () => {
    api.setBaseUrl(customUrl);
    setShowConfig(false);
    void refreshBenchmarkViews();
  };

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-acid-muted bg-obsidian/90 px-4 py-3">
        <div className="flex items-center gap-3">
          <ShieldCheck className="text-acid" size={26} aria-hidden="true" />
          <div>
            <h1 className="text-lg leading-tight font-display tracking-wider">
              Adaptive<span className="text-acid">Crypt</span>
            </h1>
            <p className="text-xs text-ink-muted">Adaptive post-quantum security for low-latency hybrid computing</p>
          </div>
        </div>
        <div className="flex max-w-xl flex-wrap items-center justify-end gap-2 text-xs">
          {healthError ? (
            <button
              onClick={() => setShowConfig(true)}
              className="flex items-center gap-1.5 rounded border border-cyber-coral/60 bg-cyber-coral/10 px-2.5 py-1 text-cyber-coral hover:bg-cyber-coral/20 transition-colors"
              title="Click to configure backend URL"
            >
              <span>Backend offline</span>
              <Settings size={13} />
            </button>
          ) : (
            health && (
              <>
                <span className="rounded border border-acid/60 bg-acid/10 px-2 py-1 font-mono text-acid font-semibold">
                  ONLINE
                </span>
                <span className="rounded border border-acid-muted px-2 py-1 font-mono text-ink-body">
                  PQC: {health.pqc_fallback ? "kyber-py / dilithium-py" : health.pqc_backend}
                </span>
                <span className="rounded border border-white/15 px-2 py-1 text-ink-muted">Crypto measured locally</span>
                <span className="rounded border border-white/15 px-2 py-1 text-ink-muted">Network simulated</span>
                <button
                  onClick={() => setShowConfig(true)}
                  className="rounded border border-white/15 p-1 text-ink-muted hover:text-white"
                  title="Configure backend URL"
                >
                  <Settings size={14} />
                </button>
              </>
            )
          )}
        </div>
      </header>

      {showConfig && (
        <div className="border-b border-cyber-coral/40 bg-charcoal px-4 py-3 text-xs">
          <div className="mx-auto flex max-w-3xl flex-col gap-2 sm:flex-row sm:items-center">
            <span className="font-semibold text-ink">Backend Server URL:</span>
            <input
              type="text"
              value={customUrl}
              onChange={(e) => setCustomUrl(e.target.value)}
              placeholder="e.g. https://your-backend.onrender.com"
              className="flex-1 rounded border border-white/20 bg-obsidian px-2.5 py-1 text-ink font-mono focus:border-acid focus:outline-none"
            />
            <div className="flex gap-2">
              <button
                onClick={handleSaveUrl}
                className="rounded bg-acid px-3 py-1 font-semibold text-obsidian hover:bg-acid/90"
              >
                Connect
              </button>
              <button
                onClick={() => setShowConfig(false)}
                className="rounded border border-white/20 px-2.5 py-1 text-ink-muted hover:text-white"
              >
                Cancel
              </button>
            </div>
          </div>
          <p className="mt-1 text-[11px] text-ink-muted">
            Enter your Render public backend URL (e.g. <code className="text-acid">https://your-service.onrender.com</code>).
            It will connect immediately and be saved in your browser.
          </p>
        </div>
      )}
    </>
  );
}
