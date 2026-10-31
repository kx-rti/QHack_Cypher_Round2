"""Round 2 Upgrade B: authenticated 3-message key establishment.

Key schedule follows Ricci et al. (2024, Sec. IV-D, Alg. 4, p. 7) and Cypher.pdf (p. 17). Both
transports exchange identical byte frames: a real TCP socket on 127.0.0.1, or in-memory buffers.

Prototype limitation: identity keys are generated per run and pinned out of band (they stand in
for certificates, so there is no PKI, no revocation, and they are not counted as wire bytes).
"""
import hashlib
import hmac
import os
import socket
import struct
import threading
import time

from . import classical, pqc
from .common import derive_key, dual_prf_combiner

PROTOCOL_VERSION = b"AdaptiveCrypt-2.0"
MODES = ("CLASSICAL", "QUANTUM_SAFE", "HYBRID")
TAMPER_TARGETS = ("none", "server_pk", "ciphertext", "signature")
_KDF_INFO = {
    "CLASSICAL": b"adaptive-v2-classical",
    "QUANTUM_SAFE": b"adaptive-v2-pqc",
    "HYBRID": b"adaptive-v2-hybrid",
}
_WIRE_LABELS = {
    "client_x25519_pk": "X25519 public key (client)",
    "server_x25519_pk": "X25519 public key (server)",
    "server_mlkem768_pk": "ML-KEM-768 public key",
    "mlkem_ct": "ML-KEM-768 ciphertext",
    "server_sig_ed25519": "Ed25519 signature (server)",
    "server_sig_mldsa": "ML-DSA-65 signature (server)",
    "client_sig_ed25519": "Ed25519 signature (client)",
    "client_sig_mldsa": "ML-DSA-65 signature (client)",
    "finished_mac": "Finished HMAC-SHA256",
    "client_nonce": "Client nonce",
    "server_nonce": "Server nonce",
}


class HandshakeAuthenticationError(Exception):
    """A signature, MAC or transcript check failed; the handshake was aborted."""


def _uses_classical(mode: str) -> bool:
    return mode in ("CLASSICAL", "HYBRID")


def _uses_pqc(mode: str) -> bool:
    return mode in ("QUANTUM_SAFE", "HYBRID")


def encode_frame(fields: dict[str, bytes]) -> bytes:
    out = bytearray()
    for name, value in fields.items():
        raw = name.encode()
        out += struct.pack(">B", len(raw)) + raw + struct.pack(">I", len(value)) + value
    return bytes(out)


def decode_frame(frame: bytes) -> dict[str, bytes]:
    fields, i = {}, 0
    try:
        while i < len(frame):
            n = frame[i]
            name = frame[i + 1:i + 1 + n].decode()
            i += 1 + n
            size = struct.unpack(">I", frame[i:i + 4])[0]
            i += 4
            if i + size > len(frame):
                raise ValueError("truncated field")
            fields[name] = frame[i:i + size]
            i += size
    except (IndexError, struct.error, UnicodeDecodeError, ValueError) as exc:
        raise HandshakeAuthenticationError(f"Malformed handshake frame: {exc}") from exc
    return fields


class _Identity:
    """A party's long-term signature keys; which schemes are used depends on the mode."""

    def __init__(self, mode: str):
        self.ed_sk = self.ed_pk = self.dsa_sk = self.dsa_pk = None
        if _uses_classical(mode):
            self.ed_sk, self.ed_pk = classical.generate_ed25519_keypair()
        if _uses_pqc(mode):
            self.dsa_sk, self.dsa_pk = pqc.generate_mldsa_keypair()

    def sign(self, prefix: str, digest: bytes) -> dict[str, bytes]:
        sigs = {}
        if self.ed_sk is not None:
            sigs[f"{prefix}_sig_ed25519"] = classical.sign_ed25519(self.ed_sk, digest)
        if self.dsa_sk is not None:
            sigs[f"{prefix}_sig_mldsa"] = pqc.sign_mldsa(self.dsa_sk, digest)
        return sigs

    def verify(self, prefix: str, digest: bytes, fields: dict[str, bytes]) -> bool:
        ok = True
        if self.ed_pk is not None:
            ok = ok and classical.verify_ed25519(self.ed_pk, digest, fields.get(f"{prefix}_sig_ed25519", b""))
        if self.dsa_pk is not None:
            ok = ok and pqc.verify_mldsa(self.dsa_pk, digest, fields.get(f"{prefix}_sig_mldsa", b""))
        return ok


