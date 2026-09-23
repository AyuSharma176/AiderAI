import asyncio

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session_factory
from app.models import Order, User


password_hash = PasswordHash.recommended()


async def seed_demo_data(session: AsyncSession, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if settings.app_env != "development":
        return

    user = await session.scalar(select(User).where(User.email == "demo@supportai.local"))
    if user is None:
        user = User(
            email="demo@supportai.local",
            name="Demo User",
            password_hash=password_hash.hash("DemoPass123!"),
        )
        session.add(user)
        await session.flush()

    existing = set(
        await session.scalars(
            select(Order.order_number).where(
                Order.order_number.in_(["ORD-1001", "ORD-1002"])
            )
        )
    )
    if "ORD-1001" not in existing:
        session.add(
            Order(
                order_number="ORD-1001",
                user_id=user.id,
                status="shipped",
                tracking_number="TRACK-1001",
            )
        )
    if "ORD-1002" not in existing:
        session.add(
            Order(order_number="ORD-1002", user_id=user.id, status="processing")
        )
    await session.commit()


async def main() -> None:
    async with get_session_factory()() as session:
        await seed_demo_data(session)


if __name__ == "__main__":
    asyncio.run(main())

