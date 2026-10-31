"""PDF and CSV reports built from live runtime objects. Nothing here is hardcoded measurement data."""
import csv
import io
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from fpdf import FPDF  # noqa: E402
from fpdf.enums import XPos, YPos  # noqa: E402
from fpdf.fonts import FontFace  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from crypto_suite.handshake import authenticated_handshake  # noqa: E402
from decision_engine.config import load_config  # noqa: E402
from decision_engine.explain import explain_decision  # noqa: E402
from decision_engine.policy import Conditions, decide, load_profile  # noqa: E402
from simulation.network import overhead_breakdown  # noqa: E402
from simulation.scenarios import SCENARIOS, TIMELINE  # noqa: E402
from simulation.sessions import simulate_session  # noqa: E402
from simulation.workloads import WORKLOADS, WORKLOADS_BY_ID  # noqa: E402

_MODES = ("CLASSICAL", "QUANTUM_SAFE", "HYBRID")
# Darker steps of the dashboard accents, chosen for a white page.
_COLORS = {"CLASSICAL": "#0369A1", "QUANTUM_SAFE": "#4D7C0F", "HYBRID": "#B45309"}
_LABELS = {"CLASSICAL": "CLASSICAL", "QUANTUM_SAFE": "QUANTUM-SAFE", "HYBRID": "HYBRID"}
_DEFAULT_CONDITIONS = Conditions("MEDIUM", 5.0, 50.0, 20_000, 10_000)
_HEADING = FontFace(emphasis="BOLD", fill_color=(235, 238, 232))


def _collect(conditions, workload_id, handshake_result, profile, config) -> dict:
    profile = profile or load_profile()
    config = config or load_config()
    conditions = conditions or _DEFAULT_CONDITIONS
    explained = explain_decision(conditions, profile, config)
    workload = WORKLOADS_BY_ID.get(workload_id) if workload_id else None
    # Without a handshake from the UI, run a real one now rather than reporting nothing.
    handshake = handshake_result or authenticated_handshake("HYBRID", use_socket=False)
    return {
        "profile": profile,
        "config": config,
        "conditions": conditions,
        "decision": explained["decision"],
        "factors": explained["factors"],
        "breakdown": [overhead_breakdown(m, conditions, profile) for m in _MODES],
        "workload": workload,
        "sessions": [simulate_session(w, profile) for w in WORKLOADS],
        "curve_session": simulate_session(workload or WORKLOADS[0], profile),
        "handshake": handshake,
        "scenarios": [(n, SCENARIOS[n], decide(SCENARIOS[n], profile, config)) for n in TIMELINE],
    }


