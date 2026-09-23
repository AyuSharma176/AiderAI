from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    encoded = hash_password("Stronger123!")

    assert encoded != "Stronger123!"
    assert verify_password("Stronger123!", encoded)
    assert not verify_password("wrong-password", encoded)


def test_access_token_contains_required_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-at-least-thirty-two-bytes")
    user_id = uuid4()

    claims = decode_access_token(create_access_token(user_id))

    assert claims.sub == user_id
    assert claims.type == "access"
    assert claims.iat < claims.exp


def test_expired_and_forged_tokens_share_safe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-at-least-thirty-two-bytes")
    expired = create_access_token(uuid4(), expires_delta=timedelta(seconds=-1))

    with pytest.raises(InvalidTokenError, match="Invalid access token"):
        decode_access_token(expired)
    with pytest.raises(InvalidTokenError, match="Invalid access token"):
        decode_access_token(f"{expired}forged")
