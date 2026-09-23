import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models import Base, Order, User
from app.scripts.seed import seed_demo_data


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret")
    settings = Settings(_env_file=None)

    await seed_demo_data(db_session, settings)
    await seed_demo_data(db_session, settings)

    users = (await db_session.scalars(select(User))).all()
    orders = (await db_session.scalars(select(Order))).all()
    assert len(users) == 1
    assert users[0].email == "demo@supportai.local"
    assert {order.order_number for order in orders} == {"ORD-1001", "ORD-1002"}


@pytest.mark.asyncio
async def test_seed_skips_non_development_environment(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret")

    await seed_demo_data(db_session, Settings(_env_file=None))

    assert (await db_session.scalars(select(User))).all() == []
