# Project structure

This document describes the Synapse monorepo layout, package conventions, and build tooling.

---

## Top-level layout

```
synapse/
├── apps/
│   ├── backend/              # Python · FastAPI · Centrifugo · Council engine
│   ├── web/                  # TypeScript · Svelte + SvelteKit
│   ├── synapse_app/          # Dart · Flutter · Desktop + Mobile
│   └── integrations/
│       ├── slack/            # Phase 1 · Python · Slack Bolt
│       ├── discord/          # Phase 1 · Python · Pycord
│       ├── telegram/         # Phase 1 · Python · python-telegram-bot
│       ├── teams/            # Phase 2 · Python · Bot Framework
│       ├── google_chat/      # Phase 2 · Python · Google Chat API
│       ├── lark/             # Phase 3 · Python · Lark Open Platform SDK
│       ├── wecom/            # Phase 3 · Python · WeCom API
│       ├── whatsapp/         # Phase 4 · Python · Meta Cloud API
│       ├── mattermost/       # Phase 4 · Python · Mattermost webhooks
│       └── line/             # Phase 4 · Python · Line Messaging API
│
├── packages/
│   └── api-client/           # Auto-generated typed API clients (TS + Dart)
│
├── docs/
│   └── _design/              # Architecture, design docs, ADRs
│
├── docker-compose.yml        # Local dev: backend + astrocyte-gateway + postgres
├── turbo.json                # Turborepo build orchestration (JS packages)
├── pnpm-workspace.yaml       # pnpm workspace definition
└── README.md
```

---

## Backend (`apps/backend/`)

```
apps/backend/
├── synapse/                          # Main Python package
│   ├── __init__.py
│   ├── main.py                       # FastAPI app factory, lifespan, CORS, middleware
│   ├── config.py                     # Settings via pydantic-settings (env vars)
│   │
│   ├── council/                      # Deliberation engine
│   │   ├── session.py                # Council session CRUD and state management
│   │   ├── orchestrator.py           # Stage coordinator, Centrifugo publish
│   │   └── stages/
│   │       ├── gather.py             # Stage 1: parallel member queries via asyncio.gather
│   │       ├── rank.py               # Stage 2: anonymised peer review, aggregate scoring
│   │       └── synthesise.py         # Stage 3: chairman synthesis
│   │
│   ├── memory/                       # Astrocyte abstraction
│   │   ├── gateway_client.py         # httpx client — retain / recall / reflect / forget
│   │   ├── context.py                # AstrocyteContext construction from JWT claims
│   │   └── banks.py                  # Bank name constants, MIP tag helpers
│   │
│   ├── realtime/                     # Centrifugo integration
│   │   ├── centrifugo.py             # HTTP publish client (httpx, async)
│   │   └── tokens.py                 # Centrifugo connection JWT signing (HMAC)
│   │
│   ├── mcp/                          # MCP server for agent-to-agent access
│   │   └── server.py                 # Tool definitions: start_council, join, contribute, recall_precedent, close
│   │
│   ├── scheduling/                   # Council scheduling (see scheduling.md)
│   │   ├── worker.py                 # APScheduler job — fires scheduled and recurring councils
│   │   ├── recurring.py              # Recurring council management
│   │   └── triggers.py               # Inbound webhook trigger handler
│   │
│   ├── templates/                    # Council templates (see templates.md)
│   │   ├── registry.py               # Built-in + custom template loading and inheritance
│   │   └── builtin/                  # Built-in YAML template definitions
│   │       ├── architecture-review.yaml
│   │       ├── security-audit.yaml
│   │       ├── code-review.yaml
│   │       ├── red-team.yaml
│   │       ├── product-decision.yaml
│   │       └── solo.yaml
│   │
│   ├── webhooks/                     # Outbound webhooks + export integrations (see webhooks.md)
│   │   ├── dispatcher.py             # Event emission + ARQ-backed delivery with retry
│   │   ├── registry.py               # Webhook CRUD and filtering
│   │   ├── signing.py                # HMAC-SHA256 via hmac stdlib
│   │   ├── delivery_log.py           # Delivery attempt tracking
│   │   └── exports/
│   │       ├── notion.py
│   │       ├── confluence.py
│   │       ├── github.py
│   │       ├── linear.py
│   │       └── markdown.py
│   │
│   ├── notifications/                # Email notifications (see notifications.md)
│   │   ├── dispatcher.py             # Routes events to aiosmtplib
│   │   ├── preferences.py            # Per-user notification preference management
│   │   └── emails/                   # Jinja2 email templates
│   │       ├── council_concluded.html.j2
│   │       ├── approval_requested.html.j2
│   │       ├── conflict_detected.html.j2
│   │       └── weekly_digest.html.j2
│   │
│   ├── analytics/                    # Analytics engine (see analytics.md)
│   │   ├── metrics.py                # Aggregation queries (consensus, velocity, members)
│   │   ├── clustering.py             # Topic clustering via AstrocyteGatewayClient.reflect()
│   │   └── api.py                    # Analytics context functions
│   │
│   ├── routers/                      # FastAPI routers (one per resource)
│   │   ├── councils.py               # CRUD + SSE stream endpoints
│   │   ├── chat.py                   # POST /v1/councils/{id}/chat (Mode 3 reflect)
│   │   ├── centrifugo.py             # GET /v1/centrifugo/token — issue connection JWT
│   │   ├── memory.py                 # Memory search endpoints for UI
│   │   ├── templates.py
│   │   ├── schedules.py
│   │   ├── webhooks.py
│   │   ├── analytics.py
│   │   ├── usage.py
│   │   └── api_keys.py
│   │
│   ├── auth/                         # Authentication and authorisation
│   │   ├── jwt.py                    # JWT validation via python-jose, AstrocyteContext construction
│   │   └── api_key.py                # API key validation and scope enforcement
│   │
│   └── db/                           # Database layer
│       ├── models.py                 # SQLAlchemy ORM models
│       ├── session.py                # Async engine + session factory
│       └── migrations/               # Alembic migrations
│           └── versions/
│
├── ee/                               # Enterprise Edition — Synapse EE License (proprietary)
│   ├── LICENSE                       # EE license (see apps/backend/ee/LICENSE)
│   ├── billing/                      # Multi-tenancy + Stripe (see multi-tenancy.md)
│   │   ├── tenants.py                # Tenant provisioning and lifecycle
│   │   ├── quotas.py                 # Quota enforcement
│   │   ├── stripe.py                 # stripe-python subscription + usage metering
│   │   └── usage.py                  # Usage tracking and reporting
│   ├── saml/                         # SAML SSO + SCIM (EE only)
│   ├── compliance/                   # Audit trails, DSAR, legal hold (EE only)
│   └── license/
│       ├── license_service.py        # License validation (online + offline)
│       └── feature_flags.py          # Runtime feature flag resolution from license
│
├── tests/
│   ├── council/
│   ├── memory/
│   └── routers/
│
├── centrifugo.yaml                   # Centrifugo config (channels, presence, history TTL)
├── mip.yaml                          # MIP routing rules for council memory banks
├── pyproject.toml                    # uv project definition + dependencies
├── alembic.ini                       # Alembic migration config
└── Dockerfile
```

