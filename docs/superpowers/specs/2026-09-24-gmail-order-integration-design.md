# Gmail Order Integration Design

## Purpose

SupportAI will let an authenticated shopper connect a Gmail account and use one interface to find and discuss purchases from Amazon, Flipkart, and later marketplaces. The integration reads order-related messages from the previous 12 months, converts them into private normalized order records, and exposes those records through an order list and authenticated agent tools.

This design does not collect Amazon or Flipkart credentials. Their official order APIs target sellers rather than ordinary shoppers, so the shopper-facing product uses user-authorized Gmail access instead.

## Release Scope

The first release includes:

- one Gmail connection per SupportAI user;
- an initial 12-month import and incremental synchronization;
- deterministic Amazon and Flipkart email adapters;
- a normalized private order store;
- connection controls inside Knowledge Base;
- a unified My Orders view;
- read-only chat enquiries and marketplace deep links;
- encrypted refresh-token storage, disconnect, and imported-data deletion.

The release excludes Outlook, marketplace credential collection, browser scraping, purchasing, cancellations, returns, refunds, email modification, and automatic execution of external actions. AI-based extraction for unknown marketplaces is deferred until deterministic adapters have reliable production metrics.

## Product Experience

Knowledge Base becomes a source-management page with two sections:

1. **Documents** retains the existing PDF workflow.
2. **Connected accounts** contains a Shopping accounts panel.

The Gmail card displays the connected address, connection state, last successful sync, imported-order count, and marketplace counts. Available actions are Connect Gmail, Sync now, Reconnect, Disconnect, and Delete imported orders. Disconnect revokes access and deletes the stored token but does not silently delete normalized orders; deletion is a separate confirmed action.

A new **My Orders** navigation destination lists orders with marketplace, status, order date, expected delivery, and total. Users can filter by marketplace, status, and date and search order numbers or item names. An order detail view shows items, shipment/tracking facts, a source-update timeline, last-sync freshness, and a safe link back to the marketplace.

Chat can answer questions such as:

- “Where is my phone order?”
- “Show my undelivered Amazon orders.”
- “What did I order from Flipkart last month?”
- “When should order 123 arrive?”

Answers identify when information was last synchronized and never imply that SupportAI can cancel, return, refund, or modify an order.

## Architecture

The existing modular monolith gains four isolated boundaries:

- `integrations/gmail`: OAuth, token refresh, Gmail transport, message discovery, full sync, and incremental sync.
- `orders/parsers`: a common parser contract plus Amazon and Flipkart adapters.
- `services/order_sync`: orchestration, deduplication, normalization, persistence, and sync lifecycle.
- `workers/order_tasks`: Celery entry points and retry policy.

Marketplace parsers do not know about OAuth, HTTP, database sessions, or Celery. Each accepts a sanitized email envelope and returns zero or more typed order observations. Gmail transport does not understand marketplace formats. The synchronization service coordinates both through explicit interfaces, making fixtures and failure behavior independently testable.

The API remains responsible for authorization and JSON contracts. Celery performs initial and incremental synchronization. PostgreSQL stores encrypted connection credentials, sync cursors, normalized orders, and non-sensitive operational metadata. Redis remains the Celery broker and rate-limit store.

## Google OAuth

The backend implements Google's server-side authorization-code flow with:

- `https://www.googleapis.com/auth/gmail.readonly` only;
- offline access for refresh tokens;
- a random, single-use, expiring `state` value bound to the SupportAI user and browser session;
- PKCE where supported by the chosen Google client library;
- exact redirect-URI validation;
- account identity lookup after authorization;
- encrypted refresh tokens and short-lived access tokens kept out of persistent storage;
- token revocation during disconnect;
- reconnect-required state after revocation or an invalid grant.

The frontend never receives Google refresh tokens. OAuth callbacks do not accept a user ID from the browser as authority; they resolve ownership from server-side state.

`gmail.readonly` is a Google restricted scope. A public deployment must complete OAuth app verification and, because restricted data is processed server-side, may require an approved recurring security assessment. Development begins with test users in a Google Cloud OAuth testing project, but the feature must not be represented as generally deployable until those production requirements are satisfied.

## Data Model

### `email_connections`

- `id`
- `user_id` with one active Gmail connection per user
- provider (`gmail`)
- provider_account_id
- email_address
- encrypted_refresh_token
- granted_scopes
- status (`connected`, `syncing`, `reconnect_required`, `disconnected`)
- last_history_id
- last_sync_started_at
- last_sync_completed_at
- last_sync_error_code
- timestamps

