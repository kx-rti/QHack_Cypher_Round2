import clsx from "clsx";
import { ArrowLeft, ArrowRight, CheckCircle2, Info, ShieldAlert, XCircle } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import { Card, fmtInt, fmtMs, Metric, MODE_META, MODES, Origin, Spinner, WarningBanner } from "../components/ui";
import { useExperiment } from "../context/ExperimentContext";
import type { Mode, TamperTarget, WireItem } from "../types/api";

const TAMPER_OPTIONS: { value: TamperTarget; label: string }[] = [
  { value: "none", label: "No Tampering" },
  { value: "server_pk", label: "Tamper Server Public Key" },
  { value: "ciphertext", label: "Tamper ML-KEM Ciphertext" },
  { value: "signature", label: "Tamper Transcript Signature" },
];

const MESSAGES = [
  { title: "1. ClientHello", direction: "right", fields: ["client_nonce", "client_x25519_pk"] },
  { title: "2. ServerHello + Signature", direction: "left",
    fields: ["server_nonce", "server_x25519_pk", "server_mlkem768_pk", "server_sig_ed25519", "server_sig_mldsa"] },
  { title: "3. ClientFinish + Key Derivation", direction: "right",
    fields: ["mlkem_ct", "client_sig_ed25519", "client_sig_mldsa", "finished_mac"] },
];

