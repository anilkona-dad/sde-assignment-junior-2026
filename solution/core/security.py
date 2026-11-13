
import hashlib
import hmac
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_encryption_key() -> bytes:
    """
    Read a 256-bit AES encryption key from the environment.
    Expected format: 64 hexadecimal characters.
    """
    value = os.environ.get("PII_ENCRYPTION_KEY", "").strip()

    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise RuntimeError(
            "PII_ENCRYPTION_KEY must contain exactly 64 hex characters."
        )

    return bytes.fromhex(value)


def _get_hmac_key() -> bytes:
    """
    Read a separate secret key for phone fingerprints.
    The key must contain at least 32 UTF-8 bytes.
    """
    value = os.environ.get("PHONE_HMAC_KEY", "").strip()

    if len(value.encode("utf-8")) < 32:
        raise RuntimeError(
            "PHONE_HMAC_KEY must contain at least 32 characters."
        )

    return value.encode("utf-8")


def encrypt_text(value: str) -> bytes:
    """Encrypt UTF-8 text using AES-256-GCM."""
    if not isinstance(value, str):
        raise TypeError("encrypt_text expects a string")

    key = _get_encryption_key()
    nonce = os.urandom(12)

    encrypted = AESGCM(key).encrypt(
        nonce,
        value.encode("utf-8"),
        None,
    )

    # Store the nonce alongside the authenticated ciphertext.
    return nonce + encrypted


def decrypt_text(ciphertext: bytes) -> str:
    """Decrypt data produced by encrypt_text."""
    if not isinstance(ciphertext, bytes) or len(ciphertext) < 29:
        raise ValueError("Invalid encrypted payload")

    key = _get_encryption_key()
    nonce = ciphertext[:12]
    encrypted = ciphertext[12:]

    return AESGCM(key).decrypt(
        nonce,
        encrypted,
        None,
    ).decode("utf-8")


def phone_fingerprint(canonical_phone: str) -> str:
    """
    Create a deterministic keyed SHA-256 fingerprint.

    Input must already be normalized, e.g. +919876543210.
    """
    if not isinstance(canonical_phone, str) or not canonical_phone:
        raise ValueError("A canonical phone number is required")

    key = _get_hmac_key()

    return hmac.new(
        key,
        canonical_phone.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