def _session_key(mode: str, k_pq: bytes, k_cl: bytes, ct: bytes, pub_cl: bytes, transcript: bytes) -> bytes:
    if mode == "CLASSICAL":
        return derive_key(k_cl, info=_KDF_INFO[mode], salt=transcript)
    if mode == "QUANTUM_SAFE":
        return derive_key(k_pq, info=_KDF_INFO[mode], salt=transcript)
    combined = dual_prf_combiner(k_pq, k_cl, ct, pub_cl, salt=transcript)
    return derive_key(combined, info=_KDF_INFO[mode], salt=transcript)


def _finished_mac(key: bytes, transcript: bytes) -> bytes:
    return hmac.new(key, b"client-finished" + transcript, hashlib.sha256).digest()


class _Client:
    def __init__(self, mode: str, identity: _Identity, server_identity: _Identity, log):
        self.mode, self.identity, self.server_identity, self.log = mode, identity, server_identity, log
        self.session_key = self.transcript = None

    def hello(self) -> bytes:
        fields = {"protocol_version": PROTOCOL_VERSION, "selected_mode": self.mode.encode(),
                  "client_nonce": os.urandom(16)}
        if _uses_classical(self.mode):
            self._x_priv, fields["client_x25519_pk"] = classical.server_start()
        self.hello_bytes = encode_frame(fields)
        self.log("Client", "ClientHello sent", "ok", len(self.hello_bytes))
        return self.hello_bytes

    def finish(self, server_hello: bytes) -> bytes:
        fields = decode_frame(server_hello)
        params = {k: v for k, v in fields.items() if "_sig_" not in k}
        transcript_1 = hashlib.sha256(self.hello_bytes + encode_frame(params)).digest()
        if not self.server_identity.verify("server", transcript_1, fields):
            self.log("Client", "Verify server signature over transcript_1", "failed", 0,
                     "Server signature does not match the ClientHello and ServerHello parameters.")
            raise HandshakeAuthenticationError(
                "Client rejected ServerHello: server signature over transcript_1 is invalid.")
        self.log("Client", "Verify server signature over transcript_1", "ok", 0)

        k_cl = k_pq = ct = pub_cl = b""
        if _uses_pqc(self.mode):
            ct, k_pq = pqc.kem_encaps(fields["server_mlkem768_pk"])
            self.log("Client", "ML-KEM-768 encapsulation", "ok", 0)
        if _uses_classical(self.mode):
            k_cl = classical.server_finish(self._x_priv, fields["server_x25519_pk"])
            pub_cl = decode_frame(self.hello_bytes)["client_x25519_pk"] + fields["server_x25519_pk"]
            self.log("Client", "X25519 shared secret computed", "ok", 0)

        self.transcript = hashlib.sha256(self.hello_bytes + server_hello + ct).digest()
        self.session_key = _session_key(self.mode, k_pq, k_cl, ct, pub_cl, self.transcript)
        self.log("Client", "Session key derived, bound to full transcript", "ok", 0)

        out = {"mlkem_ct": ct} if ct else {}
        out.update(self.identity.sign("client", self.transcript))
        out["finished_mac"] = _finished_mac(self.session_key, self.transcript)
        frame = encode_frame(out)
        self.log("Client", "ClientKeyExchange + Finished sent", "ok", len(frame))
        return frame