---

## Web frontend (`apps/web/`)

```
apps/web/
├── src/
│   ├── routes/
│   │   ├── +layout.svelte        # Root layout, auth guard
│   │   ├── +page.svelte          # Home — chat entry point
│   │   ├── councils/
│   │   │   ├── +page.svelte      # Council list
│   │   │   └── [id]/
│   │   │       └── +page.svelte  # Council view: chat thread + stage panels
│   │   └── memory/
│   │       └── +page.svelte      # Memory explorer
│   │
│   ├── lib/
│   │   ├── api/                  # Generated TypeScript API client
│   │   ├── stores/               # Svelte stores (council state, chat thread, WS)
│   │   └── components/
│   │       ├── chat/
│   │       │   ├── ChatThread.svelte     # Unified chat + council event thread
│   │       │   ├── ChatInput.svelte      # Message input + directive hints
│   │       │   ├── ThreadEntry.svelte    # Polymorphic: message / stage / verdict
│   │       │   └── DirectivePicker.svelte # @redirect, @veto, @add UI
│   │       ├── council/
│   │       │   ├── CouncilStage.svelte
│   │       │   ├── MemberResponse.svelte
│   │       │   ├── RankingView.svelte
│   │       │   └── VerdictCard.svelte
│   │       └── memory/
│   │           └── MemoryHit.svelte
│   │
│   └── app.html
│
├── package.json
├── svelte.config.js
└── vite.config.ts
```

---

## Flutter app (`apps/synapse_app/`)

