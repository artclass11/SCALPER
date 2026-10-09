"""Optional authenticated encryption helpers for future secret-vault integrations."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class SecretConfigurationError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = os.getenv("SCALPER_ENCRYPTION_KEY", "").strip()
    if not key:
        raise SecretConfigurationError("SCALPER_ENCRYPTION_KEY is required; store it in a secret manager.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise SecretConfigurationError("SCALPER_ENCRYPTION_KEY is invalid.") from exc


def encrypt_secret(secret: str) -> str:
    if not secret:
        raise ValueError("Secret must not be empty")
    return _fernet().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeEncodeError) as exc:
        raise ValueError("Unable to decrypt secret with the configured key") from exc
