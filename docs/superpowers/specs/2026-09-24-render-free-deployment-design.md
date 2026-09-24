# AiderAI Render Free-Tier Deployment Design

## Purpose

Deploy AiderAI from `github.com/AyuSharma176/AiderAI` as a public demonstration using only Render free-tier resources plus the existing Neon PostgreSQL database. The deployment retains chat, PDF indexing, Gmail OAuth, manual order synchronization, and best-effort scheduled synchronization without committing credentials.

This is explicitly a demonstration deployment. It accepts Render free-tier sleep, cold starts, ephemeral files, and non-durable Redis in exchange for zero hosting cost.

## Architecture

The repository is represented by a root `render.yaml` Blueprint with three resources:

1. `aiderai-web-ayush176` is a free Render static site. It builds the Vite application from `frontend`, publishes `dist`, and rewrites client-side routes to `index.html`.
2. `aiderai-api-ayush176` is one free Docker web service built from `backend`. A small process supervisor runs Uvicorn, one Celery worker, and one Celery Beat scheduler in the same container. Keeping all three processes in one service allows the API and worker to share the same ephemeral upload directory and avoids paid worker resources.
3. `aiderai-redis` is a free private Render Key Value service used for Celery dispatch/results and shared rate-limit state.

The existing Neon database remains the durable system of record. Only the API web service receives a public backend URL. Redis is not exposed publicly.

## Process Model

Render runs Alembic migrations in the web service's pre-deploy command. The container start command then launches:

- Celery worker with concurrency one and the solo execution pool to fit the free instance's memory budget.
- Celery Beat with its schedule file under `/tmp`.
- Uvicorn bound to `0.0.0.0:$PORT` as the HTTP process Render health-checks.

The supervisor forwards shutdown signals to all children. If any required child exits unexpectedly, the supervisor terminates the others and exits non-zero so Render can restart the service instead of leaving a partially functioning deployment.

Only one combined service instance is permitted. Multiple instances would create duplicate Beat schedulers and are unavailable on the free plan in any case.

## Frontend and Routing

The static site builds with:

- Root directory: `frontend`
- Build command: `npm install && npm run build`
- Publish directory: `dist`
- SPA rewrite: `/*` to `/index.html`

`VITE_API_URL` is the public API base URL, including `/api/v1`. It contains no secret and is baked into the static bundle at build time. The initial Blueprint uses `https://aiderai-api-ayush176.onrender.com/api/v1`.

The backend allows only `https://aiderai-web-ayush176.onrender.com` through CORS and uses that same URL when redirecting the browser after Gmail OAuth.

## Backend Configuration

Non-secret Blueprint values include:

- `APP_ENV=production`
- `GEMINI_CHAT_MODEL=gemini-3.6-flash`
- `GEMINI_EMBEDDING_MODEL=gemini-embedding-001`
- `GMAIL_INTEGRATION_ENABLED=true`
- `GOOGLE_OAUTH_REDIRECT_URI=https://aiderai-api-ayush176.onrender.com/api/v1/integrations/gmail/callback`
- `FRONTEND_URL=https://aiderai-web-ayush176.onrender.com`
- `CORS_ORIGINS=["https://aiderai-web-ayush176.onrender.com"]`
- `UPLOAD_DIR=/tmp/aiderai/uploads`

Render prompts for these secrets during initial Blueprint creation:

- `DATABASE_URL`, using the rotated Neon credentials and SQLAlchemy's `postgresql+asyncpg://` scheme
- `GEMINI_API_KEY`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GMAIL_TOKEN_ENCRYPTION_KEYS`, containing a newly generated Fernet key

Render generates new production-only values for `JWT_SECRET` and `GMAIL_MESSAGE_ID_PEPPER`. `REDIS_URL` is populated from the private Key Value connection string.

Credentials previously shared in conversation are treated as exposed. The Gemini key, Google OAuth client secret, and Neon password must be rotated before entering production values in Render. No value from the local `.env` is committed.

## Runtime Data Flow

1. The browser loads the React application from Render's static CDN.
2. Browser API and streaming-chat requests go to the public Render API service.
3. The API stores durable application state and vectors in Neon.
4. PDF uploads are validated and written under an opaque filename in `/tmp/aiderai/uploads`, then queued in Redis.
5. The co-located Celery worker reads the same file, indexes chunks into Neon, and updates document status.
6. Gmail OAuth returns to the public API callback, which stores encrypted refresh-token state and redirects to the static knowledge page.
7. Celery Beat queues due Gmail syncs only while the free web service is awake. User-triggered synchronization wakes the service and remains the reliable free-tier path.

## Free-Tier Failure Behavior

- Render can spin the API down after 15 minutes without inbound traffic. The next request experiences a cold start.
- Uvicorn, Celery worker, and Beat stop together during sleep. Scheduled Gmail synchronization is therefore best-effort, not continuous.
- The local filesystem is ephemeral. A restart between upload and processing can remove a PDF. Existing ingestion failure handling marks the document failed when processing cannot read it, allowing the user to upload it again.
- Free Key Value does not persist across restarts. Queued but unfinished tasks can be lost; durable application and order data in Neon remains intact.
- The combined service has a tight CPU and memory budget. Worker concurrency remains one, and large workloads are outside the free deployment's supported scope.
- The API health endpoint is Render's health check. Unexpected child-process exits make the whole service restart rather than silently disabling background work.

## Google OAuth

Google Cloud must contain exactly:

- Authorized JavaScript origin: `https://aiderai-web-ayush176.onrender.com`
- Authorized redirect URI: `https://aiderai-api-ayush176.onrender.com/api/v1/integrations/gmail/callback`

If Render requires different service names because either name is unavailable, the Blueprint values and Google configuration must be updated to the actual domains before Gmail is enabled.

## Delivery Sequence

1. Add tests for the combined-process supervisor and Render-specific frontend/API configuration.
2. Add the supervisor, Docker adjustments, `render.yaml`, and deployment documentation.
3. Run backend tests and lint, frontend tests/type-check/build, Blueprint syntax checks, Docker Compose validation, and a local combined-process smoke test.
4. Commit and push the deployment changes to GitHub `main`.
5. Create a Render Blueprint from the repository and enter only newly rotated secrets.
6. Wait for the API health check and static build, then update Google OAuth with the exact deployed domains.
7. Smoke-test registration/login, Gemini chat, PDF indexing, Gmail connection, manual synchronization, and unified orders.

## Acceptance Criteria

- The Blueprint creates one free static site, one free web service, and one free Key Value resource.
- No background worker or cron resource requiring a paid plan is created.
- All three backend processes run and stop as one supervised unit.
- Migrations complete before the web service starts accepting traffic.
- The React application supports direct navigation to client-side routes.
- No secret exists in Git history or frontend build variables.
- The full automated suite passes and the deployed health endpoint responds successfully.
- The documented cold-start, scheduling, ephemeral-storage, and Redis limitations remain visible to the operator.

## Non-Goals

- Always-on background synchronization.
- Durable raw-PDF storage or durable Redis on the free tier.
- Horizontal scaling or high availability.
- Moving Neon data to Render PostgreSQL.
- Production uptime guarantees.
