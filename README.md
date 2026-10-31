# AdaptiveCrypt

Adaptive Quantum Cryptography for Low-Latency Hybrid Computing: a prototype that watches conditions (sensitivity, confidentiality lifetime, latency budget, bandwidth, payload size) and selects a key-establishment mode, using real standardized cryptography and an explainable policy.

| Mode | Key establishment | Bulk cipher | Round 1 wire bytes |
|---|---|---|---|
| CLASSICAL | X25519 + HKDF-SHA256 | AES-256-GCM | 64 |
| QUANTUM_SAFE | ML-KEM-768 + HKDF-SHA256 | AES-256-GCM | 2,272 |
| HYBRID | X25519 + ML-KEM-768 + HKDF-SHA256 | AES-256-GCM | 2,336 |

**Honest scope.** This is a prototype simulation of post-quantum cryptography (PQC), which is designed to resist known quantum attacks. It uses no quantum hardware and no QKD, it has had no expert review, and it is not hardened for production. Cryptographic timings and byte sizes are measured on your machine. Network transfer is simulated as `8 * bytes / bandwidth_kbps`.

## Setup

You need Python 3.10+ and Node.js 18+. On Windows, Node can be installed with `winget install OpenJS.NodeJS.LTS`.

```powershell
# Backend (macOS/Linux: source .venv/bin/activate)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m benchmarking.run_benchmarks   # measures this machine, writes benchmarking/results.json

# Frontend
cd frontend
npm install
cd ..
```

Benchmark timings are machine-specific, so re-run the benchmark on any new machine. Decisions use the numbers in `results.json`.

## Run

Use two terminals, both starting from the project root:

```powershell
uvicorn api.main:app --reload --port 8000
```

```powershell
cd frontend
npm run dev
```

Then open http://localhost:5173.

## Test

```powershell
pytest -v
cd frontend
npm run build
```

Tests that need the real dataset archives skip when the archives are absent. Loader logic is still tested against tiny temporary archives that the tests build themselves.

## Dataset archives

Copy the six archives (`archive.zip`, `archive (1).zip` to `archive (5).zip`) into a `Resources/` folder in the project root, or point to their folder:

```powershell
$env:ADAPTIVECRYPT_RESOURCES = "C:\path\to\Resources"
```

Without them the app still runs. The dataset table reports them as not found and replay returns a clear error. No data is ever synthesized in their place.

| File | Handling |
|---|---|
| `cloud.csv` | Negative predicted durations are filtered out; Mbps is converted to kbps; grouped by task type |
| `vmCloud_data.csv` | Stream-read; incomplete rows are dropped; head-of-stream sample |
| `Network_Traffic_Dataset_1k.csv` | Derives flow bytes and effective kbps; grouped by protocol |
| `Midterm_53_group.csv` | Aggregated into 1-second throughput windows for hysteresis replay |
| `processed_dataset.csv` | Quantiles in physical units, sampled from the first 200,000 rows. `preprocessed_dataset.csv` is unitless and unused |
| `cs448b_ipasn.csv` | Excluded: no byte, latency or bandwidth fields |

## PQC backend

`crypto_suite/pqc.py` uses `liboqs-python` when it is installed with a working liboqs C library, and otherwise falls back to `kyber-py` and `dilithium-py`. Both implement FIPS 203 and FIPS 204 with identical wire sizes. The fallback is educational and not constant-time hardened, so its timings are indicative only. The active backend is shown in the UI and recorded in API responses and reports.

To use liboqs, install `cmake` and a C toolchain, run `pip install liboqs-python`, then re-run the benchmark.

## Architecture

```
Sidebar, presets, traces -> decision_engine -> crypto_suite -> benchmarking/results.json
                                 |                  |
                             simulation          reporting -> PDF, CSV
                                 |                  |
                                 +---- api (FastAPI) ---- frontend (React)
```

| Package | Responsibility |
|---|---|
| `crypto_suite/` | The only package that imports crypto libraries. AES-GCM, HKDF, Dual-PRF, X25519, Ed25519, ML-KEM-768, ML-DSA-65, authenticated handshake |
| `decision_engine/` | Deterministic policy, `policy.yaml`, signed contributions, 2D map, hysteresis, EWMA forecaster |
| `benchmarking/` | Measures every mode and writes `results.json`. Never hand-edit this file |
| `simulation/` | Network model, scenarios, five workloads, session amortization, dataset loaders |
| `reporting/` | PDF (fpdf2 + matplotlib) and CSV reports built from live objects |
| `api/` | FastAPI routes and strict Pydantic v2 schemas |
| `frontend/` | React, Vite, TypeScript, Tailwind CSS, Recharts |

