"""Measures every mode on this machine and writes benchmarking/results.json. Never hand-edit it."""
import argparse
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone

from crypto_suite import pqc
from crypto_suite.common import encrypt
from crypto_suite.handshake import authenticated_handshake
from crypto_suite.suite import MODES, bench_signatures, establish

RESULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.json")


def pct(values, p):
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * p))]


def bench_mode(mode, runs=200, warmup=10):
    for _ in range(warmup):
        establish(mode)
    times, wire = [], 0
    for _ in range(runs):
        _, wire, ms = establish(mode)
        times.append(ms)
    return {
        "handshake_ms_median": statistics.median(times),
        "handshake_ms_mean": statistics.mean(times),
        "handshake_ms_p95": pct(times, 0.95),
        "handshake_bytes": wire,
        "runs": runs,
    }


def bench_aes(size=1_000_000, runs=20):
    key, data = os.urandom(32), os.urandom(size)
    times, blob = [], b""
    for _ in range(runs):
        t0 = time.perf_counter()
        blob = encrypt(key, data)
        times.append(time.perf_counter() - t0)
    return {
        "mb_per_s": (size / 1e6) / statistics.median(times),
        "payload_bytes": size,
        "ciphertext_overhead_bytes": len(blob) - size,
        "runs": runs,
    }


def bench_auth_handshake(mode, runs=5):
    """Authenticated in-memory handshake, including signatures."""
    results = [authenticated_handshake(mode, use_socket=False, strict=True) for _ in range(runs)]
    times = [r["elapsed_ms"] for r in results]
    return {
        "handshake_ms_median": statistics.median(times),
        "handshake_ms_mean": statistics.mean(times),
        "handshake_ms_p95": pct(times, 0.95),
        "handshake_bytes": results[-1]["total_wire_bytes"],
        "runs": runs,
    }


def host_metadata():
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "python_version": sys.version.split()[0],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def run_all(runs, warmup, signature_runs=30, handshake_runs=5, path=RESULTS_PATH):
    out = {
        "pqc_backend": pqc.BACKEND,
        "host_metadata": host_metadata(),
        "modes": {m: bench_mode(m, runs, warmup) for m in MODES},
        "aes": bench_aes(),
        "signatures": bench_signatures(runs=signature_runs),
        "auth_handshake": {m: bench_auth_handshake(m, handshake_runs) for m in MODES},
        "data_origin": "MEASURED_LOCAL_CRYPTO",
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, path)
    return out


def main():
    # Pure-Python PQC is slow, so its default is smaller; --runs 200 still works.
    default_runs, default_warmup = (40, 5) if pqc.IS_FALLBACK else (200, 10)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=default_runs)
    parser.add_argument("--warmup", type=int, default=default_warmup)
    args = parser.parse_args()
    print(json.dumps(run_all(args.runs, args.warmup), indent=2))


if __name__ == "__main__":
    main()
