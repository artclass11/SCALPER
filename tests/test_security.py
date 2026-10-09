import pytest
from cryptography.fernet import Fernet

from scalper.security import SecretConfigurationError, decrypt_secret, encrypt_secret


def test_secret_encryption_round_trip(monkeypatch):
    monkeypatch.setenv("SCALPER_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    encrypted = encrypt_secret("fake-test-secret")
    assert encrypted != "fake-test-secret"
    assert decrypt_secret(encrypted) == "fake-test-secret"


def test_secret_encryption_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("SCALPER_ENCRYPTION_KEY", raising=False)
    with pytest.raises(SecretConfigurationError):
        encrypt_secret("secret")