## REST API

Interactive docs are at http://127.0.0.1:8000/docs while the backend runs.

| Route | Purpose |
|---|---|
| `GET /api/health` | Status, PQC backend, host |
| `GET /api/benchmarks` | Contents of `results.json` |
| `POST /api/benchmarks/run` | Re-measure and overwrite `results.json` |
| `POST /api/decide` | Mode, scores, reasons, warnings, overheads, contributions |
| `GET /api/scenarios` | The four canonical scenarios and timeline |
| `POST /api/crypto/roundtrip` | Real key establishment, encrypt and decrypt |
| `GET /api/policy/config` | Parameters from `policy.yaml` |
| `POST /api/policy/sensitivity-map` | Latency vs. bandwidth decision grid |
| `POST /api/crypto/handshake` | Authenticated handshake, optional tamper simulation |
| `GET /api/workloads` | Five HPC/QC profiles with default simulations |
| `POST /api/workloads/simulate-session` | N-message session with periodic re-keying |
| `GET /api/datasets/summary` | Status and summaries of each archive |
| `POST /api/datasets/replay` | Reactive vs. hysteresis + EWMA over a trace |
| `POST /api/reports/pdf`, `/csv` | Report downloads |

## Provenance labels

| `data_origin` | Meaning |
|---|---|
| `MEASURED_LOCAL_CRYPTO` | `time.perf_counter()` timings and real byte lengths on this host |
| `SIMULATED_NETWORK_MODEL` | Computed link delay and session timelines |
| `DETERMINISTIC_POLICY` | Output of the scoring policy |
| `EXTERNAL_DATASET_TRACE` | Third-party data, never presented as our benchmarks |

## Specification corrections

Where the project documents disagree with their own formulas, the formulas win, and the tests assert what the formulas produce.

| Item | Documents say | Formula gives | Resolution |
|---|---|---|---|
| Zero lifetime (`LOW, 0 y, 500 ms, 100 Mbps`) | CLASSICAL | need 6, pressure 0, net +6: HYBRID | Kept the formula; the test expects HYBRID |
| Scenario 1 scores | pressure 67.15, net -60.88 | pressure 66.89, net -60.62 | Mode is unaffected (CLASSICAL) |
| Scenario 4 "downgrade" | Downgraded by the feasibility check | Net -34.5 already selects CLASSICAL, so the check never runs | Mode is unchanged; a reason and the re-key warning are added when HYBRID would exceed the budget |
| Session amortization | Monotonically decreasing with N | Each re-key adds a handshake, so the curve settles near `hs/R` and can rise slightly | Tested as strictly decreasing up to the first re-key, and with re-keying disabled |
| Chart 1 in the PDF | One grouped chart for ms and bytes | Different units | Two panels instead of a dual axis |
| Dual-PRF hash | Ricci et al. use SHA3-512 with bitrate-sized chunks | The project key schedule specifies SHA-256 | SHA-256 is used, so the paper's proof is not claimed to carry over |

## Known limitations

- Identity keys are generated per run and pinned out of band. There is no PKI, revocation or key storage.
- The handshake's wire totals include this prototype's own framing, so they are not comparable to TLS.
- `vmCloud_data.csv` does not state a unit for `network_traffic`, so replay reads it as kbps. This is an assumption.
- Forecasting informs inputs only; the deterministic policy still decides. Check the replay's forecast error and budget-violation metrics before claiming it helps on a given trace.
- An attacker who can fake bandwidth telemetry can push the policy toward CLASSICAL. The safety floor, hysteresis and downgrade warnings reduce this risk but do not remove it.
- HYBRID amber and QUANTUM-SAFE lime are hard to tell apart with color vision deficiency, so the UI adds shapes, textures and text labels. The palette itself is specified by the design reference.

## References

- Ricci et al. (2024), *Hybrid Keys in Practice*, IEEE Access 12: Dual-PRF combiner, AES-GCM re-keying bound.
- Rallis et al. (2025), *Interfacing Quantum Computing Systems with HPC Systems*: latency in hybrid feedback loops.
- Chhibber et al. (2025), *Quantum-Resistant Cryptographic Models for Next-Gen Cybersecurity*, IEEE APCIT: Kyber and Dilithium scaling.
- Singamaneni et al. (2025), *A Novel Hybrid Quantum-Crypto Standard*, IEEE JSTARS: domain workload parameters only. Its SIDH primitive is excluded because SIDH has known cryptanalytic breaks and is outside NIST FIPS 203/204.