def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _style_axis(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#BBBBBB")
    ax.spines["bottom"].set_color("#BBBBBB")
    ax.tick_params(colors="#444444", labelsize=8)
    ax.grid(axis="y", color="#E5E5E5", linewidth=0.6)
    ax.set_axisbelow(True)


def _overhead_chart(ctx: dict) -> io.BytesIO:
    """Two panels, not a dual axis: milliseconds and bytes have different scales."""
    rows = ctx["breakdown"]
    labels = [_LABELS[r["mode"]] for r in rows]
    colors = [_COLORS[r["mode"]] for r in rows]
    fig, (left, right) = plt.subplots(1, 2, figsize=(7.2, 2.7))
    for ax, key, title, fmt in ((left, "total_ms", "Estimated overhead (ms)", "{:.2f}"),
                                (right, "handshake_bytes", "Handshake wire size (bytes)", "{:,.0f}")):
        values = [r[key] for r in rows]
        bars = ax.bar(labels, values, color=colors, width=0.55)
        ax.set_title(title, fontsize=9, loc="left", color="#222222")
        ax.bar_label(bars, labels=[fmt.format(v) for v in values], fontsize=8, padding=2, color="#222222")
        ax.margins(y=0.18)
        _style_axis(ax)
    left.axhline(ctx["conditions"].latency_budget_ms, color="#B91C1C", linewidth=1, linestyle="--",
                 label=f"Budget {ctx['conditions'].latency_budget_ms:g} ms")
    left.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    return _png(fig)


def _amortization_chart(ctx: dict) -> io.BytesIO:
    session = ctx["curve_session"]
    curve = session["amortization_curve"]
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    xs = [p["n"] for p in curve]
    markers = {"CLASSICAL": "o", "QUANTUM_SAFE": "s", "HYBRID": "^"}
    for mode in _MODES:
        ax.plot(xs, [p[mode] for p in curve], color=_COLORS[mode], marker=markers[mode], markersize=4,
                linewidth=1.5, label=_LABELS[mode])
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(xs, [str(x) for x in xs])
    ax.minorticks_off()
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    ax.set_xlabel("Number of session messages N", fontsize=8, color="#444444")
    ax.set_ylabel("Amortized overhead (ms/msg)", fontsize=8, color="#444444")
    ax.set_title(f"{session['workload_name']}: re-key every {session['rekey_interval_messages']} messages",
                 fontsize=9, loc="left", color="#222222")
    ax.legend(fontsize=7, frameon=False)
    _style_axis(ax)
    fig.tight_layout()
    return _png(fig)


def _safe(text) -> str:
    """Core PDF fonts are Latin-1 only, so map the few non-Latin-1 characters in live strings."""
    table = {"—": "-", "–": "-", "’": "'", "→": "->", "×": "x", "≥": ">=", "≤": "<="}
    text = str(text)
    for a, b in table.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


class _Report(FPDF):
    def header(self):
        self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, "AdaptiveCrypt prototype report", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(30, 30, 30)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")
        self.set_text_color(30, 30, 30)

    def h1(self, text):
        self.ln(3)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 7, _safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def body(self, text, size=9):
        self.set_font("Helvetica", "", size)
        self.multi_cell(0, 4.6, _safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def bullets(self, items):
        for item in items:
            self.body(f"- {item}")

    def grid(self, rows, widths=None, size=8):
        self.set_font("Helvetica", "", size)
        with self.table(col_widths=widths, line_height=4.8, padding=1, text_align="LEFT",
                        headings_style=_HEADING) as table:
            for row in rows:
                cells = table.row()
                for value in row:
                    cells.cell(_safe(value))
        self.ln(2)


def generate_pdf_report(conditions: Conditions | None = None, workload_id: str | None = None,
                        handshake_result: dict | None = None, profile: dict | None = None,
                        config: dict | None = None) -> bytes:
    ctx = _collect(conditions, workload_id, handshake_result, profile, config)
    profile, c, d, hs = ctx["profile"], ctx["conditions"], ctx["decision"], ctx["handshake"]
    host = profile["host_metadata"]

    pdf = _Report(format="A4")
    pdf.set_margins(15, 14, 15)
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.multi_cell(0, 7, _safe("AdaptiveCrypt - Technical Benchmark, Policy & Session Evaluation Report"),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.body(f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
             f"Benchmark host: {host['platform']}; {host['processor']}; Python {host['python_version']}; "
             f"measured {host['timestamp']}\nPQC backend: {profile['pqc_backend']}")
    pdf.ln(2)
    pdf.set_fill_color(245, 247, 240)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.multi_cell(0, 4.4, _safe(
        "Provenance. MEASURED_LOCAL_CRYPTO: timings from time.perf_counter() and byte lengths of real objects on "
        "this host. SIMULATED_NETWORK_MODEL: transfer time = 8 x bytes / bandwidth_kbps; no real network or HPC-QC "
        "facility was used. EXTERNAL_DATASET_TRACE: third-party data, never presented as AdaptiveCrypt benchmarks. "
        "This is a prototype simulation using post-quantum cryptography (PQC); it has had no expert review."),
        border=1, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.h1("1. Selected Workload & Adaptive Decision")
    if ctx["workload"]:
        pdf.body(f"Workload: {ctx['workload'].name} ({ctx['workload'].citation})")
        pdf.ln(1)
    pdf.grid([["Sensitivity", "Lifetime (yrs)", "Latency budget (ms)", "Bandwidth (kbps)", "Payload (B)"],
              [c.sensitivity, f"{c.lifetime_years:g}", f"{c.latency_budget_ms:g}", f"{c.bandwidth_kbps:,.0f}",
               f"{c.data_bytes:,}"]])
    pdf.grid([["Selected mode", "Security need", "Performance pressure", "Net score"],
              [_LABELS[d.mode], f"{d.need:.2f}", f"{d.pressure:.2f}", f"{d.net:+.2f}"]])
    pdf.grid([["Factor", "Raw value", "Score", "Weight", "Signed contribution"]] + [
        [f["factor"], f["raw_value"], f"{f['normalized_score']:.1f}", f"{f['weight']:.2f}",
         f"{f['signed_contribution']:+.2f}"] for f in ctx["factors"]])
    pdf.body("Reasons:")
    pdf.bullets(d.reasons)
    if d.warnings:
        pdf.ln(1)
        pdf.body("Warnings:")
        pdf.bullets(d.warnings)

    pdf.h1("2. Measured Cryptographic Benchmarks")
    rows = [["Mode", "Median (ms)", "Mean (ms)", "p95 (ms)", "Wire bytes", "Est. overhead (ms)", "Within budget"]]
    for r in ctx["breakdown"]:
        m = profile["modes"][r["mode"]]
        rows.append([_LABELS[r["mode"]], f"{m['handshake_ms_median']:.3f}", f"{m['handshake_ms_mean']:.3f}",
                     f"{m['handshake_ms_p95']:.3f}", f"{m['handshake_bytes']:,}", f"{r['total_ms']:.3f}",
                     "Yes" if r["total_ms"] <= c.latency_budget_ms else "No"])
    pdf.grid(rows)
    pdf.body(f"AES-256-GCM throughput: {profile['aes']['mb_per_s']:,.0f} MB/s on a "
             f"{profile['aes']['payload_bytes']:,}-byte payload; {profile['aes']['ciphertext_overhead_bytes']} bytes "
             f"of overhead per message. Runs per mode: {profile['modes']['CLASSICAL']['runs']}.")
    pdf.ln(2)
    rows = [["Signature", "Public key (B)", "Signature (B)", "Keygen (ms)", "Sign (ms)", "Verify (ms)"]]
    for name, sig in profile["signatures"].items():
        rows.append([name, f"{sig['public_key_bytes']:,}", f"{sig['signature_bytes']:,}",
                     f"{sig['keygen_ms']['median']:.3f}", f"{sig['sign_ms']['median']:.3f}",
                     f"{sig['verify_ms']['median']:.3f}"])
    pdf.grid(rows)
    pdf.image(_overhead_chart(ctx), w=180)

    pdf.h1("3. Authenticated Handshake & HPC/QC Session Simulation")
    verdict = "succeeded" if hs["success"] else f"was rejected ({hs['error_message']})"
    pdf.body(f"A {hs['mode']} handshake over {hs['transport']} {verdict}. Elapsed {hs['elapsed_ms']:.2f} ms. "
             f"Tamper target: {hs['tamper_target']}. Client and server keys match: {hs['keys_match']}. "
             f"Transcript SHA-256: {hs['transcript_sha256'] or 'n/a'}. HYBRID keys use the Dual-PRF combiner "
             "(Ricci et al., 2024, Alg. 4, p. 7), bound to the transcript and authenticated with Ed25519 and ML-DSA-65.")
    pdf.ln(1)
    if hs["wire_breakdown"]:
        pdf.grid([["Wire component", "Bytes"]] + [[w["component"], f"{w['bytes']:,}"] for w in hs["wire_breakdown"]]
                 + [["Total", f"{hs['total_wire_bytes']:,}"]], widths=(3, 1))
    rows = [["Workload", "N / R", "Mode", "Total (ms)", "ms/msg", "Bytes/msg", "Recommended"]]
    for session in ctx["sessions"]:
        for mode in _MODES:
            m = session["modes"][mode]
            rows.append([session["workload_name"], f"{session['num_messages']} / {session['rekey_interval_messages']}",
                         _LABELS[mode], f"{m['total_overhead_ms']:,.1f}", f"{m['amortized_overhead_ms_per_msg']:.3f}",
                         f"{m['amortized_wire_bytes_per_msg']:.1f}", _LABELS[session["recommended_mode"]]])
    pdf.grid(rows, widths=(30, 12, 20, 14, 12, 12, 20), size=7)
    pdf.image(_amortization_chart(ctx), w=180)

    pdf.h1("4. Security Limitations, Warnings & Recommendations")
    limitations = [
        "Harvest-now-decrypt-later: under Mosca's rule, data is at risk today if its lifetime plus migration time "
        "exceeds the time until a cryptographically relevant quantum computer exists. The dates are uncertain, so "
        "lifetime is treated as a policy input.",
        "AES-GCM re-keying: NIST SP 800-38D caps a key at 2^32 messages; Ricci et al. (2024, p. 8) derive 515.39 s "
        "at 100 Gbps and re-key every 60 s. Sessions here re-key every R messages.",
        "Telemetry spoofing: an attacker who fakes low bandwidth could push the policy toward CLASSICAL (Cypher.pdf, "
        "p. 19). The safety floor, hysteresis and downgrade warnings reduce this risk but do not remove it; "
        "measurements must come from trusted sources.",
        "Authentication: identity keys are pinned per run. There is no PKI, revocation or key storage.",
    ]
    if "fallback" in profile["pqc_backend"]:
        limitations.append("Library hardening: the active PQC backend is an educational pure-Python implementation "
                           "that is not constant-time hardened. Its timings are indicative only.")
    pdf.bullets(limitations)
    return bytes(pdf.output())


def generate_csv_report(conditions: Conditions | None = None, workload_id: str | None = None,
                        handshake_result: dict | None = None, profile: dict | None = None,
                        config: dict | None = None) -> bytes:
    ctx = _collect(conditions, workload_id, handshake_result, profile, config)
    profile, d = ctx["profile"], ctx["decision"]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["section", "item", "metric", "value", "unit", "data_origin"])
    measured, simulated, policy = "MEASURED_LOCAL_CRYPTO", "SIMULATED_NETWORK_MODEL", "DETERMINISTIC_POLICY"

    writer.writerow(["benchmark", "host", "pqc_backend", profile["pqc_backend"], "", measured])
    for mode, m in profile["modes"].items():
        for metric, unit in (("handshake_ms_median", "ms"), ("handshake_ms_mean", "ms"), ("handshake_ms_p95", "ms"),
                             ("handshake_bytes", "bytes"), ("runs", "count")):
            writer.writerow(["benchmark", mode, metric, m[metric], unit, measured])
    writer.writerow(["benchmark", "AES-256-GCM", "mb_per_s", profile["aes"]["mb_per_s"], "MB/s", measured])
    writer.writerow(["benchmark", "AES-256-GCM", "ciphertext_overhead_bytes",
                     profile["aes"]["ciphertext_overhead_bytes"], "bytes", measured])
    for name, sig in profile["signatures"].items():
        writer.writerow(["benchmark", name, "public_key_bytes", sig["public_key_bytes"], "bytes", measured])
        writer.writerow(["benchmark", name, "signature_bytes", sig["signature_bytes"], "bytes", measured])
        for op in ("keygen_ms", "sign_ms", "verify_ms"):
            writer.writerow(["benchmark", name, f"{op}_median", sig[op]["median"], "ms", measured])
    for mode, m in profile["auth_handshake"].items():
        writer.writerow(["benchmark_auth_handshake", mode, "handshake_ms_median", m["handshake_ms_median"], "ms", measured])
        writer.writerow(["benchmark_auth_handshake", mode, "handshake_bytes", m["handshake_bytes"], "bytes", measured])

    writer.writerow(["active_decision", "conditions", "mode", d.mode, "", policy])
    for metric in ("need", "pressure", "net"):
        writer.writerow(["active_decision", "conditions", metric, getattr(d, metric), "score", policy])
    for f in ctx["factors"]:
        writer.writerow(["active_decision", f["factor"], "signed_contribution", f["signed_contribution"], "score", policy])
    for r in ctx["breakdown"]:
        writer.writerow(["active_overhead", r["mode"], "wire_transfer_ms", r["wire_transfer_ms"], "ms", simulated])
        writer.writerow(["active_overhead", r["mode"], "total_ms", r["total_ms"], "ms", simulated])

    for name, _, decision in ctx["scenarios"]:
        writer.writerow(["scenario_matrix", name, "mode", decision.mode, "", policy])
        writer.writerow(["scenario_matrix", name, "net", decision.net, "score", policy])

    for session in ctx["sessions"]:
        writer.writerow(["session", session["workload_name"], "recommended_mode", session["recommended_mode"], "", policy])
        for mode, m in session["modes"].items():
            label = f"{session['workload_name']} / {mode}"
            writer.writerow(["session", label, "total_overhead_ms", m["total_overhead_ms"], "ms", simulated])
            writer.writerow(["session", label, "amortized_overhead_ms_per_msg", m["amortized_overhead_ms_per_msg"], "ms/msg", simulated])
            writer.writerow(["session", label, "amortized_wire_bytes_per_msg", m["amortized_wire_bytes_per_msg"], "bytes/msg", simulated])
    return buf.getvalue().encode("utf-8")
