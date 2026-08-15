import hashlib
import os

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_hasher = PasswordHasher()
_AES_NONCE_SIZE = 12


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _aes_key() -> bytes:
    key = settings.nexus_data_key.encode("utf-8")
    if len(key) != 32:
        raise RuntimeError("NEXUS_DATA_KEY must be exactly 32 bytes")
    return key


def encrypt_bytes(plaintext: bytes) -> bytes:
    nonce = os.urandom(_AES_NONCE_SIZE)
    return nonce + AESGCM(_aes_key()).encrypt(nonce, plaintext, None)


def decrypt_bytes(blob: bytes) -> bytes:
    nonce, ciphertext = blob[:_AES_NONCE_SIZE], blob[_AES_NONCE_SIZE:]
    return AESGCM(_aes_key()).decrypt(nonce, ciphertext, None)
