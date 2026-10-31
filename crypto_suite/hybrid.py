"""Round 1 unauthenticated hybrid: X25519 + ML-KEM-768. Round 2 lives in handshake.py."""
from . import classical, pqc


def establish() -> tuple[bytes, int]:
    c_secret, c_bytes = classical.establish()
    p_secret, p_bytes = pqc.establish()
    return c_secret + p_secret, c_bytes + p_bytes  # an attacker needs BOTH to recover the key
