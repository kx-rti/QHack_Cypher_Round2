"""Multi-message session simulator with periodic re-keying (Round 2 Upgrade C).

Re-keying follows Ricci et al. (2024, Sec. IV-E, Footnote 4, p. 8): NIST SP 800-38D caps AES-GCM
at 2^32 messages per key, which that paper turns into a time bound and a 60-second re-key policy.
"""
from decision_engine.policy import decide

from .network import transfer_ms
from .workloads import WorkloadProfile

CURVE_POINTS = (1, 5, 10, 25, 50, 100, 250, 500)
AES_GCM_OVERHEAD_BYTES = 28  # 12-byte nonce + 16-byte tag per message


def aes_gcm_rekey_bound_seconds(link_bits_per_s: float = 1e11, packet_bytes: int = 1500) -> float:
    """T_max = 8 * packet_bytes * 2^32 / link rate; 515.39 s at 100 Gbps with 1500-byte packets."""
    return 8 * packet_bytes * 2 ** 32 / link_bits_per_s


def num_handshakes(n: int, r: int) -> int:
    return 1 + (n - 1) // r


def _handshake_cost(mode: str, profile: dict, authenticated: bool) -> tuple[float, int]:
    source = profile["auth_handshake"] if authenticated else profile["modes"]
    return source[mode]["handshake_ms_median"], source[mode]["handshake_bytes"]


def _totals(mode: str, n: int, r: int, workload: WorkloadProfile, profile: dict, authenticated: bool) -> dict:
    c = workload.conditions
    hs_ms, hs_bytes = _handshake_cost(mode, profile, authenticated)
    aes_ms = c.data_bytes / (profile["aes"]["mb_per_s"] * 1e6) * 1000.0
    handshakes = num_handshakes(n, r)
    total_ms = (handshakes * (hs_ms + transfer_ms(hs_bytes, c.bandwidth_kbps))
                + n * (aes_ms + transfer_ms(AES_GCM_OVERHEAD_BYTES, c.bandwidth_kbps)))
    total_bytes = handshakes * hs_bytes + n * AES_GCM_OVERHEAD_BYTES
    return {
        "handshakes": handshakes,
        "total_overhead_ms": total_ms,
        "amortized_overhead_ms_per_msg": total_ms / n,
        "total_crypto_wire_bytes": total_bytes,
        "amortized_wire_bytes_per_msg": total_bytes / n,
    }


def simulate_session(workload: WorkloadProfile, profile: dict, include_authenticated_handshake: bool = False) -> dict:
    n, r = workload.num_messages, workload.rekey_interval_messages
    modes = {m: _totals(m, n, r, workload, profile, include_authenticated_handshake) for m in profile["modes"]}
    curve = [
        {"n": point, **{m: _totals(m, point, r, workload, profile, include_authenticated_handshake)
                        ["amortized_overhead_ms_per_msg"] for m in profile["modes"]}}
        for point in CURVE_POINTS
    ]
    return {
        "workload_id": workload.id,
        "workload_name": workload.name,
        "num_messages": n,
        "rekey_interval_messages": r,
        "include_authenticated_handshake": include_authenticated_handshake,
        "modes": modes,
        "amortization_curve": curve,
        "recommended_mode": decide(workload.conditions, profile).mode,
        "data_origin": "SIMULATED_NETWORK_MODEL",
    }
