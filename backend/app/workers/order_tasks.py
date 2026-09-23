import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Protocol
from uuid import UUID

import httpx
import structlog
from sqlalchemy import or_, select
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.integrations.gmail.client import (
    GmailAuthenticationError,
    GmailClient,
    GmailRateLimited,
    GmailUnavailableError,
)
from app.integrations.gmail.crypto import TokenCipher
from app.integrations.gmail.oauth import (
    GoogleOAuthClient,
    OAuthConsentDenied,
    OAuthProviderUnavailable,
)
from app.models import EmailConnection, EmailConnectionStatus
from app.models.base import utc_now
from app.orders.parsers import PARSER_REGISTRY
from app.services.order_sync import OrderSynchronizer, PostgreSQLSyncLock
from app.workers.celery_app import celery_app


class SyncRunner(Protocol):
    async def sync(self, connection_id: str, mode: str) -> None: ...
    async def dispose(self) -> None: ...


def process_sync(
    connection_id: str,
    mode: str,
    runner_factory: Callable[[], SyncRunner],
) -> None:
    async def execute() -> None:
        runner = runner_factory()
        try:
            await runner.sync(connection_id, mode)
        finally:
            await runner.dispose()

    asyncio.run(execute())


def is_transient_sync_error(exc: Exception) -> bool:
    return isinstance(
        exc,
        (
            GmailRateLimited,
            GmailUnavailableError,
            OAuthProviderUnavailable,
            OperationalError,
            DBAPIError,
        ),
    )


class ConfiguredSyncRunner:
    def __init__(self) -> None:
        settings = get_settings()
        keys = [item.get_secret_value() for item in settings.gmail_token_encryption_keys]
        if not keys:
            raise ValueError("Gmail token encryption is not configured")
        if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
            raise ValueError("Google OAuth is not configured")
        if not settings.gmail_message_id_pepper:
            raise ValueError("Gmail message ID pepper is not configured")
        self.settings = settings
        self.engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.http = httpx.AsyncClient()
        self.cipher = TokenCipher(keys)
        self.oauth = GoogleOAuthClient(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret.get_secret_value(),
            redirect_uri=settings.google_oauth_redirect_uri,
            http_client=self.http,
            authorization_endpoint=settings.google_oauth_authorization_endpoint,
            token_endpoint=settings.google_oauth_token_endpoint,
            revoke_endpoint=settings.google_oauth_revoke_endpoint,
            gmail_api_root=settings.gmail_api_root,
        )

    async def sync(self, connection_id: str, mode: str) -> None:
        connection_uuid = UUID(connection_id)

        async def access_token() -> str:
            async with self.sessions() as session:
                connection = await session.get(EmailConnection, connection_uuid)
                if connection is None:
                    raise ValueError("Gmail connection does not exist")
                refresh_token = self.cipher.decrypt(connection.encrypted_refresh_token)
            try:
                return await self.oauth.refresh_access_token(refresh_token)
            except OAuthConsentDenied as exc:
                raise GmailAuthenticationError("Gmail authorization must be renewed") from exc

        gmail = GmailClient(
            http_client=self.http,
            access_token_provider=access_token,
            api_root=self.settings.gmail_api_root,
        )
        synchronizer = OrderSynchronizer(
            self.sessions,
            gmail,
            PARSER_REGISTRY,
            self.cipher,
            self.settings,
            PostgreSQLSyncLock(self.engine),
            message_id_pepper=self.settings.gmail_message_id_pepper.get_secret_value(),
        )
        await synchronizer.sync(connection_uuid, mode=mode)  # type: ignore[arg-type]

    async def dispose(self) -> None:
        await self.http.aclose()
        await self.engine.dispose()


@celery_app.task(bind=True, max_retries=4, name="orders.sync")
def sync_order(self, connection_id: str, mode: str = "auto") -> None:
    logger = structlog.get_logger()
    try:
        process_sync(connection_id, mode, ConfiguredSyncRunner)
    except Exception as exc:
        logger.exception(
            "order_sync_failed",
            connection_id=connection_id,
            attempt=self.request.retries,
            transient=is_transient_sync_error(exc),
        )
        if is_transient_sync_error(exc) and self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=min(300, 2 ** (self.request.retries + 2)),
            ) from exc
        raise


async def _due_connection_ids() -> list[str]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cutoff = utc_now() - timedelta(minutes=settings.gmail_sync_interval_minutes)
    try:
        async with sessions() as session:
            ids = await session.scalars(
                select(EmailConnection.id).where(
                    EmailConnection.status == EmailConnectionStatus.CONNECTED,
                    or_(
                        EmailConnection.last_sync_completed_at.is_(None),
                        EmailConnection.last_sync_completed_at <= cutoff,
                    ),
                )
            )
            return [str(value) for value in ids]
    finally:
        await engine.dispose()


@celery_app.task(name="orders.sync_due")
def sync_due_orders() -> int:
    connection_ids = asyncio.run(_due_connection_ids())
    for connection_id in connection_ids:
        sync_order.delay(connection_id)
    return len(connection_ids)
