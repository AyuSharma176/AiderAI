# Gmail Order Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a SupportAI user connect Gmail, import 12 months of Amazon and Flipkart order emails into a private normalized order store, browse those orders, and enquire about them through chat.

**Architecture:** Add a Gmail integration boundary for OAuth and message transport, deterministic marketplace parser adapters, and an idempotent synchronization service invoked by Celery. Persist encrypted connection credentials and normalized orders in PostgreSQL; expose authenticated connection/order APIs and allow-listed order tools; add Connected accounts and My Orders React surfaces.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Redis, Celery, HTTPX, cryptography/Fernet, Pydantic 2, React 19, TypeScript, TanStack Query, Vitest, Pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-24-gmail-order-integration-design.md`

## Global Constraints

- Support exactly one Gmail connection per SupportAI user in this release.
- Request only `https://www.googleapis.com/auth/gmail.readonly`; never collect Amazon, Flipkart, or Google passwords.
- Import at most the preceding 12 months and persist normalized fields, not complete email bodies, MIME payloads, or attachments.
- Keep all order data private to the authenticated SupportAI user at the database query boundary.
- Use deterministic Amazon and Flipkart adapters; no LLM extraction in this release.
- The feature is read-only: no purchases, cancellations, returns, refunds, or email modifications.
- Encrypt refresh tokens with a versioned application key and never expose tokens to the frontend or logs.
- Keep provider URLs HTTPS-only and restricted to allow-listed Amazon and Flipkart hosts.
- All schema changes use Alembic revision `0003`; no mutation of earlier migration files.
- `.env` remains ignored; `.env.example` documents every new variable without real credentials.
- Public rollout remains feature-flagged until Google restricted-scope verification and applicable security assessment requirements are complete.

## Review Focus

- A replayed, expired, or different-browser OAuth callback must fail without exchanging its code; Task 2 pins this with state-consumption tests.
- Oversized, malformed, multipart, or script-bearing email content must be bounded and sanitized before parsing; Task 4 pins this with hostile message fixtures.
- Concurrent sync requests and an expired Gmail history cursor must not duplicate orders; Task 6 pins locking, idempotency, and full-reconciliation fallback.
- Marketplace template drift that removes an order identifier must skip the message rather than create a partial order; Task 5 pins this for both adapters.
- A guessed order UUID or marketplace order number belonging to another user must return no data; Tasks 9 and 10 pin API and tool ownership.

---

## File Structure

### Backend files to create

- `backend/app/integrations/__init__.py`: integration package marker.
- `backend/app/integrations/gmail/__init__.py`: Gmail package marker.
- `backend/app/integrations/gmail/types.py`: typed OAuth tokens, Gmail messages, pages, and history results.
- `backend/app/integrations/gmail/oauth.py`: state issuance/consumption and Google authorization/token exchange.
- `backend/app/integrations/gmail/client.py`: narrow async Gmail REST transport.
- `backend/app/integrations/gmail/crypto.py`: versioned refresh-token authenticated encryption.
- `backend/app/orders/__init__.py`: commerce-order package marker.
- `backend/app/orders/types.py`: normalized message and order-observation types.
- `backend/app/orders/parsers/base.py`: parser protocol, registry, content normalization, URL validation.
- `backend/app/orders/parsers/amazon.py`: Amazon sender matching and deterministic extraction.
- `backend/app/orders/parsers/flipkart.py`: Flipkart sender matching and deterministic extraction.
- `backend/app/services/order_sync.py`: full/incremental orchestration, locking, idempotent persistence, lifecycle state.
- `backend/app/services/commerce_orders.py`: private list/detail queries shared by API and tools.
- `backend/app/workers/order_tasks.py`: Celery sync task with task-local async engine lifecycle.
- `backend/app/models/email_connection.py`: connection/status/cursor entity.
- `backend/app/models/commerce_order.py`: normalized order, item, and source-event entities.
- `backend/app/schemas/integration.py`: connection and OAuth API contracts.
- `backend/app/schemas/commerce_order.py`: order list/detail contracts.
- `backend/app/api/v1/integrations.py`: Gmail status/authorize/callback/sync/disconnect/delete endpoints.
- `backend/app/api/v1/orders.py`: authenticated order list/detail endpoints.
- `backend/alembic/versions/0003_gmail_commerce_orders.py`: explicit connection/order schema.

### Frontend files to create

- `frontend/src/integrations/types.ts`: Gmail connection DTOs.
- `frontend/src/integrations/useGmailIntegration.ts`: status and mutations.
- `frontend/src/integrations/ShoppingAccountsPanel.tsx`: Gmail connection card and controls.
- `frontend/src/integrations/ShoppingAccountsPanel.test.tsx`: connection-state tests.
- `frontend/src/orders/types.ts`: order DTOs and filters.
- `frontend/src/orders/useOrders.ts`: private order queries.
- `frontend/src/orders/OrdersPage.tsx`: searchable/filterable order list.
- `frontend/src/orders/OrderDetailPage.tsx`: order timeline and safe marketplace link.
- `frontend/src/orders/OrdersPage.test.tsx`: list, filters, freshness, and ownership-safe error UI.

### Existing files to modify

- `backend/pyproject.toml`: explicit HTTPX and cryptography runtime dependencies.
- `backend/app/core/config.py`: Gmail feature, OAuth, encryption, sync, and sender settings.
- `backend/app/models/__init__.py`, `backend/app/models/user.py`: model exports and relationships.
- `backend/app/workers/celery_app.py`: include order task module and beat schedule.
- `backend/app/main.py`: include integrations and orders routers.
- `backend/app/services/rate_limit.py`: user-scoped integration-sync limiter.
- `backend/app/tools/schemas.py`, `backend/app/tools/support.py`, `backend/app/tools/registry.py`: order enquiry tools.
- `backend/app/ai/types.py`: explicit SDK-compatible tool selection fields.
- `backend/app/api/v1/chat.py`: existing registry automatically receives new tool handlers.
- `frontend/src/documents/DocumentsPage.tsx`: render Connected accounts alongside documents.
- `frontend/src/App.tsx`, `frontend/src/layout/Sidebar.tsx`: My Orders routes/navigation.
- `frontend/src/chat/MessageBubble.tsx`: optional normalized order-result card rendering.
- `.env.example`, `docker-compose.yml`, `README.md`: configuration, worker inclusion, setup, privacy, and verification notes.

