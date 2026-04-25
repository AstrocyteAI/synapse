# Project structure

This document describes the Synapse monorepo layout, package conventions, and build tooling.

---

## Top-level layout

```
synapse/
├── apps/
│   ├── backend/              # Python · FastAPI · Council engine
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
├── docker-compose.yml        # Local dev: backend + pgvector
├── turbo.json                # Turborepo build orchestration (JS packages)
├── pnpm-workspace.yaml       # pnpm workspace definition
└── README.md
```

---

## Backend (`apps/backend/`)

```
apps/backend/
├── synapse/
│   ├── __init__.py
│   ├── main.py               # FastAPI app, lifespan, CORS, route registration
│   ├── config.py             # Pydantic Settings — env vars, synapse.yaml loader
│   │
│   ├── council/              # Deliberation engine
│   │   ├── __init__.py
│   │   ├── session.py        # Session lifecycle (create, advance, close)
│   │   ├── orchestrator.py   # Stage coordinator, SSE emission
│   │   ├── models.py         # Pydantic DTOs: CouncilSession, Stage*, Verdict
│   │   └── stages/
│   │       ├── __init__.py
│   │       ├── gather.py     # Stage 1: parallel member queries + precedent injection
│   │       ├── rank.py       # Stage 2: anonymised peer review, aggregate scoring
│   │       └── synthesise.py # Stage 3: chairman synthesis
│   │
│   ├── memory/               # Astrocyte abstraction
│   │   ├── __init__.py
│   │   ├── client.py         # AstrocyteClient protocol + LibraryClient + GatewayClient
│   │   └── banks.py          # Bank name constants, MIP tag helpers
│   │
│   ├── mcp/                  # MCP server for agent-to-agent access
│   │   ├── __init__.py
│   │   └── server.py         # Tool definitions: start_council, join, contribute, recall_precedent, close
│   │
│   ├── api/                  # REST route handlers
│   │   ├── __init__.py
│   │   ├── councils.py       # CRUD + SSE stream endpoints
│   │   ├── sessions.py       # Session management
│   │   ├── chat.py           # POST /v1/councils/{id}/chat (Mode 3 reflect)
│   │   └── memory.py         # Memory search endpoints for UI
│   │
│   ├── chat/                 # Chat layer
│   │   ├── __init__.py
│   │   ├── router.py         # WebSocket handler — Modes 1 + 2
│   │   ├── reflect.py        # Mode 3: AstrocyteClient.reflect() wrapper
│   │   └── directives.py     # Parse @redirect, @veto, @close, @add
│   │
│   ├── streaming/
│   │   ├── sse.py            # SSE event formatting (read-only observers)
│   │   └── ws.py             # WebSocket connection manager
│   │
│   ├── auth/
│   │   ├── jwt.py            # JWT validation, AstrocyteContext construction
│   │   └── api_keys.py       # API key creation, validation, scope enforcement
│   │
│   ├── scheduling/           # Council scheduling (see scheduling.md)
│   │   ├── __init__.py
│   │   ├── scheduler.py      # APScheduler setup and job management
│   │   ├── models.py         # ScheduledCouncil, RecurringCouncil DTOs
│   │   └── triggers.py       # Inbound webhook trigger endpoint
│   │
│   ├── templates/            # Council templates (see templates.md)
│   │   ├── __init__.py
│   │   ├── registry.py       # Built-in + custom template loading and inheritance
│   │   ├── models.py         # CouncilTemplate DTO
│   │   └── builtin/          # Built-in YAML template definitions
│   │       ├── architecture-review.yaml
│   │       ├── security-audit.yaml
│   │       ├── code-review.yaml
│   │       ├── red-team.yaml
│   │       ├── product-decision.yaml
│   │       └── solo.yaml
│   │
│   ├── webhooks/             # Outbound webhooks + export integrations (see webhooks.md)
│   │   ├── __init__.py
│   │   ├── dispatcher.py     # Event emission + delivery with retry
│   │   ├── registry.py       # Webhook CRUD and filtering
│   │   ├── signing.py        # HMAC-SHA256 signing and verification
│   │   ├── delivery_log.py   # Delivery attempt tracking
│   │   └── exports/
│   │       ├── notion.py
│   │       ├── confluence.py
│   │       ├── github.py
│   │       ├── linear.py
│   │       └── markdown.py
│   │
│   ├── notifications/        # Email notifications (see notifications.md)
│   │   ├── __init__.py
│   │   ├── dispatcher.py     # Routes notification events to email + push
│   │   ├── preferences.py    # Per-user notification preference management
│   │   └── email/
│   │       ├── sender.py     # SMTP / provider adapter
│   │       ├── signing.py    # Signed action link generation + verification
│   │       └── templates/    # Jinja2 HTML + text templates
│   │           ├── base.html
│   │           ├── council_concluded.html
│   │           ├── approval_requested.html
│   │           ├── conflict_detected.html
│   │           └── weekly_digest.html
│   │
│   ├── analytics/            # Analytics engine (see analytics.md)
│   │   ├── __init__.py
│   │   ├── metrics.py        # Aggregation queries (consensus, velocity, members)
│   │   ├── clustering.py     # Topic clustering via Astrocyte reflect()
│   │   └── api.py            # Analytics REST endpoints
│   │
│   └── billing/              # Multi-tenancy + Stripe (see multi-tenancy.md)
│       ├── __init__.py
│       ├── tenants.py        # Tenant provisioning and lifecycle
│       ├── quotas.py         # Quota enforcement via Redis counters
│       ├── stripe.py         # Stripe subscription + usage metering
│       └── usage.py          # Usage tracking and reporting
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── astrocyte.yaml            # Astrocyte config (storage provider, MIP path, policy)
├── mip.yaml                  # MIP routing rules for council memory banks
├── synapse.yaml              # Synapse config (council defaults, LLM provider)
├── pyproject.toml            # uv-managed; Python 3.12+
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
| `synapse.yaml` | `apps/backend/` | Council defaults, LLM provider, memory mode |
| `astrocyte.yaml` | `apps/backend/` | Astrocyte storage provider, policy, MIP path |
| `mip.yaml` | `apps/backend/` | Memory Intent Protocol routing rules |
| `docker-compose.yml` | Root | Local dev stack (backend + pgvector) |
| `turbo.json` | Root | JS build pipeline (web, api-client) |
| `pnpm-workspace.yaml` | Root | JS workspace definition |
| `pyproject.toml` | `apps/backend/` | Python dependencies (uv) |
| `pubspec.yaml` | `apps/synapse_app/` | Dart/Flutter dependencies |

---

## Build and development

### Local development

```bash
# Backend (library mode — Astrocyte runs in-process)
cd apps/backend
uv sync
uv run fastapi dev synapse/main.py

