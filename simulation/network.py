"""Simulated network model: transfer time is computed from bytes and bandwidth, not measured."""


def transfer_ms(num_bytes: int, bandwidth_kbps: float) -> float:
    """Simulated serialization delay: (bytes * 8 bits) / (kbps * 1000) * 1000 ms."""
    return (num_bytes * 8.0) / max(bandwidth_kbps, 1e-6)


def overhead_breakdown(mode: str, cond, profile: dict) -> dict:
    m = profile["modes"][mode]
    aes_ms = cond.data_bytes / (profile["aes"]["mb_per_s"] * 1e6) * 1000.0
    wire_ms = transfer_ms(m["handshake_bytes"], cond.bandwidth_kbps)
    return {
        "mode": mode,
        "handshake_ms": m["handshake_ms_median"],
        "wire_transfer_ms": wire_ms,
        "aes_ms": aes_ms,
        "total_ms": m["handshake_ms_median"] + wire_ms + aes_ms,
        "handshake_bytes": m["handshake_bytes"],
    }


def overhead_ms(mode: str, cond, profile: dict) -> float:
    """Measured crypto time + simulated handshake transfer + measured-rate AES time."""
    return overhead_breakdown(mode, cond, profile)["total_ms"]