---

### Task 1: Gmail Configuration and Token Encryption

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/integrations/__init__.py`
- Create: `backend/app/integrations/gmail/__init__.py`
- Create: `backend/app/integrations/gmail/crypto.py`
- Test: `backend/tests/integrations/gmail/test_crypto.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `TokenCipher.encrypt(plaintext: str) -> str`
- Produces: `TokenCipher.decrypt(ciphertext: str) -> str`
- Produces settings: `gmail_integration_enabled`, `google_oauth_client_id`, `google_oauth_client_secret`, `google_oauth_redirect_uri`, `gmail_token_encryption_keys`, `gmail_import_months`, `gmail_sync_interval_minutes`, `gmail_max_message_bytes`

- [ ] **Step 1: Write failing encryption and production-configuration tests**

```python
def test_token_cipher_round_trip_and_key_rotation() -> None:
    old = Fernet.generate_key().decode()
    current = Fernet.generate_key().decode()
    old_cipher = TokenCipher([old]).encrypt("refresh-secret")
    cipher = TokenCipher([current, old])
    assert cipher.decrypt(old_cipher) == "refresh-secret"
    assert cipher.encrypt("refresh-secret").startswith("v1:")


def test_enabled_production_gmail_requires_oauth_and_encryption(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("GMAIL_INTEGRATION_ENABLED", "true")
    with pytest.raises(ValidationError, match="Google OAuth"):
        Settings(JWT_SECRET="x" * 32, GEMINI_API_KEY="key")
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/integrations/gmail/test_crypto.py tests/test_health.py -q`

Expected: FAIL because `TokenCipher` and Gmail settings do not exist.

- [ ] **Step 3: Add explicit runtime dependencies and settings**

Add `httpx>=0.28,<1` and `cryptography>=46,<51` to `[project].dependencies`. Add settings with safe disabled defaults:

```python
gmail_integration_enabled: bool = False
google_oauth_client_id: str | None = None
google_oauth_client_secret: SecretStr | None = None
google_oauth_redirect_uri: str = "http://localhost:8000/api/v1/integrations/gmail/callback"
gmail_token_encryption_keys: list[SecretStr] = []
gmail_import_months: int = 12
gmail_sync_interval_minutes: int = 30
gmail_max_message_bytes: int = 1_000_000
```

Extend the settings validator so enabled production mode requires client ID, client secret, an HTTPS redirect URI, and at least one valid Fernet key.

- [ ] **Step 4: Implement versioned authenticated encryption**

```python
class TokenCipher:
    def __init__(self, keys: Sequence[str]) -> None:
        if not keys:
            raise ValueError("At least one token encryption key is required")
        self._fernets = [Fernet(key.encode()) for key in keys]

    def encrypt(self, plaintext: str) -> str:
        return "v1:" + self._fernets[0].encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        version, payload = ciphertext.split(":", 1)
        if version != "v1":
            raise InvalidToken("Unsupported token version")
        for fernet in self._fernets:
            try:
                return fernet.decrypt(payload.encode()).decode()
            except InvalidToken:
                continue
        raise InvalidToken("Token cannot be decrypted")
```

- [ ] **Step 5: Run focused tests and quality checks**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/integrations/gmail/test_crypto.py tests/test_health.py -q && ..\.venv\Scripts\python.exe -m ruff check app/integrations app/core/config.py tests/integrations/gmail/test_crypto.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app/core/config.py backend/app/integrations backend/tests/integrations/gmail/test_crypto.py backend/tests/test_health.py
git commit -m "feat: add secure Gmail integration configuration"
```

---

### Task 2: OAuth State and Google Authorization Flow

**Files:**
- Create: `backend/app/integrations/gmail/types.py`
- Create: `backend/app/integrations/gmail/oauth.py`
- Test: `backend/tests/integrations/gmail/test_oauth.py`

**Interfaces:**
- Consumes: `TokenCipher` only after token exchange; OAuth itself never persists tokens.
- Produces: `GoogleOAuthTokens(access_token: str, refresh_token: str | None, expires_in: int, scope: str)`
- Produces: `OAuthStateStore.issue(user_id: UUID, browser_nonce: str) -> Awaitable[str]`
- Produces: `OAuthStateStore.consume(state: str, browser_nonce: str) -> Awaitable[OAuthState]`; the returned server-side state is the source of truth for the bound user ID
- Produces: `GoogleOAuthClient.authorization_url(state: str, code_challenge: str) -> str`
- Produces: `GoogleOAuthClient.exchange_code(code: str, code_verifier: str) -> Awaitable[GoogleOAuthTokens]`
- Produces: `GoogleOAuthClient.revoke(token: str) -> Awaitable[None]`

- [ ] **Step 1: Write failing state and URL tests**

```python
@pytest.mark.asyncio
async def test_state_is_single_use_bound_to_user_and_browser() -> None:
    store = OAuthStateStore(FakeRedis(), ttl_seconds=600)
    state = await store.issue(USER_A, "browser-a")
    consumed = await store.consume(state, "browser-a")
    assert consumed.user_id == USER_A
    with pytest.raises(InvalidOAuthState):
        await store.consume(state, "browser-a")


@pytest.mark.asyncio
async def test_state_rejects_a_different_browser() -> None:
    store = OAuthStateStore(FakeRedis(), ttl_seconds=600)
    state = await store.issue(USER_A, "browser-a")
    with pytest.raises(InvalidOAuthState):
        await store.consume(state, "browser-b")