```
apps/synapse_app/
├── lib/
│   ├── main.dart
│   ├── app.dart                  # App root, routing, theme
│   │
│   ├── features/
│   │   ├── chat/
│   │   │   ├── chat_screen.dart          # Unified chat thread (Modes 1 + 2)
│   │   │   ├── chat_thread_widget.dart   # Thread entries (messages, stages, verdict)
│   │   │   ├── chat_input_widget.dart    # Input + directive support
│   │   │   └── verdict_chat_screen.dart  # Mode 3: chat with closed verdict
│   │   ├── councils/
│   │   │   ├── council_list_screen.dart
│   │   │   ├── council_detail_screen.dart  # Stages + chat thread combined
│   │   │   └── verdict_screen.dart
│   │   ├── memory/
│   │   │   ├── memory_explorer_screen.dart
│   │   │   └── memory_hit_card.dart
│   │   └── notifications/        # Mobile: push notification handling
│   │
│   ├── api/                      # Generated Dart API client
│   │   └── synapse_api_client.dart
│   │
│   └── core/
│       ├── auth/                 # JWT storage, refresh
│       ├── sse/                  # SSE stream listener
│       └── theme/
│
├── pubspec.yaml
└── analysis_options.yaml
```

The same Flutter project targets both desktop (macOS, Windows, Linux) and mobile (iOS, Android). Platform-specific behaviour (notifications on mobile, window management on desktop) is handled with conditional imports and platform checks.

---

## Shared packages (`packages/`)

### `packages/api-client/`

Auto-generated from the Synapse backend's OpenAPI schema. Do not edit manually.

```
packages/api-client/
├── typescript/               # Generated TypeScript client (consumed by web)
│   └── src/
│       ├── client.ts
│       └── models.ts
├── dart/                     # Generated Dart client (consumed by Flutter app)
│   └── lib/
│       └── synapse_client.dart
└── generate.sh               # Runs openapi-generator for both targets
```

Regenerate after backend API changes:
```bash
cd packages/api-client && ./generate.sh
```

---

## Configuration files

| File | Location | Purpose |
|------|----------|---------|
| `mip.yaml` | `apps/backend/` | Memory Intent Protocol routing rules |
| `centrifugo.yaml` | `apps/backend/` | Centrifugo channels, presence, history TTL, API key |
| `pyproject.toml` | `apps/backend/` | Python project definition + dependencies (uv) |
| `alembic.ini` | `apps/backend/` | Alembic database migration config |
| `docker-compose.yml` | Root | Local dev stack (backend + astrocyte-gateway + postgres + centrifugo + redis) |
| `turbo.json` | Root | JS build pipeline (web, api-client) |
| `pnpm-workspace.yaml` | Root | JS workspace definition |
| `pubspec.yaml` | `apps/synapse_app/` | Dart/Flutter dependencies |

---

## Build and development

### Local development

```bash
# Full local stack — required: backend + astrocyte-gateway + postgres + centrifugo
docker compose up

# Backend only (if astrocyte-gateway is already running)
cd apps/backend
uv sync
uv run alembic upgrade head
uv run fastapi dev synapse/main.py

# Web
cd apps/web
pnpm dev

# Desktop
cd apps/synapse_app
flutter run -d macos
```

### Environment variables (backend)

| Variable | Default | Purpose |
|----------|---------|---------|
| `ASTROCYTE_GATEWAY_URL` | — | Base URL of the running `astrocyte-gateway` service |
| `ASTROCYTE_TOKEN` | — | Auth token for Astrocyte gateway requests |
| `CENTRIFUGO_API_URL` | `http://centrifugo:8000` | Centrifugo HTTP API base URL |
| `CENTRIFUGO_API_KEY` | — | Centrifugo server-side API key (publish, presence) |
| `CENTRIFUGO_TOKEN_SECRET` | — | HMAC secret for signing client connection JWTs |
| `SYNAPSE_LLM_PROVIDER` | `openrouter` | `openrouter`, `litellm`, or `direct` |
| `OPENROUTER_API_KEY` | — | Required for OpenRouter |
| `SYNAPSE_AUTH_MODE` | `dev` | `dev`, `api_key`, or `jwt_oidc` |
| `SYNAPSE_JWT_JWKS_URL` | — | JWKS endpoint for JWT validation |
| `SYNAPSE_LICENSE_KEY` | — | Unlocks EE features (multi-tenancy, SAML, compliance) |
| `DATABASE_URL` | — | PostgreSQL connection string |
| `ARQ_REDIS_URL` | `redis://localhost:6379` | Redis URL for ARQ webhook/email job queue |

