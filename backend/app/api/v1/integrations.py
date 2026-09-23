import secrets
from collections.abc import AsyncIterator, Callable
from typing import Annotated

import httpx
from celery.exceptions import CeleryError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.integrations.gmail.crypto import TokenCipher
from app.integrations.gmail.oauth import (
    GMAIL_READONLY_SCOPE,
    GoogleOAuthClient,
    InvalidOAuthState,
    OAuthStateStore,
)
from app.models import (
    CommerceOrder,
    EmailConnection,
    EmailConnectionStatus,
    User,
)
from app.schemas.integration import GmailAuthorizationResponse, GmailConnectionResponse
from app.services.rate_limit import enforce_integration_sync_rate_limit, get_redis_client
from app.workers.order_tasks import sync_order

router = APIRouter(prefix="/api/v1/integrations/gmail", tags=["integrations"])
OAUTH_NONCE_COOKIE = "gmail_oauth_nonce"


def _require_enabled(settings: Settings) -> None:
    if not settings.gmail_integration_enabled:
        raise HTTPException(404, detail={"code": "not_found", "message": "Not found"})


def get_oauth_state_store(
    redis: Annotated[object, Depends(get_redis_client)],
) -> OAuthStateStore:
    return OAuthStateStore(redis)


async def get_google_oauth_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[GoogleOAuthClient]:
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(503, detail="Google OAuth is not configured")
    client = httpx.AsyncClient()
    try:
        yield GoogleOAuthClient(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret.get_secret_value(),
            redirect_uri=settings.google_oauth_redirect_uri,
            http_client=client,
        )
    finally:
        await client.aclose()


def get_token_cipher(settings: Annotated[Settings, Depends(get_settings)]) -> TokenCipher:
    keys = [item.get_secret_value() for item in settings.gmail_token_encryption_keys]
    if not keys:
        raise HTTPException(503, detail="Gmail token encryption is not configured")
    return TokenCipher(keys)


def get_gmail_dispatcher() -> Callable[[str, str], None]:
    return lambda connection_id, mode: sync_order.delay(connection_id, mode)


async def _owned_connection(
    session: AsyncSession, user_id
) -> EmailConnection | None:
    return await session.scalar(
        select(EmailConnection).where(
            EmailConnection.user_id == user_id,
            EmailConnection.provider == "gmail",
        )
    )