# Web
cd apps/web
pnpm dev

# Desktop
cd apps/synapse_app
flutter run -d macos

# Full local stack (backend + pgvector)
docker compose up
```

### Environment variables (backend)

| Variable | Default | Purpose |
|----------|---------|---------|
| `SYNAPSE_ASTROCYTE_MODE` | `library` | `library` or `gateway` |
| `ASTROCYTE_GATEWAY_URL` | — | Required when mode is `gateway` |
| `ASTROCYTE_TOKEN` | — | Auth token for gateway mode |
| `SYNAPSE_LLM_PROVIDER` | `openrouter` | `openrouter`, `litellm`, or `direct` |
| `OPENROUTER_API_KEY` | — | Required for OpenRouter |
| `SYNAPSE_AUTH_MODE` | `dev` | `dev`, `api_key`, or `jwt_oidc` |
| `SYNAPSE_JWT_JWKS_URL` | — | JWKS endpoint for JWT validation |

---

## Phases

### Core platform

| Phase | Deliverable |
|-------|------------|
| **1 — Core** | Council engine, Astrocyte integration, REST + SSE + WebSocket, Svelte web UI |
| **2 — Desktop** | Flutter desktop app with rich council observation and MIP traces |
| **3 — Mobile** | Flutter mobile app (push notifications, read, Mode 3 chat, approve) |
| **4 — MCP** | MCP server for agent-to-agent council access |
| **5 — Async councils** | Async deliberation mode for live multi-agent sessions |
| **6 — Templates + Deliberation** | Council templates, multi-round deliberation, red team mode |
| **7 — Workflows** | Conflict detection, approval chains, council chains, auto-promotion |
| **8 — Scheduling** | Scheduled, recurring, and triggered councils |
| **9 — Analytics** | Member leaderboard, decision velocity, topic clustering dashboard |
| **10 — RBAC + Webhooks** | Full role model, API keys, outbound webhooks, export integrations |
| **11 — SDK** | `synapse-py` and `synapse-ts` generated from OpenAPI schema |
| **12 — Notifications** | Email notifications, weekly digest, per-user preferences |
| **13 — Multi-tenancy** | Tenant isolation, quota enforcement, Stripe billing |

### Integration phases

| Phase | Platforms |
|-------|----------|
| **Integration 1** | Slack, Discord, Telegram |
| **Integration 2** | Microsoft Teams, Google Chat |
| **Integration 3** | Lark, WeCom |
| **Integration 4** | WhatsApp, Mattermost, Line |
| **Integration 5** | Extract inline clients into shared `synapse-py` dependency |
