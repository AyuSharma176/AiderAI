from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.auth import (
    EmailExistsError,
    InvalidCredentialsError,
    authenticate_user,
    register_user,
)


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def auth_response(user: User) -> AuthResponse:
    return AuthResponse(access_token=create_access_token(user.id), user=UserResponse.model_validate(user))


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    request: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return auth_response(await register_user(session, request))
    except EmailExistsError:
        return JSONResponse(
            status_code=409,
            content={
                "code": "email_exists",
                "message": "An account with this email already exists",
            },
        )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return auth_response(await authenticate_user(session, request.email, request.password))
    except InvalidCredentialsError:
        return JSONResponse(
            status_code=401,
            content={
                "code": "invalid_credentials",
                "message": "Invalid email or password",
            },
        )


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user

