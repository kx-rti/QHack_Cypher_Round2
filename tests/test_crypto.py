import pytest

from crypto_suite import classical, pqc
from crypto_suite.common import decrypt, dual_prf_combiner, encrypt
from crypto_suite.handshake import HandshakeAuthenticationError, authenticated_handshake
from crypto_suite.suite import MODES, establish, secure_roundtrip


@pytest.mark.parametrize("mode", MODES)
def test_roundtrip(mode):
    result = secure_roundtrip(mode, b"secret " * 50)
    assert result["correct"]
    assert result["overhead_bytes"] == 28


def test_wrong_key_fails():
    key, _, _ = establish("CLASSICAL")
    other, _, _ = establish("CLASSICAL")
    with pytest.raises(Exception):
        decrypt(other, encrypt(key, b"x"))


def test_tamper_detected():
    key, _, _ = establish("CLASSICAL")
    blob = bytearray(encrypt(key, b"hello"))
    blob[-1] ^= 1
    with pytest.raises(Exception):
        decrypt(key, bytes(blob))


@pytest.mark.parametrize("mode,expected", [("CLASSICAL", 64), ("QUANTUM_SAFE", 2272), ("HYBRID", 2336)])
def test_wire_sizes(mode, expected):
    assert establish(mode)[1] == expected


def test_signature_sizes_and_rejection():
    sk, pk = pqc.generate_mldsa_keypair()
    sig = pqc.sign_mldsa(sk, b"m")
    assert (len(pk), len(sig)) == (1952, 3309)
    assert pqc.verify_mldsa(pk, b"m", sig)
    assert not pqc.verify_mldsa(pk, b"n", sig)
    ed_sk, ed_pk = classical.generate_ed25519_keypair()
    ed_sig = classical.sign_ed25519(ed_sk, b"m")
    assert (len(ed_pk), len(ed_sig)) == (32, 64)
    assert not classical.verify_ed25519(ed_pk, b"n", ed_sig)


def test_dual_prf_depends_on_both_secrets():
    args = (b"\x01" * 32, b"\x02" * 32, b"c" * 1088, b"p" * 64, b"s" * 32)
    base = dual_prf_combiner(*args)
    assert len(base) == 32
    assert base == dual_prf_combiner(*args)
    assert base != dual_prf_combiner(b"\x03" * 32, *args[1:])
    assert base != dual_prf_combiner(args[0], b"\x03" * 32, *args[2:])
    assert base != dual_prf_combiner(*args[:2], b"d" * 1088, *args[3:])
    assert base != dual_prf_combiner(*args[:4], b"t" * 32)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("use_socket", [True, False])
def test_authenticated_handshake_socket_and_memory(mode, use_socket):
    result = authenticated_handshake(mode, use_socket=use_socket, strict=True)
    assert result["success"] and result["keys_match"]
    assert result["client_key_fp"] == result["server_key_fp"] != ""
    assert result["total_wire_bytes"] == sum(w["bytes"] for w in result["wire_breakdown"])


def _component_bytes(result):
    return {w["field"]: w["bytes"] for w in result["wire_breakdown"]}


def test_handshake_wire_components_are_real_sizes():
    parts = _component_bytes(authenticated_handshake("HYBRID", use_socket=False, strict=True))
    assert parts["client_x25519_pk"] == parts["server_x25519_pk"] == 32
    assert parts["server_mlkem768_pk"] == 1184
    assert parts["mlkem_ct"] == 1088
    assert parts["server_sig_ed25519"] == parts["client_sig_ed25519"] == 64
    assert parts["server_sig_mldsa"] == parts["client_sig_mldsa"] == 3309


@pytest.mark.parametrize("use_socket", [True, False])
@pytest.mark.parametrize("mode,target", [
    ("CLASSICAL", "server_pk"), ("CLASSICAL", "signature"),
    ("QUANTUM_SAFE", "server_pk"), ("QUANTUM_SAFE", "ciphertext"), ("QUANTUM_SAFE", "signature"),
    ("HYBRID", "server_pk"), ("HYBRID", "ciphertext"), ("HYBRID", "signature"),
])
def test_authenticated_handshake_tamper_rejected(mode, target, use_socket):
    with pytest.raises(HandshakeAuthenticationError):
        authenticated_handshake(mode, use_socket=use_socket, tamper_target=target, strict=True)
    result = authenticated_handshake(mode, use_socket=use_socket, tamper_target=target)
    assert not result["success"] and result["tamper_applied"]
    assert any(s["status"] == "failed" for s in result["steps_log"])


def test_ciphertext_target_is_not_applicable_in_classical_mode():
    result = authenticated_handshake("CLASSICAL", use_socket=False, tamper_target="ciphertext")
    assert result["success"] and not result["tamper_applied"]