def test_authorization_url_has_exact_readonly_scope_and_pkce() -> None:
    url = client.authorization_url("state-1", "challenge-1")
    query = parse_qs(urlsplit(url).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert query["access_type"] == ["offline"]
    assert query["state"] == ["state-1"]
    assert query["code_challenge_method"] == ["S256"]
```

- [ ] **Step 2: Run tests and verify the missing-module failure**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/integrations/gmail/test_oauth.py -q`

Expected: FAIL importing `app.integrations.gmail.oauth`.

- [ ] **Step 3: Implement atomic state issue/consume**

Store only a SHA-256 digest of the random state in Redis under `oauth:gmail:{digest}` with JSON containing `user_id`, a digest of `browser_nonce`, and the PKCE verifier. Consume with a Lua script that gets and deletes the value atomically; validate using constant-time comparisons.

```python
STATE_TTL_SECONDS = 600

async def consume(self, state: str, browser_nonce: str) -> OAuthState:
    key = f"oauth:gmail:{sha256(state.encode()).hexdigest()}"
    payload = await self.redis.eval(GET_AND_DELETE_SCRIPT, 1, key)
    if payload is None:
        raise InvalidOAuthState("Authorization state is invalid or expired")
    parsed = OAuthState.model_validate_json(payload)
    if not compare_digest(parsed.browser_nonce_hash, self._digest(browser_nonce)):
        raise InvalidOAuthState("Authorization state is invalid or expired")
    return parsed
```

- [ ] **Step 4: Implement OAuth HTTP exchange and safe error mapping**

Use injected `httpx.AsyncClient`, fixed Google endpoints, exact timeouts, `raise_for_status`, and Pydantic validation. Map denied consent to `OAuthConsentDenied`, invalid/replayed state to `InvalidOAuthState`, and provider/network errors to `OAuthProviderUnavailable`; never include provider payloads in exception messages.

- [ ] **Step 5: Add tests for expired state, replay, foreign browser, denied consent, missing refresh token, timeout, and redaction**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/integrations/gmail/test_oauth.py -q`

Expected: PASS, including the Review Focus state cases.

- [ ] **Step 6: Commit**

```bash
git add backend/app/integrations/gmail/types.py backend/app/integrations/gmail/oauth.py backend/tests/integrations/gmail/test_oauth.py
git commit -m "feat: add hardened Gmail OAuth flow"
```

---

### Task 3: Connection and Commerce Order Persistence

**Files:**
- Create: `backend/app/models/email_connection.py`
- Create: `backend/app/models/commerce_order.py`
- Create: `backend/alembic/versions/0003_gmail_commerce_orders.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/user.py`
- Test: `backend/tests/test_commerce_models.py`

**Interfaces:**
- Produces: `EmailConnectionStatus` enum and `EmailConnection`
- Produces: `Marketplace`, `CommerceOrderStatus`, `CommerceOrder`, `CommerceOrderItem`, `OrderSourceEvent`
- Produces uniqueness on `(user_id, provider)`, `(user_id, marketplace, marketplace_order_id)`, and `(connection_id, provider_message_id_hash)`

- [ ] **Step 1: Write failing model tests**

```python
@pytest.mark.asyncio
async def test_same_marketplace_order_is_unique_per_user(session) -> None:
    session.add_all([
        CommerceOrder(user_id=USER_A, marketplace=Marketplace.AMAZON, marketplace_order_id="A-1", status=CommerceOrderStatus.PLACED),
        CommerceOrder(user_id=USER_B, marketplace=Marketplace.AMAZON, marketplace_order_id="A-1", status=CommerceOrderStatus.PLACED),
    ])
    await session.commit()


@pytest.mark.asyncio
async def test_duplicate_source_message_for_connection_is_rejected(session) -> None:
    # Persist the same opaque source-message hash twice for one connection.
    with pytest.raises(IntegrityError):
        await persist_duplicate_events(session)
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/test_commerce_models.py -q`

Expected: FAIL because commerce entities are undefined.

- [ ] **Step 3: Implement focused SQLAlchemy models**

Use explicit enums and relationships. Store monetary values as `Numeric(12, 2)`, currency as `String(3)`, encrypted token as `Text`, and provider IDs/hashes as bounded indexed strings. Add cascades from user to connection/orders and from order to items/events.

```python
class CommerceOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commerce_orders"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    marketplace: Mapped[Marketplace] = mapped_column(Enum(Marketplace, native_enum=False))
    marketplace_order_id: Mapped[str] = mapped_column(String(120))
    status: Mapped[CommerceOrderStatus] = mapped_column(Enum(CommerceOrderStatus, native_enum=False), index=True)
    __table_args__ = (UniqueConstraint("user_id", "marketplace", "marketplace_order_id", name="uq_commerce_order_owner_marketplace_id"),)
```

- [ ] **Step 4: Write explicit Alembic operations**

Create all tables, indexes, foreign keys, and uniqueness constraints with `op.create_table`/`op.create_index`; do not import mutable application metadata. Downgrade drops tables in dependency order.

- [ ] **Step 5: Verify SQLite models and PostgreSQL migration**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/test_commerce_models.py -q`

Run: `docker compose run --rm api alembic upgrade head`

Expected: tests PASS; PostgreSQL reports upgrade `0002 -> 0003`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models backend/alembic/versions/0003_gmail_commerce_orders.py backend/tests/test_commerce_models.py
git commit -m "feat: persist Gmail connections and commerce orders"
```

---

### Task 4: Gmail Message Transport and Safe Content Normalization

**Files:**
- Create: `backend/app/integrations/gmail/client.py`
- Create: `backend/app/orders/types.py`
- Create: `backend/app/orders/parsers/base.py`
- Test: `backend/tests/integrations/gmail/test_client.py`
- Test: `backend/tests/orders/test_message_normalizer.py`

**Interfaces:**
- Produces: `GmailClient.list_candidate_ids(after: datetime, page_token: str | None) -> Awaitable[GmailMessagePage]`
- Produces: `GmailClient.get_message(message_id: str) -> Awaitable[GmailRawMessage]`
- Produces: `GmailClient.list_history(start_history_id: str, page_token: str | None) -> Awaitable[GmailHistoryPage]`
- Produces: `normalize_message(raw: GmailRawMessage, max_bytes: int) -> CommerceEmail`
- Produces: `validate_marketplace_url(value: str, marketplace: Marketplace) -> str | None`

- [ ] **Step 1: Write failing Gmail transport contract tests**

```python
@pytest.mark.asyncio
async def test_candidate_query_is_bounded_to_senders_and_date(fake_http) -> None:
    await client.list_candidate_ids(datetime(2025, 9, 24, tzinfo=UTC), None)
    request = fake_http.requests[0]
    assert "after:2025/09/24" in request.url.params["q"]
    assert "from:(amazon.in OR flipkart.com)" in request.url.params["q"]
    assert request.url.params["maxResults"] == "100"


@pytest.mark.asyncio
async def test_provider_payload_is_not_leaked_on_failure(fake_http) -> None:
    fake_http.respond(500, {"error": {"message": "user@example.com token=secret"}})
    with pytest.raises(GmailUnavailableError, match="temporarily unavailable") as caught:
        await client.get_message("m1")
    assert "secret" not in str(caught.value)
```

- [ ] **Step 2: Write hostile normalization tests**

```python
def test_normalizer_rejects_oversized_message() -> None:
    with pytest.raises(MessageTooLargeError):
        normalize_message(raw_message(body=b"x" * 101), max_bytes=100)


def test_normalizer_strips_scripts_and_ignores_attachments() -> None:
    email = normalize_message(html_message("<script>steal()</script><p>Order A-1</p>", attachment=b"secret"), 1000)
    assert "steal" not in email.text
    assert "Order A-1" in email.text
    assert "secret" not in email.text
```

- [ ] **Step 3: Run tests and verify failures**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/integrations/gmail/test_client.py tests/orders/test_message_normalizer.py -q`

Expected: FAIL importing Gmail client and message normalizer.

- [ ] **Step 4: Implement the narrow Gmail REST client**

Use `users/me/messages`, `users/me/messages/{id}`, and `users/me/history`; fixed connect/read timeouts; bounded `maxResults=100`; injected access-token provider; typed page models; explicit handling for 401, 404 history expiration, 429, and transient 5xx.

- [ ] **Step 5: Implement bounded MIME normalization and safe URLs**

Decode only `text/plain` and `text/html`; cap decoded bytes before parsing; remove scripts/styles/forms; normalize whitespace; ignore attachments and remote resources. Allow links only when scheme is HTTPS and the normalized host matches configured Amazon/Flipkart suffixes without substring tricks.

- [ ] **Step 6: Run focused tests including malformed base64, nested multipart, script HTML, oversized body, and deceptive URL hosts**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/integrations/gmail/test_client.py tests/orders/test_message_normalizer.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/integrations/gmail/client.py backend/app/orders backend/tests/integrations/gmail/test_client.py backend/tests/orders/test_message_normalizer.py
git commit -m "feat: add bounded Gmail message transport"
```

---

### Task 5: Amazon and Flipkart Parser Adapters

**Files:**
- Create: `backend/app/orders/parsers/amazon.py`
- Create: `backend/app/orders/parsers/flipkart.py`
- Create: `backend/tests/fixtures/orders/amazon_order_placed.json`
- Create: `backend/tests/fixtures/orders/amazon_shipped.json`
- Create: `backend/tests/fixtures/orders/flipkart_order_placed.json`
- Create: `backend/tests/fixtures/orders/flipkart_delivered.json`
- Create: `backend/tests/orders/test_amazon_parser.py`
- Create: `backend/tests/orders/test_flipkart_parser.py`

**Interfaces:**
- Consumes: `CommerceEmail`
- Produces: `AmazonOrderParser.matches(email) -> bool` and `.parse(email) -> list[OrderObservation]`
- Produces: `FlipkartOrderParser.matches(email) -> bool` and `.parse(email) -> list[OrderObservation]`
- Produces: `PARSER_REGISTRY: tuple[OrderEmailParser, ...]`

- [ ] **Step 1: Add sanitized fixtures and failing parser tests**

```python
def test_amazon_shipment_extracts_required_and_optional_facts() -> None:
    observations = AmazonOrderParser().parse(load_fixture("amazon_shipped.json"))
    assert observations == [OrderObservation(
        marketplace=Marketplace.AMAZON,
        marketplace_order_id="402-0000000-0000000",
        event_type=OrderEventType.SHIPPED,
        occurred_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
        status=CommerceOrderStatus.SHIPPED,
        items=[OrderItemObservation(title="USB-C charger", quantity=1)],
        marketplace_url="https://www.amazon.in/gp/your-account/order-details?orderID=402-0000000-0000000",
    )]


def test_flipkart_template_without_order_id_is_skipped() -> None:
    email = load_fixture("flipkart_delivered.json").model_copy(update={"text": "Your item was delivered"})
    assert FlipkartOrderParser().parse(email) == []
```

- [ ] **Step 2: Run tests and verify missing parsers**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/orders/test_amazon_parser.py tests/orders/test_flipkart_parser.py -q`

Expected: FAIL importing parser classes.

- [ ] **Step 3: Implement deterministic parsing with explicit minimum fields**

Use sender allow-lists, anchored order-number patterns, labeled amount/date/status extraction, HTML/text fallbacks, and safe URL validation. Return no observation unless marketplace, order ID, event type, and source timestamp are present. Never invent totals, delivery dates, products, or tracking numbers.

- [ ] **Step 4: Add table-driven tests for placed, shipped, delivered, cancelled, repeated item names, locale amounts, missing IDs, unrelated senders, and template drift**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/orders -q`

Expected: PASS and both missing-order-ID Review Focus tests skip safely.

- [ ] **Step 5: Commit**

```bash
git add backend/app/orders/parsers backend/tests/orders backend/tests/fixtures/orders
git commit -m "feat: parse Amazon and Flipkart order emails"
```

---

### Task 6: Idempotent Full and Incremental Synchronization

**Files:**
- Create: `backend/app/services/order_sync.py`
- Test: `backend/tests/services/test_order_sync.py`

**Interfaces:**
- Consumes: session factory, `GmailClient`, parser registry, `TokenCipher`, connection ID.
- Produces: `OrderSynchronizer.sync(connection_id: UUID, mode: Literal["auto", "full"] = "auto") -> Awaitable[SyncResult]`
- Produces: `SyncResult(candidate_count: int, parsed_count: int, skipped_count: int, order_count: int, history_id: str)`

- [ ] **Step 1: Write failing initial-sync and upsert tests**

```python
@pytest.mark.asyncio
async def test_initial_sync_upserts_order_and_discards_raw_body(sync_context) -> None:
    result = await sync_context.synchronizer.sync(sync_context.connection.id, mode="full")
    assert result.order_count == 1
    order = await sync_context.load_order("402-0000000-0000000")
    assert order.user_id == sync_context.user.id
    assert not hasattr(order, "raw_email")


@pytest.mark.asyncio
async def test_repeated_message_and_overlapping_sync_do_not_duplicate(sync_context) -> None:
    first, second = await asyncio.gather(
        sync_context.synchronizer.sync(sync_context.connection.id),
        sync_context.synchronizer.sync(sync_context.connection.id),
    )
    assert await sync_context.order_count() == 1
    assert await sync_context.event_count() == 1
    assert {first.skipped_locked, second.skipped_locked} == {False, True}
```

- [ ] **Step 2: Write failing expired-history and ownership tests**

```python
@pytest.mark.asyncio
async def test_expired_history_cursor_runs_bounded_reconciliation(sync_context) -> None:
    sync_context.gmail.history_error = GmailHistoryExpired()
    await sync_context.synchronizer.sync(sync_context.connection.id)
    assert sync_context.gmail.full_query_after == utc_now() - relativedelta(months=12)


@pytest.mark.asyncio
async def test_connection_owner_controls_all_written_orders(sync_context) -> None:
    await sync_context.synchronizer.sync(sync_context.connection.id)
    assert set(await sync_context.persisted_user_ids()) == {sync_context.connection.user_id}
```

- [ ] **Step 3: Run tests and verify failure**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/services/test_order_sync.py -q`

Expected: FAIL because `OrderSynchronizer` does not exist.

- [ ] **Step 4: Implement connection locking and lifecycle**

Acquire a PostgreSQL advisory transaction lock derived from the connection UUID; expose a fake lock adapter for SQLite tests. Set `syncing` and start time only after lock acquisition. Preserve `connected` during retryable failure, set `reconnect_required` only for invalid grants, and always clear a stale syncing state in `finally`.

- [ ] **Step 5: Implement source-event deduplication and order upsert**

Hash provider message IDs with an application pepper before persistence. Skip an existing `(connection_id, provider_message_id_hash)`. Upsert by owner/marketplace/order ID, replace items only when a newer observation contains item facts, append source events, and resolve status through an explicit precedence function.

- [ ] **Step 6: Implement full/incremental selection and expired-cursor fallback**

Full sync uses `utc_now() - relativedelta(months=settings.gmail_import_months)`. Incremental sync uses `history.list`. A `GmailHistoryExpired` triggers the same bounded full reconciliation. Save the newest history ID only after the page's database transaction commits.

- [ ] **Step 7: Run focused tests and verify review-focus cases**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/services/test_order_sync.py -q`

Expected: PASS for concurrency, repeated messages, pagination, partial-page rollback, invalid grant, retryable failure, expired cursor, and ownership.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/order_sync.py backend/tests/services/test_order_sync.py
git commit -m "feat: synchronize Gmail orders idempotently"
```

---

### Task 7: Celery Order Synchronization Tasks

**Files:**
- Create: `backend/app/workers/order_tasks.py`
- Modify: `backend/app/workers/celery_app.py`
- Test: `backend/tests/workers/test_order_tasks.py`

**Interfaces:**
- Consumes: `OrderSynchronizer.sync(connection_id, mode)`
- Produces: Celery task `orders.sync(connection_id: str, mode: str = "auto")`
- Produces: periodic task `orders.sync_due`

- [ ] **Step 1: Write failing sequential-job and retry tests**

```python
def test_two_sequential_jobs_create_and_dispose_separate_engines(monkeypatch) -> None:
    process_sync("connection-1", runner)
    process_sync("connection-2", runner)
    assert runner.loop_ids[0] != runner.loop_ids[1]
    assert runner.disposed == ["connection-1", "connection-2"]


def test_invalid_grant_is_not_retried(task) -> None:
    with pytest.raises(GmailReconnectRequired):
        task.run_with(FailingRunner(GmailReconnectRequired()))
    assert task.retry_calls == []
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/workers/test_order_tasks.py -q`

Expected: FAIL because order tasks are absent.

- [ ] **Step 3: Implement task-local engine lifecycle and retry classification**

Mirror the corrected document-worker pattern: construct and dispose the async engine inside each `asyncio.run` invocation. Retry quota, network, and database transient errors with bounded exponential backoff and jitter; do not retry invalid grant, malformed configuration, or permanent parser/data errors.

- [ ] **Step 4: Add a due-connection scheduler**

Query connection IDs whose last successful sync exceeds `gmail_sync_interval_minutes`; enqueue individual `orders.sync` tasks rather than processing mail in the beat task. Add the module to Celery includes and a 15-minute beat entry.

- [ ] **Step 5: Run worker tests**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/workers/test_order_tasks.py tests/workers/test_tasks.py -q`

Expected: PASS, including two sequential jobs in one worker process.

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/order_tasks.py backend/app/workers/celery_app.py backend/tests/workers/test_order_tasks.py
git commit -m "feat: process Gmail order sync jobs"
```

---

### Task 8: Gmail Connection API

**Files:**
- Create: `backend/app/schemas/integration.py`
- Create: `backend/app/api/v1/integrations.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/rate_limit.py`
- Test: `backend/tests/api/test_integrations.py`

**Interfaces:**
- Consumes: OAuth state/client, `TokenCipher`, `EmailConnection`, Celery dispatcher.
- Produces endpoints specified in the design and `GmailConnectionResponse`.

- [ ] **Step 1: Write failing status/authorize/callback tests**

```python
@pytest.mark.asyncio
async def test_authorize_returns_google_url_without_tokens(client, auth_headers) -> None:
    response = await client.post("/api/v1/integrations/gmail/authorize", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["authorization_url"].startswith("https://accounts.google.com/")
    assert "token" not in response.text.lower()


@pytest.mark.asyncio
async def test_callback_persists_encrypted_refresh_token_and_queues_sync(context) -> None:
    response = await context.callback("valid-code", "valid-state")
    assert response.status_code == 303
    connection = await context.load_connection()
    assert connection.encrypted_refresh_token != "refresh-secret"
    assert context.queued == [(str(connection.id), "full")]
```

- [ ] **Step 2: Write failing disconnect/delete/rate-limit tests**

Cover revocation before token deletion, idempotent disconnect, explicit deletion retaining the Gmail connection, cascade cleanup when the owning user is deleted, cross-user access, disabled feature behavior, queue publication failure, and user-scoped sync limiting.

- [ ] **Step 3: Run tests and verify 404/import failures**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/api/test_integrations.py -q`

Expected: FAIL because the router is absent.

- [ ] **Step 4: Implement response schemas and router**

```python
class GmailConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: EmailConnectionStatus
    email_address: str | None
    last_sync_completed_at: datetime | None
    imported_order_count: int
    marketplace_counts: dict[Marketplace, int]
    reconnect_required: bool
```

Use an HttpOnly, SameSite=Lax, Secure-in-production nonce cookie for browser binding. Callback validates state before token exchange, resolves the owning user exclusively from the consumed server-side state, reads the account address through Gmail `users.getProfile`, then redirects only to the configured frontend origin. Store a newly returned refresh token; preserve an existing token when Google legitimately omits it on reauthorization.

- [ ] **Step 5: Implement safe dispatch compensation and ownership**

If initial/manual task publication fails, persist a stable retryable sync error without discarding the valid connection. All status, disconnect, sync, and deletion queries filter by authenticated user ID.

- [ ] **Step 6: Run API tests and full backend suite**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/api/test_integrations.py -q && ..\.venv\Scripts\python.exe -m pytest -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/integration.py backend/app/api/v1/integrations.py backend/app/main.py backend/app/services/rate_limit.py backend/tests/api/test_integrations.py
git commit -m "feat: expose Gmail connection lifecycle"
```

---

### Task 9: Private Commerce Order API

**Files:**
- Create: `backend/app/services/commerce_orders.py`
- Create: `backend/app/schemas/commerce_order.py`
- Create: `backend/app/api/v1/orders.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_orders.py`

**Interfaces:**
- Produces: `list_commerce_orders(session, user_id, filters) -> list[CommerceOrder]`
- Produces: `get_commerce_order(session, user_id, order_id) -> CommerceOrder`
- Produces: `GET /api/v1/orders` and `GET /api/v1/orders/{order_id}`

- [ ] **Step 1: Write failing list/filter/detail tests**

```python
@pytest.mark.asyncio
async def test_list_filters_by_owner_marketplace_status_and_query(order_context) -> None:
    response = await order_context.client.get(
        "/api/v1/orders?marketplace=amazon&status=shipped&q=charger",
        headers=order_context.user_a_headers,
    )
    assert [item["marketplace_order_id"] for item in response.json()["items"]] == ["A-1"]


@pytest.mark.asyncio
async def test_foreign_order_id_is_not_found(order_context) -> None:
    response = await order_context.client.get(
        f"/api/v1/orders/{order_context.user_b_order.id}",
        headers=order_context.user_a_headers,
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests and verify missing endpoints**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/api/test_orders.py -q`

Expected: FAIL/404.

- [ ] **Step 3: Implement bounded queries and schemas**

Use `limit` 1–100, opaque cursor pagination by `(placed_at, id)`, indexed exact filters, escaped case-insensitive item/order search, eager loading for detail only, and deterministic descending order. Return `last_sync_completed_at` so the UI can state freshness.

- [ ] **Step 4: Validate marketplace links at serialization boundary**

If a legacy or malformed URL fails `validate_marketplace_url`, return `null`; never emit an arbitrary stored URL.

- [ ] **Step 5: Run tests including guessed UUID, foreign marketplace number, wildcard query, invalid cursor, and empty results**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/api/test_orders.py -q`

Expected: PASS, including the Review Focus cross-user case.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/commerce_orders.py backend/app/schemas/commerce_order.py backend/app/api/v1/orders.py backend/app/main.py backend/tests/api/test_orders.py
git commit -m "feat: expose private unified orders API"
```

---

### Task 10: Authenticated Order Agent Tools

**Files:**
- Modify: `backend/app/tools/schemas.py`
- Modify: `backend/app/tools/support.py`
- Modify: `backend/app/tools/registry.py`
- Modify: `backend/app/ai/types.py`
- Modify: `backend/app/ai/prompts.py`
- Test: `backend/tests/tools/test_commerce_order_tools.py`
- Test: `backend/tests/agent/test_graph.py`
- Test: `backend/tests/ai/test_gateway.py`

**Interfaces:**
- Produces tools: `list_my_orders`, `get_my_order`, `find_my_orders_by_product`
- Extends `ToolName` and SDK-supported `IntentDecision` with explicit optional fields: `marketplace`, `status`, `since`, `limit`, `order_id`, `query`

- [ ] **Step 1: Write failing ownership and result-shape tests**

```python
@pytest.mark.asyncio
async def test_get_my_order_ignores_model_identity_and_scopes_owner(context) -> None:
    result = await execute_tool(
        "get_my_order",
        {"order_id": str(context.user_b_order.id), "user_id": str(context.user_b.id)},
        context.user_a.id,
        context.session,
    )
    assert result.data["found"] is False


@pytest.mark.asyncio
async def test_list_my_orders_returns_freshness_without_source_email(context) -> None:
    result = await context.list_tool({"limit": 10})
    assert result.data["last_synced_at"] is not None
    assert "email_body" not in result.model_dump_json()
```

- [ ] **Step 2: Write failing installed-SDK schema test**

Extend the existing `_transformers.t_schema(None, IntentDecision)` assertion to require no `additionalProperties` and the new explicit scalar fields.

- [ ] **Step 3: Run tests and verify unknown-tool/schema failures**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/tools/test_commerce_order_tools.py tests/agent/test_graph.py tests/ai/test_gateway.py -q`

Expected: FAIL until tool names, handlers, and schema fields exist.

- [ ] **Step 4: Implement typed inputs and owner-scoped handlers**

Use Pydantic `extra="forbid"`, normalized bounds, and the shared commerce-order service. Do not add `user_id` to any input model. Return a stable `{found: false}` or empty list for foreign/nonexistent records rather than leaking existence.

- [ ] **Step 5: Extend intent schema without dictionary fields**

Keep Gemini compatibility by using explicit optional fields and mapping only fields relevant to the chosen tool through `tool_arguments`; do not reintroduce `dict[str, str]` into `response_schema`.

- [ ] **Step 6: Run focused and full backend tests**

Run: `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/tools/test_commerce_order_tools.py tests/agent/test_graph.py tests/ai/test_gateway.py -q && ..\.venv\Scripts\python.exe -m pytest -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/tools backend/app/ai backend/tests/tools/test_commerce_order_tools.py backend/tests/agent/test_graph.py backend/tests/ai/test_gateway.py
git commit -m "feat: answer authenticated commerce order questions"
```

---

### Task 11: Connected Accounts Frontend

**Files:**
- Create: `frontend/src/integrations/types.ts`
- Create: `frontend/src/integrations/useGmailIntegration.ts`
- Create: `frontend/src/integrations/ShoppingAccountsPanel.tsx`
- Create: `frontend/src/integrations/ShoppingAccountsPanel.test.tsx`
- Modify: `frontend/src/documents/DocumentsPage.tsx`
- Modify: `frontend/src/documents/DocumentsPage.test.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Gmail integration endpoints from Task 8.
- Produces: `<ShoppingAccountsPanel />` and query key `['gmail-connection', userId]`.

- [ ] **Step 1: Write failing disconnected/connected/syncing UI tests**

```tsx
it("starts Gmail authorization from Knowledge Base", async () => {
  server.use(statusHandler(disconnected), authorizeHandler("https://accounts.google.com/o/oauth2/v2/auth?..."));
  renderKnowledge();
  await userEvent.click(await screen.findByRole("button", { name: /connect gmail/i }));
  expect(assignLocation).toHaveBeenCalledWith(expect.stringMatching(/^https:\/\/accounts\.google\.com\//));
});

it("shows freshness, counts, and reconnect state", async () => {
  server.use(statusHandler({ ...connected, status: "reconnect_required", marketplace_counts: { amazon: 4, flipkart: 2 } }));
  renderKnowledge();
  expect(await screen.findByText(/reconnect required/i)).toBeVisible();
  expect(screen.getByText("4 Amazon orders")).toBeVisible();
  expect(screen.getByText("2 Flipkart orders")).toBeVisible();
});
```

- [ ] **Step 2: Run tests and verify missing component**

Run: `cd frontend && pnpm test -- --run src/integrations/ShoppingAccountsPanel.test.tsx src/documents/DocumentsPage.test.tsx`

Expected: FAIL.

- [ ] **Step 3: Implement private query/mutation hooks**

Use the authenticated API client, user-scoped query keys, disabled duplicate Sync now mutations, invalidation after mutation, and 401 handling inherited from `authenticatedFetch`. Authorization navigation only accepts an HTTPS `accounts.google.com` URL returned by the backend.

- [ ] **Step 4: Implement accessible connection states and destructive confirmations**

Render disconnected, authorizing, syncing, connected, reconnect-required, and retryable-error states. Disconnect and Delete imported orders require distinct confirmation dialogs with explicit consequences; never combine them.

- [ ] **Step 5: Integrate into Knowledge Base and responsive styles**

Add a Connected accounts section before Documents without changing existing document behavior. Preserve keyboard access, visible focus, mobile layout, and status text independent of color.

- [ ] **Step 6: Run focused and full frontend checks**

Run: `cd frontend && pnpm test -- --run src/integrations/ShoppingAccountsPanel.test.tsx src/documents/DocumentsPage.test.tsx && pnpm run typecheck`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/integrations frontend/src/documents frontend/src/styles.css
git commit -m "feat: connect Gmail from knowledge base"
```

---

### Task 12: Unified My Orders Frontend

**Files:**
- Create: `frontend/src/orders/types.ts`
- Create: `frontend/src/orders/useOrders.ts`
- Create: `frontend/src/orders/OrdersPage.tsx`
- Create: `frontend/src/orders/OrderDetailPage.tsx`
- Create: `frontend/src/orders/OrdersPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/layout/Sidebar.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: order endpoints from Task 9.
- Produces routes `/orders` and `/orders/:orderId` and query keys scoped by authenticated user and filters.

- [ ] **Step 1: Write failing list/filter/freshness tests**

```tsx
it("filters unified orders and shows sync freshness", async () => {
  renderOrders();
  expect(await screen.findByText("USB-C charger")).toBeVisible();
  await userEvent.selectOptions(screen.getByLabelText(/marketplace/i), "flipkart");
  expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining("marketplace=flipkart"), expect.anything());
  expect(screen.getByText(/last synced/i)).toBeVisible();
});

it("does not render a non-allow-listed marketplace link", async () => {
  server.use(orderDetailHandler({ ...order, marketplace_url: null }));
  renderOrderDetail();
  expect(await screen.findByText(order.marketplace_order_id)).toBeVisible();
  expect(screen.queryByRole("link", { name: /open in/i })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests and verify missing pages**

Run: `cd frontend && pnpm test -- --run src/orders/OrdersPage.test.tsx`

Expected: FAIL.

- [ ] **Step 3: Implement typed hooks and filters**

Serialize marketplace/status/search/date filters through `URLSearchParams`; debounce search input; keep previous page data; scope keys by user ID; render stable empty, loading, stale, and error states.

- [ ] **Step 4: Implement order list and detail timeline**

Use semantic tables/cards by breakpoint, marketplace badges, textual statuses, localized dates/currency, item quantities, source-event timeline, and last-sync freshness. Add `rel="noopener noreferrer"` to validated marketplace links.

- [ ] **Step 5: Add routes/navigation and mobile sign-out preservation**

Add My Orders to the sidebar and route table. Ensure the existing mobile breakpoint retains an accessible account/sign-out action while modifying navigation styles.

- [ ] **Step 6: Run frontend tests, typecheck, and production build**

Run: `cd frontend && pnpm test -- --run && pnpm run typecheck && pnpm run build`

Expected: all tests PASS and Vite build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/orders frontend/src/App.tsx frontend/src/layout/Sidebar.tsx frontend/src/styles.css
git commit -m "feat: add unified My Orders experience"
```

---

### Task 13: Compose Journey, Environment, and Documentation

**Files:**
- Create: `backend/tests/integration/test_gmail_order_journey.py`
- Create: `backend/tests/integration/fake_gmail.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `backend/app/workers/celery_app.py`

**Interfaces:**
- Consumes all prior tasks.
- Produces a reproducible local fake-Gmail journey and complete operator documentation.

- [ ] **Step 1: Write a failing Compose integration journey**

The test must use PostgreSQL/pgvector, Redis, the API, and a real Celery worker. Mock only Google's network boundary with a fake HTTP service returning realistic OAuth, profile, message-list, message-get, and history responses.

```python
@pytest.mark.compose
async def test_gmail_orders_flow(compose_client, fake_gmail) -> None:
    user = await compose_client.register("orders@example.com")
    await compose_client.complete_google_oauth(user, fake_gmail.authorization_code)
    await fake_gmail.wait_for_sync_completed()
    orders = await compose_client.get("/api/v1/orders", user=user)
    assert {(item["marketplace"], item["marketplace_order_id"]) for item in orders["items"]} == {
        ("amazon", "402-0000000-0000000"),
        ("flipkart", "OD000000000000000000"),
    }
    answer = await compose_client.chat("Where is my charger order?", user=user)
    assert "shipped" in answer.lower()
```

- [ ] **Step 2: Run the journey and verify it fails before environment wiring**

Run: `docker compose --profile integration run --rm integration-tests pytest tests/integration/test_gmail_order_journey.py -q`

Expected: FAIL because fake Gmail/profile configuration is absent.

- [ ] **Step 3: Add integration profile and complete environment keys**

Document and wire:

```dotenv
GMAIL_INTEGRATION_ENABLED=false
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/integrations/gmail/callback
GMAIL_TOKEN_ENCRYPTION_KEYS=[]
GMAIL_IMPORT_MONTHS=12
GMAIL_SYNC_INTERVAL_MINUTES=30
GMAIL_MAX_MESSAGE_BYTES=1000000
GMAIL_MESSAGE_ID_PEPPER=
FRONTEND_URL=http://localhost:5173
```

Production validation rejects missing/placeholder secrets only when the feature is enabled. Add an `integration-tests` Compose service under the `integration` profile, reusing the API build and mounting the integration tests. The profile injects fake, non-production credentials and endpoint overrides available only in test settings.

- [ ] **Step 4: Update README setup and operational guidance**

Document Google Cloud test-user setup, redirect URI, feature flag, Fernet key generation, restricted-scope verification/security-assessment constraint, privacy/retention behavior, sync troubleshooting, disconnect versus delete, and explicit non-support for marketplace passwords and shopper credential scraping.

- [ ] **Step 5: Run final verification**

Run: `cd backend && ..\.venv\Scripts\python.exe -m ruff check app tests && ..\.venv\Scripts\python.exe -m pytest -q`

Run: `cd frontend && pnpm test -- --run && pnpm run typecheck && pnpm run build`

Run: `docker compose config --quiet`

Run: `docker compose build api worker frontend integration-tests`

Run: `docker compose run --rm api alembic upgrade head`

Run: `docker compose --profile integration run --rm integration-tests pytest tests/integration/test_gmail_order_journey.py -q`

Run: `docker compose up -d && docker compose ps`

Expected: lint, backend tests, frontend tests, typecheck, build, migration, Compose journey, and health checks all pass; API, PostgreSQL, and Redis are healthy; worker and frontend are running.

- [ ] **Step 6: Commit**

```bash
git add .env.example docker-compose.yml README.md backend/tests/integration backend/app/workers/celery_app.py
git commit -m "test: verify Gmail order integration end to end"
```

---

## Final Review Checklist

- [ ] Confirm every spec acceptance criterion maps to Tasks 1–13.
- [ ] Confirm no production code stores raw email bodies, MIME payloads, attachments, access tokens, or plaintext refresh tokens.
- [ ] Confirm all OAuth callback, integration, order, and tool paths derive ownership from the authenticated user.
- [ ] Confirm Google `IntentDecision` still serializes through installed `google-genai` without `additionalProperties`.
- [ ] Confirm two sequential Celery jobs do not reuse an async engine across closed event loops.
- [ ] Confirm feature-disabled startup requires no Google credentials and preserves existing SupportAI behavior.
- [ ] Request one whole-branch code review and fix Critical/Important findings once.
- [ ] Use `superpowers:verification-before-completion` before claiming completion.
- [ ] Use `superpowers:finishing-a-development-branch` for the integration decision.
