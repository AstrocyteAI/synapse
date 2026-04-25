# Technology stack

This document records the technology choices for the Synapse open-source self-hosted backend and the rationale behind each decision.

> The hosted Cerebro version of Synapse uses a different backend stack (Elixir + Phoenix). See `cerebro/docs/_design/synapse-backend.md`.

---

## Backend

### Python 3.12 + FastAPI

**Python** — the pragmatic choice for an open-source self-hosted project. Python is the dominant language in AI/ML tooling; LLM SDKs, evaluation libraries, and the messaging integration bots all use Python. Contributors can work across the full codebase in one language without a context switch.

**FastAPI** — async-native (critical for parallel LLM calls in Stage 1 and Stage 2 via `asyncio.gather`), automatic OpenAPI schema generation (used to generate `synapse-py` and `synapse-ts` clients), and clean dependency injection. FastAPI serves only REST endpoints — it holds no WebSocket connection state.

**uv** — package and virtualenv management. Fast, reproducible, and consistent with Astrocyte's own tooling.

### Centrifugo (real-time sidecar)

Centrifugo is a self-contained Go binary that manages all persistent client connections. FastAPI publishes council events to Centrifugo's HTTP API; Centrifugo delivers them to all subscribers regardless of which backend replica the event originated from. FastAPI workers are fully stateless with respect to connections.

```python
# After a stage completes — Python publishes once, Centrifugo delivers to all
await centrifugo.publish(
    channel=f"council:{council_id}",
    data={"type": "stage1_complete", "responses": [...]}
)
```

**Why Centrifugo over FastAPI WebSockets + Redis pub/sub:**
- FastAPI WebSockets require sticky sessions or manual Redis subscription management per worker — complexity that grows with every new connection feature
- The migration from FastAPI WebSockets to Centrifugo later is a full rework of client connection code, auth flow, and server handlers; starting with Centrifugo avoids that entirely
- Centrifugo provides presence (observer count per council) and history (reconnecting clients catch up without the backend replaying events) out of the box

**Single-node local dev:** Centrifugo runs as one container in `docker-compose.yml` with no Redis dependency. Multi-node production: add `broker: redis` to `centrifugo.yaml` — Python code unchanged.

### Database and background jobs

**SQLAlchemy (async) + asyncpg** — async ORM for PostgreSQL. Alembic for schema migrations.

**APScheduler** — in-process async scheduler for one-time and recurring council execution.

**ARQ + Redis** — async job queue for webhook delivery with exponential backoff retry, email dispatch, and weekly digest generation.

### HTTP and integrations

**httpx** — async HTTP client for Astrocyte gateway calls, LLM provider APIs (OpenRouter, LiteLLM), and Stripe.

**python-jose** — JWT decoding and RS256 signature validation.

**aiosmtplib + Jinja2** — async SMTP delivery with HTML/text email templates.

**hmac (stdlib)** — HMAC-SHA256 webhook signing. No external dependency.

**stripe-python** — Stripe API client for subscription management and usage metering (EE only, in `ee/billing/`).

**Astrocyte integration** — Synapse connects to Astrocyte exclusively in **Gateway mode** (HTTP). The `AstrocyteGatewayClient` wraps all `retain`, `recall`, `reflect`, and `forget` calls via `httpx`, constructing `AstrocyteContext` (principal, tenant_id, role) from the validated JWT on every request. In-process library mode is not used.

### LLM access

**OpenRouter** (default) — single API endpoint for 100+ models. One auth token, one rate-limit surface, uniform interface across GPT, Claude, Gemini, Grok, and open-weight models. Ideal for councils that mix models from multiple providers.

**LiteLLM** (alternative) — self-hosted proxy with the same multi-provider benefit. Preferred when teams require on-premise routing or want to avoid third-party intermediaries.

Direct SDK calls are supported for single-provider councils where OpenRouter overhead is not justified.

---

## Frontends

### Svelte + SvelteKit (web)

**Why Svelte over React:**
- Compiles away the framework — no virtual DOM, smaller bundle, faster runtime
- Reactive stores are a natural fit for Centrifugo event streams: council stage events flow into stores with minimal ceremony
- SvelteKit provides routing, server-side rendering, and API routes out of the box
- Lighter than React for a developer tool where bundle size and initial load time matter

**SvelteKit** handles:
- Council dashboard (live stage streaming via Centrifugo)
- Memory explorer (search and browse Astrocyte banks)
- Session history
- Admin views (MIP routing traces, policy events)

### Flutter (desktop + mobile)

