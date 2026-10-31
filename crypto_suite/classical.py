"""X25519 key exchange (64 B on the wire) and Ed25519 signatures (32 B pk, 64 B sig)."""
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _raw(pub) -> bytes:
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw)


def server_start():
    priv = X25519PrivateKey.generate()
    return priv, _raw(priv.public_key())


def client_respond(server_pub: bytes):
    priv = X25519PrivateKey.generate()
    secret = priv.exchange(X25519PublicKey.from_public_bytes(server_pub))
    return secret, _raw(priv.public_key())


def server_finish(priv, client_pub: bytes) -> bytes:
    return priv.exchange(X25519PublicKey.from_public_bytes(client_pub))


def establish() -> tuple[bytes, int]:
    s_priv, s_pub = server_start()
    c_secret, c_pub = client_respond(s_pub)
    s_secret = server_finish(s_priv, c_pub)
    assert c_secret == s_secret and len(c_secret) == 32
    return c_secret, len(s_pub) + len(c_pub)


def generate_ed25519_keypair():
    sk = Ed25519PrivateKey.generate()
    return sk, _raw(sk.public_key())


def sign_ed25519(sk, msg: bytes) -> bytes:
    return sk.sign(msg)


def verify_ed25519(pk_bytes: bytes, msg: bytes, sig: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(pk_bytes).verify(sig, msg)
        return True
    except (InvalidSignature, ValueError):
        return False
