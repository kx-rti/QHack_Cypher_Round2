"""Shared primitives: HKDF key derivation, AES-256-GCM, and the Dual-PRF combiner."""
import hashlib
import hmac
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def derive_key(secret: bytes, info: bytes = b"adaptive-crypto-v1", salt: bytes | None = None) -> bytes:
    """Turn raw shared secret(s) into a clean 32-byte AES key."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(secret)


def encrypt(key: bytes, plaintext: bytes, aad: bytes | None = None) -> bytes:
    """AES-256-GCM with a fresh 12-byte nonce; returns nonce || ciphertext || tag (+28 B)."""
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes | None = None) -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


def _g(key: bytes, public: bytes, expansion: int = 3) -> bytes:
    """One-way expansion g(K, pp) (Ricci et al., 2024, Sec. IV-D, Alg. 3): H(K||pp1)||H(K||pp2)||H(K||pp3).

    Ricci et al. instantiate H with SHA3-512 and bitrate-sized pp chunks. This prototype uses
    SHA-256 per the project key schedule and splits pp into three equal parts, so the X25519
    chunks are shorter than the paper requires; the paper's proof is not claimed to carry over.
    """
    step = max(1, len(public) // expansion)
    chunks = [public[i * step:(i + 1) * step if i < expansion - 1 else None] for i in range(expansion)]
    return b"".join(hashlib.sha256(key + chunk).digest() for chunk in chunks)


def dual_prf_combiner(k_pq: bytes, k_cl: bytes, ct_pq: bytes, pub_cl: bytes, salt: bytes) -> bytes:
    """Two-key Dual-PRF combiner (Ricci et al., 2024, Sec. IV-D, Alg. 4, Line 7, p. 7).

    K = H(HMAC(k1, u2 || 1) XOR HMAC(k2, u1 || 2)), where k_i = HMAC(salt, K_i). The output
    stays unpredictable as long as at least one input secret does (Sec. V, Thm. 1, p. 9).
    """
    k1 = hmac.new(salt, k_pq, hashlib.sha256).digest()
    k2 = hmac.new(salt, k_cl, hashlib.sha256).digest()
    u1 = _g(k_pq, ct_pq)
    u2 = _g(k_cl, pub_cl)
    left = hmac.new(k1, u2 + b"\x01", hashlib.sha256).digest()
    right = hmac.new(k2, u1 + b"\x02", hashlib.sha256).digest()
    return hashlib.sha256(bytes(a ^ b for a, b in zip(left, right))).digest()
