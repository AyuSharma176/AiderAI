from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.auth import RegisterRequest


class EmailExistsError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


async def register_user(session: AsyncSession, request: RegisterRequest) -> User:
    if await session.scalar(select(User).where(User.email == request.email)) is not None:
        raise EmailExistsError
    user = User(
        email=request.email,
        name=request.name.strip(),
        password_hash=hash_password(request.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    return user

