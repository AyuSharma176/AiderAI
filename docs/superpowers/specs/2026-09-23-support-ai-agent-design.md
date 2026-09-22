# SupportAI Agent Platform Design

## Purpose

SupportAI Agent Platform is an interview-ready customer-support application that demonstrates practical generative AI and backend engineering without unnecessary distributed-system complexity. Registered users can chat with an AI support agent, ask questions grounded in company documents, check their orders, view their profile, and create support tickets. Company staff can upload PDF knowledge documents for asynchronous processing.

The project must run locally through Docker Compose, use the real Google Gemini API in normal operation, and use deterministic mocks only in automated tests. It is a standalone repository at `D:\codes\support-ai-agent` and does not reuse StudyBotAI code or history.

## Scope

The first release supports one company and one shared knowledge base. Users have private conversations, messages, orders, and tickets. The system deliberately excludes Kubernetes, Kafka, microservices, payments, complex permissions, multiple agents, and a deployment pipeline.

## Architecture

The system is a modular monolith with a separate background worker:

- A React, Vite, and TypeScript single-page application provides authentication, chat, conversation history, and knowledge-base management.
- A FastAPI application exposes authenticated JSON APIs and a server-sent events chat endpoint.
- A Celery worker extracts text from PDFs, chunks it, requests Gemini embeddings, and stores vectors.
- PostgreSQL with pgvector stores application data and document embeddings.
- Redis is the Celery broker/result backend and the shared store for rate limiting.
- Google Gemini provides embeddings, intent classification support, and response generation through the official SDK.
- LangGraph implements one support agent as an explicit, inspectable workflow.

Docker Compose runs `frontend`, `api`, `worker`, `postgres`, and `redis`. The backend remains one deployable codebase shared by the API and worker processes.

## Backend Boundaries

The FastAPI codebase is divided into focused modules:

- `api`: HTTP routes, request/response schemas, authentication dependencies, and SSE framing.
- `agent`: LangGraph state, graph construction, nodes, routing, and prompts.
- `rag`: PDF extraction, chunking, embedding, indexing, and similarity retrieval.
- `tools`: allow-listed support operations with typed inputs and authenticated ownership checks.
- `models`: SQLAlchemy entities and database lifecycle.
- `services`: authentication, conversations, documents, Gemini access, logging, and rate limiting.
- `workers`: Celery application and document-processing tasks.

Each module exposes a small interface so that AI providers, retrieval details, and tool implementations can be tested independently.

## Data Model

- `users`: ID, email, display name, password hash, and timestamps.
- `conversations`: ID, owning user ID, title, and timestamps.
- `messages`: ID, conversation ID, role, content, optional citations/tool metadata, and timestamp.
- `documents`: ID, filename, content type, processing status, error message, and timestamps. Documents are company-wide.
- `document_chunks`: ID, document ID, chunk index, text, metadata, and pgvector embedding.
- `orders`: ID/order number, owning user ID, status, tracking number, and timestamps.
- `tickets`: ID, owning user ID, issue, status, and timestamps.
- `agent_execution_logs`: request/conversation references, event type, model, latency, tool name, success flag, safe metadata, and timestamp.

Database migrations are managed with Alembic. Seed data creates demo users and orders without embedding secrets in source control.

## Authentication and Authorization

Registration and login use normalized unique email addresses, Argon2 password hashing, and signed short-lived JWT access tokens. Authenticated dependencies load the current user. All conversation, message, order, and ticket queries enforce ownership at the database boundary. The shared document collection requires authentication but does not implement roles in this release.

Secrets are read from environment variables. Local `.env` files are ignored, while `.env.example` files document every required setting. Normal AI operation requires `GEMINI_API_KEY` and fails with a clear configuration error when it is absent.

## Agent Workflow

`ConversationState` contains messages, user ID, conversation ID, retrieved context, citations, selected tool, tool arguments, tool result, route, and execution events.

The LangGraph workflow uses four conceptual nodes:

1. **Intent analyzer** chooses `knowledge`, `tool`, or `direct` and returns structured output.
2. **Retrieval node** embeds the question, performs a scoped top-k pgvector search, and prepares cited context.
3. **Tool execution node** validates structured arguments and invokes one allow-listed function.
4. **Response generator** combines conversation context with retrieved facts or tool results and streams a natural response.