### `commerce_orders`

- `id`
- `user_id`
- marketplace (`amazon`, `flipkart`)
- marketplace_order_id
- placed_at
- currency and total amount
- normalized status
- expected_delivery_at and delivered_at
- tracking number and carrier when present
- marketplace URL when validated
- last_source_message_at
- timestamps

A unique constraint on `(user_id, marketplace, marketplace_order_id)` prevents cross-user collisions and duplicate imports.

### `commerce_order_items`

- `id`
- `order_id`
- title
- quantity
- unit price when present
- marketplace product identifier when present

### `order_source_events`

- `id`
- `order_id`
- hashed or opaque Gmail message ID for deduplication
- event type (`placed`, `shipped`, `out_for_delivery`, `delivered`, `cancelled`, `return_update`, `unknown`)
- event timestamp
- parser name and parser version
- safe structured facts required to rebuild the timeline

No complete email body, raw MIME payload, attachment, authentication header, access token, or refresh token appears in order tables or logs.

## Synchronization Flow

### Initial synchronization

1. OAuth callback validates state, exchanges the code, encrypts the refresh token, and creates or updates the connection.
2. The API enqueues an initial-sync task and returns the user to Connected accounts.
3. The worker searches the preceding 12 months using a bounded query containing recognized sender domains and commerce keywords.
4. It fetches candidate messages in bounded pages and batches.
5. The message normalizer decodes headers and supported text/HTML parts, removes scripts and unsafe markup, and enforces message-size limits.
6. Parsers run by marketplace and produce typed observations.
7. The service upserts orders, items, and source events transactionally, then records the newest Gmail `historyId`.
8. The connection becomes connected and records completion time and counts.

### Incremental synchronization

Scheduled jobs and Sync now use Gmail `history.list` from the saved history ID. New or changed candidate messages are processed through the same idempotent pipeline. When Gmail reports that a history ID is outside its retained range, the worker performs a bounded 12-month reconciliation rather than failing permanently.

Only one sync may run for a connection at a time. A database advisory lock or equivalent distributed lock prevents overlapping manual and scheduled jobs. Retries use exponential backoff and preserve idempotency through source-message and marketplace-order uniqueness.

## Parser Contract

Each parser implements:

- sender and subject matching;
- `parse(message) -> list[OrderObservation]`;
- a parser name and semantic version;
- confidence based on required deterministic fields, not an LLM score.

An observation requires marketplace, order identifier, source event type, and source timestamp. Optional facts are omitted rather than guessed. Later messages may enrich an existing order. Status resolution follows a monotonic event precedence table while allowing explicit cancellation or return events to supersede shipment states.

HTML parsing uses structural selectors plus labeled-text fallbacks. Fixtures remove personal details while preserving marketplace layout. A message that cannot meet the minimum contract is skipped and counted; it does not create a partial mystery order.

## Agent Integration

The allow-listed tool registry gains:

- `list_my_orders(marketplace?, status?, since?, limit?)`
- `get_my_order(order_id)`
- `find_my_orders_by_product(query, limit?)`

Tool handlers derive `user_id` exclusively from the authenticated request. The model cannot supply or override identity. Results contain normalized order facts and last-sync timestamps, not email bodies or OAuth data. Tool output is serialized separately from system instructions and user content.

Intent classification adds an order-history route without replacing the existing local demo order tool until migration is complete. If Gmail is disconnected, stale, or syncing, the agent explains the state and directs the user to Connected accounts. Ambiguous product matches return a small selection rather than guessing.

## API Surface

- `GET /api/v1/integrations/gmail/status`
- `POST /api/v1/integrations/gmail/authorize`
- `GET /api/v1/integrations/gmail/callback`
- `POST /api/v1/integrations/gmail/sync`
- `POST /api/v1/integrations/gmail/disconnect`
- `DELETE /api/v1/integrations/gmail/orders`
- `GET /api/v1/orders`
- `GET /api/v1/orders/{order_id}`

State-changing endpoints require authentication and existing CSRF/origin protections appropriate to the token transport. Sync and authorization endpoints have user-scoped Redis limits. Order list and detail enforce ownership in the database query.

## Security and Privacy