export default function HandshakeInspectorPage() {
  const { handshakeResult: result, setHandshakeResult } = useExperiment();
  const [mode, setMode] = useState<Mode>("HYBRID");
  const [useSocket, setUseSocket] = useState(true);
  const [tamper, setTamper] = useState<TamperTarget>("none");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      setHandshakeResult(await api.handshake(mode, useSocket, tamper));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const breakdown = result?.wire_breakdown ?? [];

  return (
    <>
      <Card title="Handshake execution">
        <div className="grid gap-3 md:grid-cols-3">
          <div>
            <label htmlFor="hs-mode" className="field-label">Mode</label>
            <select id="hs-mode" className="control" value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
              {MODES.map((m) => <option key={m} value={m}>{MODE_META[m].label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="hs-transport" className="field-label">Transport</label>
            <select id="hs-transport" className="control" value={useSocket ? "socket" : "memory"} onChange={(e) => setUseSocket(e.target.value === "socket")}>
              <option value="socket">Real TCP Loopback Socket (127.0.0.1)</option>
              <option value="memory">In-Memory Deterministic</option>
            </select>
          </div>
          <div>
            <label htmlFor="hs-tamper" className="field-label">Active MitM attack simulator</label>
            <select id="hs-tamper" className="control" value={tamper} onChange={(e) => setTamper(e.target.value as TamperTarget)}>
              {TAMPER_OPTIONS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
        </div>
        <button type="button" className="btn btn-primary mt-3" onClick={() => void run()} disabled={busy}>
          {busy && <Spinner />} Run Authenticated Handshake
        </button>
        {error && <div className="mt-3"><WarningBanner>{error}</WarningBanner></div>}
      </Card>

      {!result && <Card><p className="text-sm text-ink-muted">Run a handshake to see measured byte counts, transcript and keys.</p></Card>}

      {result && (
        <>
          {result.success ? (
            <div className="flex items-center gap-3 rounded-xl border border-acid bg-acid/10 p-3 text-sm text-ink">
              <CheckCircle2 className="text-acid" size={22} aria-hidden="true" />
              Verified: signatures and Finished MAC passed, and both sides derived the same key.
            </div>
          ) : (
            <div role="alert" className="flex items-center gap-3 rounded-xl border border-cyber-coral bg-cyber-coral/10 p-3 text-sm text-ink">
              <ShieldAlert className="text-cyber-coral" size={22} aria-hidden="true" />
              <div><strong>MitM tamper detected.</strong> {result.error_message}</div>
            </div>
          )}
          {result.tamper_target !== "none" && !result.tamper_applied && (
            <WarningBanner>{MODE_META[result.mode].label} has no ML-KEM ciphertext, so this attack had nothing to tamper with.</WarningBanner>
          )}

          <div className="grid gap-4 xl:grid-cols-2">
            <Card title="Client-server sequence" subtitle={result.success ? "Measured field sizes from this run." : "Field sizes are shown for completed handshakes only."}>
              <div className="flex justify-between text-xs font-medium uppercase tracking-wide text-ink-muted">
                <span>Client (HPC node)</span><span>Server (QC gateway)</span>
              </div>
              <ol className="mt-2 space-y-2">
                {MESSAGES.map((message) => (
                  <li key={message.title} className="rounded-lg border border-white/10 bg-obsidian p-2.5">
                    <div className="flex items-center gap-2 text-sm font-medium text-ink">
                      {message.direction === "right"
                        ? <ArrowRight size={15} className="text-acid" aria-label="Client to server" />
                        : <ArrowLeft size={15} className="text-acid" aria-label="Server to client" />}
                      {message.title}
                    </div>
                    <FieldList items={breakdown.filter((w) => message.fields.includes(w.field))} />
                  </li>
                ))}
              </ol>
              {result.success && (
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <Metric label="Total on the wire" value={fmtInt(result.total_wire_bytes)} unit="B" />
                  <Metric label="Elapsed" value={fmtMs(result.elapsed_ms)} unit="ms" />
                </div>
              )}
            </Card>

            <Card title="Verification and Dual-PRF" subtitle="Ricci et al., 2024, Sec. IV-D, Alg. 4, p. 7">
              <pre className="overflow-x-auto rounded-lg border border-white/10 bg-obsidian p-2.5 font-mono text-xs text-ink-body">{`k1 = HMAC(salt, K_pq)    u1 = g(K_pq, ct)
k2 = HMAC(salt, K_cl)    u2 = g(K_cl, p_cl)
K  = H(HMAC(k1, u2 || 1) XOR HMAC(k2, u1 || 2))
session_key = HKDF-SHA256(K, salt = transcript)`}</pre>
              <p className="mt-2 text-xs text-ink-muted">HYBRID mode only. CLASSICAL and QUANTUM-SAFE apply HKDF to their single secret.</p>
              <div className="mt-3 space-y-2">
                <Metric label="Transcript SHA-256" value={result.transcript_sha256 || "Not reached"} />
                <div className="grid grid-cols-2 gap-2">
                  <Metric label="Client key fingerprint" value={result.client_key_fp || "Not derived"} />
                  <Metric label="Server key fingerprint" value={result.server_key_fp || "Not derived"} />
                </div>
                <Metric label="Keys match" value={result.keys_match ? "Yes" : "No"} />
              </div>
              <div className="mt-2"><Origin value={result.data_origin} /></div>
            </Card>
          </div>

          <Card title="Step log">
            <ol className="space-y-1">
              {result.steps_log.map((step, index) => (
                <li key={index} className="flex items-start gap-2 text-sm">
                  {step.status === "ok" && <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-acid" aria-label="Passed" />}
                  {step.status === "failed" && <XCircle size={15} className="mt-0.5 shrink-0 text-cyber-coral" aria-label="Failed" />}
                  {step.status === "info" && <Info size={15} className="mt-0.5 shrink-0 text-cyber-amber" aria-label="Note" />}
                  <div className={clsx(step.status === "failed" && "text-ink")}>
                    <span className="mr-1.5 font-mono text-xs text-ink-muted">{step.actor}</span>
                    {step.action}
                    {step.wire_bytes > 0 && <span className="ml-1.5 font-mono text-xs text-ink-muted">({fmtInt(step.wire_bytes)} B)</span>}
                    {step.detail && <div className="text-xs text-ink-muted">{step.detail}</div>}
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </>
      )}
    </>
  );
}

function FieldList({ items }: { items: WireItem[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-1.5 grid gap-x-4 gap-y-0.5 text-xs sm:grid-cols-2">
      {items.map((item) => (
        <li key={item.field} className="flex justify-between gap-2">
          <span className="text-ink-muted">{item.component}</span>
          <span className="font-mono text-ink">{fmtInt(item.bytes)} B</span>
        </li>
      ))}
    </ul>
  );
}
