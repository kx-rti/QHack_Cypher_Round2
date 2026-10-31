"""Single entry point for upper layers; nothing outside crypto_suite imports crypto libraries."""
import statistics
import time

from . import classical, hybrid, pqc
from .common import decrypt, derive_key, encrypt

MODES = ("CLASSICAL", "QUANTUM_SAFE", "HYBRID")
_ESTABLISH = {"CLASSICAL": classical.establish, "QUANTUM_SAFE": pqc.establish, "HYBRID": hybrid.establish}


def establish(mode: str) -> tuple[bytes, int, float]:
    t0 = time.perf_counter()
    secret, wire_bytes = _ESTABLISH[mode]()
    key = derive_key(secret)
    return key, wire_bytes, (time.perf_counter() - t0) * 1000


def secure_roundtrip(mode: str, plaintext: bytes) -> dict:
    key, wire_bytes, hs_ms = establish(mode)
    t0 = time.perf_counter()
    blob = encrypt(key, plaintext)
    enc_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    out = decrypt(key, blob)
    dec_ms = (time.perf_counter() - t0) * 1000
    return {
        "mode": mode,
        "handshake_ms": hs_ms,
        "handshake_bytes": wire_bytes,
        "encrypt_ms": enc_ms,
        "decrypt_ms": dec_ms,
        "plaintext_bytes": len(plaintext),
        "ciphertext_bytes": len(blob),
        "overhead_bytes": len(blob) - len(plaintext),
        "ciphertext_preview_hex": blob[:32].hex(),
        "correct": out == plaintext,
        "pqc_backend": pqc.BACKEND,
    }


def _pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * p))]


def _stats(values: list[float]) -> dict:
    return {"median": statistics.median(values), "mean": statistics.mean(values), "p95": _pct(values, 0.95)}


def _bench_scheme(keygen, sign, verify, runs: int, warmup: int) -> dict:
    msg = b"AdaptiveCrypt signature benchmark transcript digest"
    keygen_ms, sign_ms, verify_ms, pk, sig = [], [], [], b"", b""
    for i in range(warmup + runs):
        t0 = time.perf_counter()
        sk, pk = keygen()
        t1 = time.perf_counter()
        sig = sign(sk, msg)
        t2 = time.perf_counter()
        assert verify(pk, msg, sig)
        t3 = time.perf_counter()
        if i >= warmup:
            keygen_ms.append((t1 - t0) * 1000)
            sign_ms.append((t2 - t1) * 1000)
            verify_ms.append((t3 - t2) * 1000)
    return {
        "public_key_bytes": len(pk),
        "signature_bytes": len(sig),
        "keygen_ms": _stats(keygen_ms),
        "sign_ms": _stats(sign_ms),
        "verify_ms": _stats(verify_ms),
        "runs": runs,
    }


def bench_signatures(runs: int = 30, warmup: int = 3) -> dict:
    """Measures Ed25519 vs ML-DSA-65 keygen, sign and verify on this machine."""
    return {
        "Ed25519": _bench_scheme(classical.generate_ed25519_keypair, classical.sign_ed25519,
                                 classical.verify_ed25519, runs, warmup),
        "ML-DSA-65": _bench_scheme(pqc.generate_mldsa_keypair, pqc.sign_mldsa, pqc.verify_mldsa, runs, warmup),
    }
