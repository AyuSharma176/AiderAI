from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

password_hasher = PasswordHash.recommended()


class InvalidTokenError(ValueError):
    pass


class TokenClaims(BaseModel):
    sub: UUID
    iat: datetime
    exp: datetime
    type: str


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hasher.verify(password, encoded)


def create_access_token(user_id: UUID, *, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    issued_at = datetime.now(UTC)
    expires_at = issued_at + (expires_delta or timedelta(minutes=settings.jwt_access_token_minutes))
    return jwt.encode(
        {"sub": str(user_id), "iat": issued_at, "exp": expires_at, "type": "access"},
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> TokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "iat", "exp", "type"]},
        )
        claims = TokenClaims.model_validate(payload)
        if claims.type != "access":
            raise InvalidTokenError("Invalid access token")
        return claims
    except (jwt.PyJWTError, ValidationError, ValueError) as exc:
        raise InvalidTokenError("Invalid access token") from exc