Conditional edges skip retrieval and tools when unnecessary. The graph supports these typed tools:

- `get_order_status(order_id)`: returns only an order owned by the authenticated user.
- `create_support_ticket(issue)`: creates a ticket for the authenticated user after validating the issue.
- `get_customer_profile(user_id)`: ignores model-supplied identity escalation and permits only the authenticated user.

The backend persists the user message before graph execution. The assistant response is accumulated while SSE events are emitted, then saved atomically after successful completion. Typed events include `stage`, `token`, `citation`, `complete`, and `error`.

## RAG Pipeline

Uploading a PDF creates a `pending` document and enqueues `process_document(document_id)`. The worker validates and extracts the PDF, normalizes and chunks text with page metadata, requests Gemini embeddings in bounded batches, replaces the document chunks transactionally, and marks the document `ready` or `failed`.

At chat time, the retrieval node embeds the user's question and performs cosine similarity search against ready chunks. Results include filename, page, chunk ID, and score so the UI can display citations.

Retrieved text is delimited as untrusted reference data. The system prompt prohibits following instructions found in retrieved documents and requires relevant evidence for knowledge answers.

## API Surface

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/chat/message` using SSE
- `GET /api/v1/conversations`
- `POST /api/v1/conversations`
- `GET /api/v1/conversations/{conversation_id}`
- `DELETE /api/v1/conversations/{conversation_id}`
- `POST /api/v1/documents/upload`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`

Health endpoints distinguish process liveness from dependency readiness. OpenAPI documents non-streaming endpoints and the README documents the SSE event contract.

## Frontend Experience

The interface uses a restrained navy and indigo enterprise-support visual system with accessible contrast and responsive layouts. Login and registration provide inline validation. A dashboard links Chat, Conversations, and Knowledge Base. Chat renders persisted messages, streaming text, timestamps, citations, retry states, and live stage indicators. Conversation history resumes prior threads. Knowledge Base supports drag-and-drop PDF upload and displays processing and failure states.

TanStack Query manages server state and invalidation. A small authentication store manages the access token and current user. The frontend excludes fake analytics and unrelated administration screens.

## Security and Abuse Controls

- Pydantic schemas constrain all inputs.
- PDF type, extension, and configurable size limits are validated before storage.
- Redis-backed limits protect registration/login, chat, and upload endpoints.
- Tool names are fixed and tool arguments are schema-validated.
- Database ownership checks prevent cross-user data access.
- Prompt construction separates system instructions, user content, retrieved data, and tool results.
- Logs redact tokens, passwords, API keys, full prompts, and sensitive headers.
- CORS origins, JWT settings, model names, upload limits, and rate limits are environment-configurable.

## Reliability and Observability

Middleware assigns or propagates a request ID. Structured JSON logs record request latency, status, graph routing, retrieval counts, Gemini model/latency, tool calls, worker state, and failures. Agent execution records retain safe operational metadata without secrets or full private content.

Database and provider errors map to stable API error codes. SSE streams terminate with a typed error event when generation fails. Celery uses bounded retries for transient provider and database failures. Failed documents remain visible with their status.

## Testing

Backend pytest coverage includes authentication, protected routes, ownership, chunking and retrieval ranking, prompt-injection boundaries, intent routing, tools, graph branches, SSE events, document jobs, and failure behavior. Frontend Vitest and Testing Library coverage includes authentication, route protection, streaming chat, tool-stage indicators, citations, upload validation, and document statuses. Gemini is mocked at the provider boundary.

## Local Development and Documentation

The README will provide prerequisites, environment variables, Docker Compose commands, migrations, seed and test commands, API examples, troubleshooting, and Mermaid diagrams for architecture, RAG, agent, and tool flows. It will include concise interview explanations covering implementation, RAG, LangGraph, tool safety, and scaling.

## Scaling Path

The initial architecture scales through multiple stateless API and worker replicas. A production evolution can move uploads to object storage, use managed PostgreSQL/pgvector, separate worker queues, cache safe retrieval results, add connection pooling, and introduce tenant IDs and roles. These are documented evolution points rather than first-release scope.

## Completion Criteria

The project is complete when a fresh developer can configure secrets, start Docker Compose, register, use seeded order tools, upload a PDF, observe asynchronous indexing, ask a grounded question with citations, resume conversation history, create a ticket, and run both test suites successfully.