**Why Flutter over Electron/Tauri (desktop) + React Native (mobile):**
- One Dart codebase for both surfaces — no split between desktop wrapper and mobile app
- Flutter's custom renderer excels at the UI Synapse needs: council stage visualisation, real-time agent activity, memory graph views, rich animations
- No JavaScript bridge overhead on mobile — compiled to native ARM
- Tauri wraps a web app; Flutter renders its own widgets at native speed
- Desktop and mobile share the same component library, navigation patterns, and API client

**Flutter desktop** — primary use cases:
- Observing active councils with rich per-agent detail
- Memory graph exploration beyond what the web UI exposes
- MIP routing trace viewer and observability dashboard

**Flutter mobile** — primary use cases:
- Push notifications when a council concludes
- Reading council verdicts and session history
- Approving or rejecting pending decisions
- Not a council creation surface

**Why not Flutter for web:**
- Flutter web's CanvasKit renderer ships ~2 MB+ before application code
- Browser feel (text selection, scrolling, right-click) is subtly wrong for a developer tool
- Svelte is the right choice for the browser surface

---

## Monorepo tooling

**pnpm + Turborepo** — manages the JavaScript/TypeScript packages (`web/`, `packages/`). Turborepo handles build caching and task orchestration across the frontend workspace.

**uv** — manages the Python backend (`apps/backend/`) and messaging integration bots (`apps/integrations/`).

**Docker Compose** — local development stack: FastAPI backend + Centrifugo + Astrocyte gateway + PostgreSQL. All four services are required; there is no library-mode shortcut.

---

## API contract

The backend emits an **OpenAPI schema** at `/openapi.json`. Typed clients are generated from this schema:

| Consumer | Generated client |
|---------|-----------------|
| Svelte web | TypeScript client via `openapi-typescript` |
| Flutter desktop + mobile | Dart client via `openapi-generator` |

**Centrifugo (WebSocket / SSE)** — real-time council events flow via Centrifugo channels, not the REST API. Clients obtain a connection JWT from `GET /v1/centrifugo/token`, connect to Centrifugo directly, and subscribe to `council:{id}`. Mode 1 and Mode 2 real-time streams use this path. Mode 3 (chat with verdict) is pure REST.

---

## Authentication

**JWT (RS256)** — Synapse validates tokens from a configured OIDC provider via `python-jose`. The JWT subject and claims are mapped to an `AstrocyteContext` passed to all memory operations.

**Centrifugo connection JWT** — issued by `GET /v1/centrifugo/token` after the user's Synapse JWT is validated. Signed with `CENTRIFUGO_TOKEN_SECRET`. Carries user ID and allowed channel list.

**MCP access** — API key auth with per-key bank scoping. Agent identities are tracked as `agent:{name}` principals in Astrocyte audit logs.

---

## Decision log

| Decision | Chosen | Alternatives considered | Reason |
|----------|--------|------------------------|--------|
| Backend language | Python | Elixir (Phoenix), Go | Open-source accessibility; AI/ML ecosystem; consistent with integration bots; hosted Cerebro version uses Elixir |
| Web framework | FastAPI | Django, Flask | Async-native; auto OpenAPI schema generation; clean DI |
| Real-time layer | Centrifugo | FastAPI WebSockets + Redis, Phoenix Channels | Stateless Python workers; no sticky sessions; built-in presence + history; single Go binary; clean upgrade path |
| Astrocyte mode | Gateway only | Library + Gateway | Gateway is language-agnostic; library mode is Python-only but couples deploy; gateway is the production path regardless |
| Background jobs | APScheduler + ARQ | Celery, Oban | APScheduler for in-process scheduling; ARQ for durable retry queue; both async-native |
| Database ORM | SQLAlchemy async | Tortoise ORM, raw asyncpg | Mature; alembic migrations; familiar to Python community |
| JWT validation | python-jose | authlib, PyJWT | RS256 support; well-maintained |
| Web frontend | Svelte | React, Vue | Smaller bundle; Centrifugo event streams map cleanly to Svelte stores; lighter for dev tool |
| Desktop | Flutter | Tauri, Electron | One codebase with mobile; native rendering; no JS bridge |
| Mobile | Flutter | React Native, Expo | Shared with desktop; performance; no bridge |
| Flutter web | Not used | Flutter web | Bundle size; browser feel; Svelte is better for the browser surface |
| Integration bots | Python (uv) | Elixir, TypeScript | Thin adapters calling REST API; Slack Bolt, Pycord, python-telegram-bot are mature |
| Package manager (JS) | pnpm + Turborepo | npm, yarn, nx | Monorepo-native; build caching |
| LLM access | OpenRouter (default) | LiteLLM, direct SDKs | Multi-model; single auth; council flexibility |
| Auth | JWT RS256 / OIDC + python-jose | API key only | Stateless; matches Astrocyte gateway; multi-tenant ready |