@router.get("", response_model=GmailConnectionResponse)
async def gmail_status(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GmailConnectionResponse:
    _require_enabled(settings)
    connection = await _owned_connection(session, user.id)
    if connection is None:
        return GmailConnectionResponse(status=EmailConnectionStatus.DISCONNECTED)
    counts = dict(
        (
            await session.execute(
                select(CommerceOrder.marketplace, func.count(CommerceOrder.id))
                .where(CommerceOrder.user_id == user.id)
                .group_by(CommerceOrder.marketplace)
            )
        ).all()
    )
    return GmailConnectionResponse(
        status=connection.status,
        email_address=connection.email_address,
        last_sync_completed_at=connection.last_sync_completed_at,
        imported_order_count=sum(counts.values()),
        marketplace_counts=counts,
        reconnect_required=connection.status == EmailConnectionStatus.RECONNECT_REQUIRED,
    )


@router.post("/authorize", response_model=GmailAuthorizationResponse)
async def authorize_gmail(
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    state_store: Annotated[OAuthStateStore, Depends(get_oauth_state_store)],
    oauth: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
) -> GmailAuthorizationResponse:
    _require_enabled(settings)
    nonce = secrets.token_urlsafe(32)
    state = await state_store.issue(user.id, nonce)
    challenge = await state_store.get_code_challenge(state)
    response.set_cookie(
        OAUTH_NONCE_COOKIE,
        nonce,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        max_age=600,
    )
    return GmailAuthorizationResponse(
        authorization_url=oauth.authorization_url(state, challenge)
    )


@router.get("/callback")
async def gmail_callback(
    request: Request,
    code: str,
    state: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    state_store: Annotated[OAuthStateStore, Depends(get_oauth_state_store)],
    oauth: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
    cipher: Annotated[TokenCipher, Depends(get_token_cipher)],
    dispatch: Annotated[Callable[[str, str], None], Depends(get_gmail_dispatcher)],
):
    _require_enabled(settings)
    nonce = request.cookies.get(OAUTH_NONCE_COOKIE)
    if not nonce:
        raise HTTPException(400, detail="Authorization state is invalid or expired")
    try:
        oauth_state = await state_store.consume(state, nonce)
    except InvalidOAuthState as exc:
        raise HTTPException(400, detail="Authorization state is invalid or expired") from exc
    tokens = await oauth.exchange_code(code, oauth_state.code_verifier)
    if GMAIL_READONLY_SCOPE not in tokens.scope.split():
        raise HTTPException(400, detail="Required Gmail permission was not granted")
    profile = await oauth.get_profile(tokens.access_token)
    user = await session.get(User, oauth_state.user_id)
    if user is None:
        raise HTTPException(404, detail="Account no longer exists")
    connection = await _owned_connection(session, user.id)
    if connection is None:
        if not tokens.refresh_token:
            raise HTTPException(400, detail="Google did not provide an offline token")
        connection = EmailConnection(
            user_id=user.id,
            provider="gmail",
            provider_account_id=profile["emailAddress"],
            email_address=profile["emailAddress"],
            encrypted_refresh_token=cipher.encrypt(tokens.refresh_token),
            granted_scopes=tokens.scope,
            status=EmailConnectionStatus.CONNECTED,
            last_history_id=profile["historyId"],
        )
        session.add(connection)
    else:
        connection.provider_account_id = profile["emailAddress"]
        connection.email_address = profile["emailAddress"]
        connection.granted_scopes = tokens.scope
        connection.status = EmailConnectionStatus.CONNECTED
        if tokens.refresh_token:
            connection.encrypted_refresh_token = cipher.encrypt(tokens.refresh_token)
    await session.commit()
    await session.refresh(connection)
    try:
        dispatch(str(connection.id), "full")
    except (CeleryError, OSError):
        connection.last_sync_error_code = "dispatch_failed"
        await session.commit()
    response = RedirectResponse(f"{settings.frontend_url.rstrip('/')}/knowledge?gmail=connected", 303)
    response.delete_cookie(OAUTH_NONCE_COOKIE)
    return response


@router.post("/sync", status_code=202)
async def sync_gmail(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    dispatch: Annotated[Callable[[str, str], None], Depends(get_gmail_dispatcher)],
    _rate_limit: Annotated[None, Depends(enforce_integration_sync_rate_limit)],
) -> dict[str, str]:
    _require_enabled(settings)
    connection = await _owned_connection(session, user.id)
    if connection is None:
        raise HTTPException(404, detail="Gmail is not connected")
    try:
        dispatch(str(connection.id), "auto")
    except (CeleryError, OSError) as exc:
        connection.last_sync_error_code = "dispatch_failed"
        await session.commit()
        raise HTTPException(503, detail="Sync could not be queued") from exc
    return {"status": "queued"}


@router.delete("", status_code=204)
async def disconnect_gmail(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    oauth: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
    cipher: Annotated[TokenCipher, Depends(get_token_cipher)],
) -> Response:
    _require_enabled(settings)
    connection = await _owned_connection(session, user.id)
    if connection is not None and connection.status != EmailConnectionStatus.DISCONNECTED:
        await oauth.revoke(cipher.decrypt(connection.encrypted_refresh_token))
        connection.encrypted_refresh_token = ""
        connection.status = EmailConnectionStatus.DISCONNECTED
        await session.commit()
    return Response(status_code=204)


@router.delete("/orders", status_code=204)
async def delete_imported_orders(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    _require_enabled(settings)
    await session.execute(delete(CommerceOrder).where(CommerceOrder.user_id == user.id))
    await session.commit()
    return Response(status_code=204)
