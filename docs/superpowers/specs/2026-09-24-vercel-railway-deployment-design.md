# AiderAI Vercel and Railway Deployment Design

## Purpose

Deploy AiderAI from `github.com/AyuSharma176/AiderAI` without Render-style idle boot delays. The production system must retain chat streaming, PDF indexing, Gmail order synchronization, scheduled refreshes, and the existing Neon PostgreSQL data while keeping every credential out of Git.

The intended audience is the project owner operating a portfolio or small production deployment. Success means the Vercel frontend and Railway API are continuously reachable, asynchronous work survives API requests, Gmail OAuth returns to the production application, and a new GitHub push can be deployed and rolled back predictably.

## Selected Architecture

### Vercel frontend

Vercel builds the `frontend` workspace with `npm run build` and publishes `frontend/dist`. The browser calls the Railway API through an absolute `VITE_API_URL`. SPA rewrites send non-file routes such as `/chat`, `/knowledge`, and `/orders` to `index.html`.

Only public configuration is included in the Vercel build. No Gemini, Google OAuth, database, JWT, Redis, or bucket secret is exposed through a `VITE_` variable.

### Railway backend

One Railway project contains four runtime resources sourced from the same GitHub repository:

1. `aiderai-api` builds `backend/Dockerfile`, runs database migrations, then starts Uvicorn on Railway's assigned `PORT`. It is the only publicly reachable Railway service.
2. `aiderai-worker` builds the same backend image and runs the Celery worker.
3. `aiderai-scheduler` builds the same backend image and runs Celery Beat. Exactly one scheduler instance is allowed.
4. A private Railway Redis service provides the Celery broker/result backend and shared rate-limit state.

The API, worker, and scheduler use the same immutable Git commit and common production environment values. Railway private networking supplies Redis; Neon remains the system of record for relational data and vectors.

### Durable PDF storage

The API and worker are separate services, so their local filesystems cannot be used to exchange uploaded PDFs. A private Railway Storage Bucket provides S3-compatible object storage.

The backend gains a storage boundary with two implementations:

- `local`, preserving the current filesystem behavior for local Docker development and tests.
- `s3`, used in production with Railway Bucket credentials.

On upload, the API validates the PDF and writes it under an opaque generated object key. The database stores that key, never a public URL or user-supplied path. The worker fetches the object through the private S3 API, extracts and embeds it, and keeps the object available for safe retries. Bucket errors produce the existing sanitized document failure state; credentials and provider response bodies are never returned to the client.

## Configuration

### Vercel

- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `dist`
- `VITE_API_URL=https://<railway-api-domain>/api/v1`

### Shared Railway backend variables

- `APP_ENV=production`
- `DATABASE_URL` using SQLAlchemy's `postgresql+asyncpg://` scheme and the rotated Neon credentials
- `REDIS_URL` referencing the private Railway Redis URL
- `JWT_SECRET` generated specifically for production
- `GEMINI_API_KEY`
- `GEMINI_CHAT_MODEL=gemini-3.6-flash`
- `GEMINI_EMBEDDING_MODEL=gemini-embedding-001`
- `GMAIL_INTEGRATION_ENABLED=true`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI=https://<railway-api-domain>/api/v1/integrations/gmail/callback`
- `GMAIL_TOKEN_ENCRYPTION_KEYS` containing a newly generated Fernet key
- `GMAIL_MESSAGE_ID_PEPPER` generated specifically for production
- `FRONTEND_URL=https://<vercel-domain>`
- `CORS_ORIGINS=["https://<vercel-domain>"]`
- `STORAGE_BACKEND=s3`
- S3 endpoint, bucket, region, access-key, and secret-key values injected from the Railway Bucket

The API public domain and Vercel production domain are established before the final OAuth and CORS values are applied. Google Cloud receives the exact Railway callback URL as an authorized redirect URI and the Vercel domain as an authorized JavaScript origin.

Credentials previously shared in conversation are treated as exposed. The Gemini API key, Google OAuth client secret, Neon password, JWT secret, Fernet key, and message-ID pepper must be newly generated or rotated before production deployment.

## Request and Background Data Flow

1. The browser loads the static React bundle from Vercel.
2. Authenticated browser requests and chat streams go directly to the Railway API over HTTPS.
3. The API reads and writes application state in Neon and uses Redis for rate limits and Celery dispatch.
4. PDF uploads are stored in the private Railway Bucket, then queued by object key. The worker retrieves and indexes them into Neon.
5. Gmail OAuth redirects to the Railway API callback, which stores encrypted refresh-token state and returns the browser to the Vercel knowledge page.
6. Celery Beat periodically queues due Gmail synchronizations; the worker calls Gmail and updates unified orders in Neon.

## Failure Handling

- The API health endpoint is Railway's deployment health check. A deployment is not promoted until the service is healthy.
- Alembic migrations run only in the API pre-start path, preventing three services from racing migrations.
- Worker tasks retain their existing retry and terminal-failure behavior. Bucket access failures are logged with request/task context and surfaced as safe document states.
- The single scheduler avoids duplicate periodic dispatch. Order synchronization remains idempotent by provider message hash and order identity.
- CORS is restricted to the production Vercel origin. Preview deployments do not receive production OAuth secrets by default.
- Rollback uses Vercel and Railway deployment history. Schema changes must remain backward compatible with the previous application revision so application rollback does not require a destructive database rollback.

## Delivery Sequence

1. Add the storage abstraction, S3 implementation, production start commands, Vercel SPA configuration, deployment documentation, and tests.
2. Push the deployment commit to GitHub `main` after the full release test suite passes.
3. Create the Railway project, Redis service, and Storage Bucket; configure the API, worker, and scheduler from the same GitHub commit.
4. Generate the Railway API domain and confirm `/health/ready` before enabling Gmail.
5. Create the Vercel project from the `frontend` root and point `VITE_API_URL` at Railway.
6. Set the final Vercel origin in Railway CORS/frontend settings and the final Railway callback in Google Cloud.
7. Run a production smoke test: register/login, stream chat, upload/index a PDF, connect Gmail, synchronize orders, and confirm a scheduled sync is queued.

## Testing and Acceptance

- Unit tests cover local and S3 storage behavior, upload cleanup, worker retrieval, and safe provider failures.
- Existing backend, frontend, Gmail, and order tests remain green.
- Frontend type-check and production build pass with an absolute API URL.
- Deployment configuration is validated without secrets committed.
- Live health checks prove both public services are reachable.
- The production smoke test proves API-to-worker file handoff, Gemini chat, Gmail OAuth, and order synchronization.

## Explicit Non-Goals

- Rewriting the Python backend as Vercel Functions.
- Replacing Celery with Vercel Queues or Workflow.
- Moving Neon data into Railway PostgreSQL.
- Exposing Redis, the bucket, worker, or scheduler publicly.
- Committing any production credential or generated secret.