---

## Roadmap

All four tracks are driven by the **OpenAPI schema** as the shared contract. The frontends and integrations target the contract — they are not coupled to either backend implementation.

> The hosted Cerebro backend (Elixir + Phoenix) follows its own roadmap, maintained separately in the Cerebro repository. It is not documented here.

---

### Track 1 — Backend (open source)

Python · FastAPI · Centrifugo

| Phase | Deliverable |
|-------|-------------|
| **B1 — Core engine** | Council engine (gather → rank → synthesise), Astrocyte gateway integration, REST + SSE endpoints, Centrifugo publish, OpenAPI schema |
| **B2 — MCP server** | `start_council`, `join`, `contribute`, `recall_precedent`, `close` tools |
| **B3 — Async councils** | Quorum-based async deliberation, cursor polling, timeout policy |
| **B4 — Templates** | Built-in templates, custom templates, template inheritance |
| **B5 — Deliberation quality** | Multi-round deliberation, convergence detection, red team mode |
| **B6 — Workflows** | Conflict detection, approval chains, council chains, auto-promotion, demotion |
| **B7 — Scheduling** | Scheduled, recurring (cron), and externally triggered councils |
| **B8 — Analytics** | Member leaderboard, decision velocity, consensus distribution, topic clustering |
| **B9 — RBAC + Webhooks** | Full role model, API keys, outbound HMAC-signed webhooks, export integrations |
| **B10 — Notifications** | Email notifications, weekly digest, per-user preferences |
| **B11 — Multi-tenancy** | Tenant isolation, quota enforcement, Stripe billing (EE) |

---

### Track 2 — Web frontend

Svelte + SvelteKit · targets the OpenAPI contract

| Phase | Deliverable |
|-------|-------------|
| **W1 — Core** | Chat entry point (Mode 1), council list, stage streaming via Centrifugo, verdict display |
| **W2 — Human-in-the-loop** | Mode 2 participation, directives (`@redirect`, `@veto`, `@add`, `@close`), summon agent UI |
| **W3 — Mode 3 chat** | Chat with closed verdict, related precedents surfaced |
| **W4 — Memory explorer** | Search and browse Astrocyte banks |
| **W5 — Templates + Scheduling** | Template picker, schedule builder, triggered council UI |
| **W6 — Workflows** | Conflict alerts, approval UI, council chain viewer |
| **W7 — Analytics** | Member leaderboard, decision velocity dashboard, topic clustering |
| **W8 — Admin** | RBAC management, API keys, webhook registration, MIP routing traces |
| **W9 — Notifications + preferences** | In-app notification feed, per-user preference settings |
| **W10 — Multi-tenancy** | Tenant switcher, quota dashboard, billing management (EE) |

---

### Track 3 — Desktop + mobile (Flutter)

One Dart codebase · targets the OpenAPI contract

| Phase | Deliverable |
|-------|-------------|
| **F1 — Desktop core** | Council list, stage streaming, per-member reasoning traces, ranking matrix |
| **F2 — Desktop chat** | Mode 1 + Mode 2 participation, directives, summon agent |
| **F3 — Desktop depth** | Memory graph, MIP routing trace viewer, observability dashboard |
| **F4 — Mobile core** | Council list, verdict reading, Mode 3 chat |
| **F5 — Mobile notifications** | Push notifications (concluded, approval requests), approve/reject flow |

---

### Track 4 — Messaging integrations

Python · thin adapters over the REST API · can start as soon as B1 ships

| Phase | Platforms |
|-------|-----------|
| **I1** | Slack · Discord · Telegram |
| **I2** | Microsoft Teams · Google Chat |
| **I3** | Lark · WeCom |
| **I4** | WhatsApp · Mattermost · Line |
| **I5** | Extract inline clients into shared `synapse-py` dependency |

---

### Phase alignment

Tracks are independent but some phases have natural synchronisation points:

| Sync point | Backend | Frontend |
|------------|---------|----------|
| API contract available | B1 complete | W1, F1, I1 can start |
| MCP tools available | B2 complete | Agent integrations can use `start_council` |
| Human-in-the-loop API | B1 (directives in B1) | W2, F2 can ship |
| Templates API | B4 complete | W5 template picker can ship |
| Workflows API | B6 complete | W6 approval UI can ship |
| Analytics API | B8 complete | W7 dashboard can ship |
| Full RBAC + webhooks | B9 complete | W8 admin panel can ship |