- Refresh tokens use authenticated encryption with a dedicated key supplied through `GMAIL_TOKEN_ENCRYPTION_KEY`; key versioning supports rotation.
- Google client ID, client secret, redirect URI, OAuth scopes, sync interval, and import lookback are environment settings documented in `.env.example`.
- Tokens, raw messages, sender addresses, subjects, order identifiers, item titles, and customer details are excluded from logs.
- Parser input is untrusted. HTML is never rendered directly and email instructions never influence agent policy.
- Marketplace URLs are accepted only for allow-listed HTTPS hosts and rendered with safe link behavior.
- Imported records are private to their SupportAI owner.
- Disconnect and delete actions are audited using metadata only.
- Account removal must revoke Google access and delete tokens and imported commerce data.

The privacy notice and OAuth consent explanation must state what is read, why it is read, what is retained, and how the user can revoke access or delete imported data.

## Failure Handling and Observability

Connections expose stable safe error states: authorization denied, reconnect required, rate limited, temporary provider failure, parser degradation, and internal sync failure. Users see actionable text without provider payloads.

Worker metrics include sync duration, candidate count, parsed count, skipped count, order upsert count, provider latency, retry count, and parser/version counts. Alerts watch reconnect spikes, parser success-rate drops by marketplace, repeated Gmail quota failures, and stuck syncing states. Metrics never use email addresses or order identifiers as labels.

Partial work commits in bounded batches. A failed page can retry without duplicating prior results. Provider 401/invalid-grant errors stop retries and require reconnect; quota and transient 5xx errors retry with bounded exponential backoff.

## Testing

- Unit tests cover token encryption/rotation, OAuth state expiry and replay, URL validation, query construction, parser fixtures, status precedence, and tool ownership.
- Contract tests exercise Gmail transport against recorded sanitized response shapes and verify pagination, refresh, history reconciliation, and safe error mapping.
- Service tests cover duplicate messages, repeated orders, concurrent sync exclusion, partial failure, retry, and deletion.
- API tests cover cross-user isolation, rate limits, callback ownership, disconnect, and stable error contracts.
- Agent tests verify all three order tools and ensure model-supplied identity is ignored.
- Frontend tests cover connect, syncing, reconnect, disconnect confirmation, filters, freshness indicators, and chat order cards.
- A Compose journey runs PostgreSQL, Redis, API, and worker, uses a fake Gmail HTTP service with realistic OAuth/Gmail contracts, imports sanitized Amazon and Flipkart fixtures, and confirms both list and chat retrieval.

Tests never require a developer's Gmail account, live mailbox, or committed OAuth secret.

## Rollout

1. Ship schema, encryption, OAuth testing-mode connection, and connection UI behind `GMAIL_INTEGRATION_ENABLED`.
2. Add Amazon fixtures/parser and internal test-user synchronization.
3. Add Flipkart fixtures/parser and the unified My Orders view.
4. Add agent tools and chat order cards.
5. Measure parser reliability and complete Google verification/security requirements before public enablement.

## Acceptance Criteria

- A test user can connect Gmail without exposing a refresh token to the browser.
- Initial sync imports only matching messages from the previous 12 months.
- Amazon and Flipkart fixtures create correct, deduplicated private orders.
- Incremental sync adds updates without rescanning or duplicating history and reconciles an expired history cursor.
- Users can view and search their orders and ask chat questions about them.
- Every order query enforces authenticated ownership.
- Disconnect revokes access and removes stored credentials; imported-data deletion is explicit and complete.
- Logs and agent context contain no raw email bodies or OAuth secrets.
- The app communicates last-sync freshness and reconnect/failure states clearly.

## External Constraints

- Gmail `gmail.readonly` is a restricted OAuth scope and public release depends on Google's verification requirements and potentially an independent security assessment.
- Gmail history IDs have limited retention; an expired cursor requires a full bounded reconciliation.
- Marketplace email templates can change without notice, so parser versions, sanitized fixtures, and success-rate monitoring are required product capabilities.

## References

- Google OAuth for server-side web apps: https://developers.google.com/identity/protocols/oauth2/web-server
- Gmail scopes and restricted-scope requirements: https://developers.google.com/workspace/gmail/api/auth/scopes
- Gmail full and incremental synchronization: https://developers.google.com/workspace/gmail/api/guides/sync
- Google OAuth token security practices: https://developers.google.com/identity/protocols/oauth2/resources/best-practices
- Google Workspace user-data policy: https://developers.google.com/workspace/workspace-api-user-data-developer-policy
- Amazon Selling Partner Orders API: https://developer-docs.amazon.com/sp-api/docs/orders-api
- Flipkart Marketplace Seller APIs: https://seller.flipkart.com/api-docs/FMSAPI.html
