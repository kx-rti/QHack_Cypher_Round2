"""ML-KEM-768 (FIPS 203) and ML-DSA-65 (FIPS 204): liboqs if available, else pure-Python fallback."""
BACKEND = None
IS_FALLBACK = False

try:
    # liboqs-python can raise SystemExit from import when the C library cannot be built.
    import oqs

    _kems = oqs.get_enabled_kem_mechanisms()
    _sigs = oqs.get_enabled_sig_mechanisms()
    KEM_NAME = next(n for n in ("ML-KEM-768", "Kyber768") if n in _kems)
    SIG_NAME = next(n for n in ("ML-DSA-65", "Dilithium3") if n in _sigs)
    BACKEND = f"liboqs ({KEM_NAME}, {SIG_NAME})"
except (Exception, SystemExit):
    from dilithium_py.ml_dsa import ML_DSA_65
    from kyber_py.ml_kem import ML_KEM_768

    IS_FALLBACK = True
    BACKEND = "kyber-py / dilithium-py (educational pure-Python fallback, not constant-time hardened)"

KEM_PK_BYTES, KEM_CT_BYTES, KEM_SECRET_BYTES = 1184, 1088, 32
SIG_PK_BYTES, SIG_BYTES = 1952, 3309


def kem_keygen() -> tuple[bytes, bytes]:
    """Returns (public key, secret key)."""
    if IS_FALLBACK:
        return ML_KEM_768.keygen()
    with oqs.KeyEncapsulation(KEM_NAME) as server:
        pk = server.generate_keypair()
        return pk, server.export_secret_key()


def kem_encaps(pk: bytes) -> tuple[bytes, bytes]:
    """Returns (ciphertext, shared secret)."""
    if IS_FALLBACK:
        secret, ct = ML_KEM_768.encaps(pk)  # kyber-py returns (K, c)
        return ct, secret
    with oqs.KeyEncapsulation(KEM_NAME) as client:
        return client.encap_secret(pk)


def kem_decaps(sk: bytes, ct: bytes) -> bytes:
    if IS_FALLBACK:
        return ML_KEM_768.decaps(sk, ct)
    with oqs.KeyEncapsulation(KEM_NAME, secret_key=sk) as server:
        return server.decap_secret(ct)


def establish() -> tuple[bytes, int]:
    """Server publishes pk, client replies with ciphertext. Returns (secret, bytes on wire)."""
    pk, sk = kem_keygen()
    ct, client_secret = kem_encaps(pk)
    server_secret = kem_decaps(sk, ct)
    assert len(client_secret) == KEM_SECRET_BYTES
    assert len(pk) == KEM_PK_BYTES
    assert len(ct) == KEM_CT_BYTES
    assert client_secret == server_secret
    return client_secret, len(pk) + len(ct)


def generate_mldsa_keypair() -> tuple[bytes, bytes]:
    """Returns (secret key, public key), in the same order as generate_ed25519_keypair()."""
    if IS_FALLBACK:
        pk, sk = ML_DSA_65.keygen()
        return sk, pk
    with oqs.Signature(SIG_NAME) as signer:
        pk = signer.generate_keypair()
        return signer.export_secret_key(), pk


def sign_mldsa(sk: bytes, msg: bytes) -> bytes:
    if IS_FALLBACK:
        return ML_DSA_65.sign(sk, msg)
    with oqs.Signature(SIG_NAME, secret_key=sk) as signer:
        return signer.sign(msg)


def verify_mldsa(pk: bytes, msg: bytes, sig: bytes) -> bool:
    try:
        if IS_FALLBACK:
            return bool(ML_DSA_65.verify(pk, msg, sig))
        with oqs.Signature(SIG_NAME) as verifier:
            return bool(verifier.verify(msg, sig, pk))
    except Exception:  # malformed input from the wire counts as a failed verification
        return False
