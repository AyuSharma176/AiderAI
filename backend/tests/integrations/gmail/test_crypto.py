import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.integrations.gmail.crypto import TokenCipher


def test_token_cipher_round_trip_and_key_rotation() -> None:
    old = Fernet.generate_key().decode()
    current = Fernet.generate_key().decode()
    old_cipher = TokenCipher([old]).encrypt("refresh-secret")

    cipher = TokenCipher([current, old])

    assert cipher.decrypt(old_cipher) == "refresh-secret"
    assert cipher.encrypt("refresh-secret").startswith("v1:")


def test_token_cipher_rejects_unknown_version() -> None:
    cipher = TokenCipher([Fernet.generate_key().decode()])

    with pytest.raises(InvalidToken, match="Unsupported token version"):
        cipher.decrypt("v2:not-a-token")


def test_token_cipher_requires_a_key() -> None:
    with pytest.raises(ValueError, match="At least one"):
        TokenCipher([])
