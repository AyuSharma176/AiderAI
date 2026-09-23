from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("Enter a valid email address")
    return normalized


class RegisterRequest(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=128)

    _normalize_email = field_validator("email")(normalize_email)


class LoginRequest(BaseModel):
    email: str
    password: str

    _normalize_email = field_validator("email")(normalize_email)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