class _Server:
    def __init__(self, identity: _Identity, client_identity: _Identity, log):
        self.identity, self.client_identity, self.log = identity, client_identity, log
        self.session_key = self.transcript = None

    def respond(self, client_hello: bytes) -> bytes:
        self.hello_bytes = client_hello
        fields = decode_frame(client_hello)
        self.mode = fields.get("selected_mode", b"").decode(errors="replace")
        if fields.get("protocol_version") != PROTOCOL_VERSION or self.mode not in MODES:
            raise HandshakeAuthenticationError("Server rejected ClientHello: unsupported version or mode.")
        self.log("Server", "ClientHello accepted", "ok", 0)

        params = {"server_nonce": os.urandom(16)}
        if _uses_classical(self.mode):
            self._x_priv, params["server_x25519_pk"] = classical.server_start()
            self._client_x = fields["client_x25519_pk"]
        if _uses_pqc(self.mode):
            params["server_mlkem768_pk"], self._kem_sk = pqc.kem_keygen()
        self._params = params
        transcript_1 = hashlib.sha256(client_hello + encode_frame(params)).digest()
        self.hello_out = encode_frame({**params, **self.identity.sign("server", transcript_1)})
        self.log("Server", "ServerHello signed and sent", "ok", len(self.hello_out))
        return self.hello_out

    def verify_finish(self, frame: bytes) -> None:
        fields = decode_frame(frame)
        ct = fields.get("mlkem_ct", b"")
        self.transcript = hashlib.sha256(self.hello_bytes + self.hello_out + ct).digest()
        if not self.client_identity.verify("client", self.transcript, fields):
            self.log("Server", "Verify client signature over full transcript", "failed", 0,
                     "Client signature does not match the transcript the server observed.")
            raise HandshakeAuthenticationError(
                "Server rejected ClientKeyExchange: client signature over the full transcript is invalid.")
        self.log("Server", "Verify client signature over full transcript", "ok", 0)

        k_cl = k_pq = pub_cl = b""
        if _uses_pqc(self.mode):
            k_pq = pqc.kem_decaps(self._kem_sk, ct)
            self.log("Server", "ML-KEM-768 decapsulation", "ok", 0)
        if _uses_classical(self.mode):
            k_cl = classical.server_finish(self._x_priv, self._client_x)
            pub_cl = self._client_x + self._params["server_x25519_pk"]
            self.log("Server", "X25519 shared secret computed", "ok", 0)
        self.session_key = _session_key(self.mode, k_pq, k_cl, ct, pub_cl, self.transcript)

        expected = _finished_mac(self.session_key, self.transcript)
        if not hmac.compare_digest(expected, fields.get("finished_mac", b"")):
            self.log("Server", "Verify Finished MAC", "failed", 0, "Finished MAC mismatch.")
            raise HandshakeAuthenticationError("Server rejected Finished: MAC mismatch.")
        self.log("Server", "Verify Finished MAC", "ok", 0)


def _flip_field(frame: bytes, field: str) -> bytes:
    """An on-path attacker flips one bit in the named field, leaving the framing intact."""
    fields = decode_frame(frame)
    value = bytearray(fields[field])
    value[0] ^= 0x01
    fields[field] = bytes(value)
    return encode_frame(fields)


def _tamper_field(target: str, mode: str) -> str | None:
    """Which field the target hits in this mode, or None if the mode does not carry one."""
    if target == "server_pk":
        return "server_mlkem768_pk" if _uses_pqc(mode) else "server_x25519_pk"
    if target == "signature":
        return "server_sig_mldsa" if _uses_pqc(mode) else "server_sig_ed25519"
    if target == "ciphertext":
        return "mlkem_ct" if _uses_pqc(mode) else None
    return None


def _send_frame(sock: socket.socket, frame: bytes) -> None:
    sock.sendall(struct.pack(">I", len(frame)) + frame)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed the connection")
        buf += chunk
    return bytes(buf)


def _recv_frame(sock: socket.socket) -> bytes:
    return _recv_exact(sock, struct.unpack(">I", _recv_exact(sock, 4))[0])


def _run_memory(client: _Client, server: _Server, tamper) -> list[bytes]:
    hello = client.hello()
    server_hello = server.respond(hello)
    finish = client.finish(tamper(server_hello))
    server.verify_finish(tamper(finish))
    return [hello, server_hello, finish]


def _run_socket(client: _Client, server: _Server, tamper) -> list[bytes]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(30)
    port = listener.getsockname()[1]
    server_error: list[Exception] = []
    frames: list[bytes] = []

    def serve():
        try:
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(30)
                _send_frame(conn, server.respond(_recv_frame(conn)))
                server.verify_finish(_recv_frame(conn))
        except ConnectionError:
            server.log("Server", "Connection closed by client after abort", "info", 0)
        except Exception as exc:
            server_error.append(exc)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=30) as sock:
            hello = client.hello()
            frames.append(hello)
            _send_frame(sock, hello)
            server_hello = _recv_frame(sock)
            frames.append(server_hello)
            finish = client.finish(tamper(server_hello))
            frames.append(finish)
            _send_frame(sock, tamper(finish))
    finally:
        thread.join(timeout=30)
        listener.close()
    if server_error:
        raise server_error[0]
    return frames


def _wire_breakdown(frames: list[bytes]) -> list[dict]:
    items, payload = [], 0
    for frame in frames:
        for name, value in decode_frame(frame).items():
            if name in _WIRE_LABELS and value:
                items.append({"component": _WIRE_LABELS[name], "field": name, "bytes": len(value)})
                payload += len(value)
    # Everything else on the wire: version/mode strings, field names, and length prefixes.
    total = sum(len(f) + 4 for f in frames)
    items.append({"component": "Protocol framing and metadata", "field": "framing", "bytes": total - payload})
    return items


def authenticated_handshake(mode: str, use_socket: bool = True, tamper_target: str | None = None,
                            strict: bool = False) -> dict:
    """Runs the handshake and returns a structured result.

    A failed verification returns success=False with the step log, or raises
    HandshakeAuthenticationError when strict=True.
    """
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")
    target = tamper_target or "none"
    if target not in TAMPER_TARGETS:
        raise ValueError(f"Unknown tamper target: {target}")

    steps: list[dict] = []

    def log(actor: str, action: str, status: str, wire_bytes: int, detail: str = "") -> None:
        steps.append({"actor": actor, "action": action, "status": status, "wire_bytes": wire_bytes, "detail": detail})

    field = _tamper_field(target, mode)
    tamper_applied = False

    def tamper(frame: bytes) -> bytes:
        nonlocal tamper_applied
        if field and not tamper_applied and field in decode_frame(frame):
            tamper_applied = True
            log("Attacker", f"Flipped 1 bit in {field} in transit", "info", 0)
            return _flip_field(frame, field)
        return frame

    if target != "none" and field is None:
        log("Attacker", f"Target '{target}' does not exist in {mode} mode; nothing was tampered", "info", 0)

    # Identities are provisioned out of band, so they fall outside the measured handshake.
    server_identity, client_identity = _Identity(mode), _Identity(mode)
    client = _Client(mode, client_identity, server_identity, log)
    server = _Server(server_identity, client_identity, log)

    error = None
    frames: list[bytes] = []
    t0 = time.perf_counter()
    try:
        frames = (_run_socket if use_socket else _run_memory)(client, server, tamper)
    except (HandshakeAuthenticationError, ConnectionError, OSError, ValueError, KeyError) as exc:
        error = exc
    elapsed_ms = (time.perf_counter() - t0) * 1000

    keys_match = bool(client.session_key and server.session_key
                      and hmac.compare_digest(client.session_key, server.session_key))
    success = error is None and keys_match
    if strict and error is not None:
        raise HandshakeAuthenticationError(str(error)) from error

    return {
        "success": success,
        "mode": mode,
        "transport": "tcp_loopback" if use_socket else "in_memory",
        "elapsed_ms": elapsed_ms,
        "total_wire_bytes": sum(len(f) + 4 for f in frames) if success else 0,
        "wire_breakdown": _wire_breakdown(frames) if success else [],
        "transcript_sha256": client.transcript.hex() if client.transcript else "",
        "client_key_fp": hashlib.sha256(client.session_key).hexdigest()[:16] if client.session_key else "",
        "server_key_fp": hashlib.sha256(server.session_key).hexdigest()[:16] if server.session_key else "",
        "keys_match": keys_match,
        "steps_log": steps,
        "tamper_target": target,
        "tamper_applied": tamper_applied,
        "error_message": str(error) if error else "",
        "pqc_backend": pqc.BACKEND,
        "data_origin": "MEASURED_LOCAL_CRYPTO",
    }
