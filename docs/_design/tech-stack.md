# Technology stack

This document records the technology choices for Synapse and the rationale behind each decision.

---

## Backend

### Python 3.12 + FastAPI

**Python** — consistent with Astrocyte (`astrocyte-py`). The council engine imports Astrocyte as a library in development; a shared language means no serialisation boundary between Synapse and Astrocyte in library mode.

**FastAPI** — the same pattern used by `astrocyte-gateway-py`. Async-native (critical for parallel LLM calls in Stage 1 and Stage 2), built-in SSE support, automatic OpenAPI schema generation (used to generate typed API clients for Svelte and Flutter).

**uv** — package and virtualenv management. Fast, modern, reproducible. Used by Astrocyte; consistency across the AstrocyteAI monorepo matters.

### LLM access

**OpenRouter** (default) — single API endpoint for 100+ models. One auth token, one rate-limit surface, uniform interface across GPT, Claude, Gemini, Grok, and open-weight models. Ideal for councils that mix models from multiple providers.

**LiteLLM** (alternative) — self-hosted proxy with the same multi-provider benefit. Preferred when teams require on-premise routing or want to avoid third-party intermediaries.

Direct SDK calls are supported for single-provider councils where OpenRouter overhead is not justified.

---

## Frontends

### Svelte + SvelteKit (web)

**Why Svelte over React:**
- Compiles away the framework — no virtual DOM, smaller bundle, faster runtime
- Reactive model is a natural fit for SSE-driven council streaming: events flow into reactive stores with minimal ceremony
- SvelteKit provides routing, server-side rendering, and API routes out of the box
- Lighter than React for a developer tool where bundle size and initial load time matter

**Why not Flutter web:**
- Flutter web's CanvasKit renderer ships ~2 MB+ before application code
- Initial load is noticeably slower than any JS framework
- Browser feel (text selection, scrolling, right-click) is subtly wrong compared to native HTML
- Acceptable for public-facing apps that prioritise cross-platform code; not the right trade-off for a developer tool where the web surface is primary

**SvelteKit** handles:
- Council dashboard (live stage streaming via SSE)
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
- Local development experience (Astrocyte in library mode, full observability)
- MIP routing trace viewer

**Flutter mobile** — primary use cases:
- Push notifications when a council concludes
- Reading council verdicts and session history
- Approving or rejecting pending decisions
- Not a council creation surface

**Why not Flutter for web:**
- See Svelte rationale above. The web surface is the primary browser experience; it should feel like the web.
- Flutter desktop + Flutter mobile share code without needing Flutter web.

---

## Monorepo tooling

**pnpm + Turborepo** — manages the JavaScript/TypeScript packages (`web/`, `packages/`). Turborepo handles build caching and task orchestration across the frontend workspace.

**uv workspaces** — manages Python packages within the backend.

**Docker Compose** — local development stack: Synapse backend + pgvector. Astrocyte in library mode reads `astrocyte.yaml` directly.

---

## API contract

The backend emits an **OpenAPI schema** at `/openapi.json`. Typed clients are generated from this schema for both frontend surfaces:

| Consumer | Generated client |
|---------|-----------------|
| Svelte web | TypeScript client via `openapi-typescript` |
| Flutter desktop + mobile | Dart client via `openapi-generator` |

This ensures frontend types stay in sync with the backend without manual maintenance.

**SSE** — used for council stage streaming (backend → frontend). One-directional; sufficient for the current deliberation model. WebSocket is a future option if bi-directional interaction (human joining a live council mid-session) is added.

---

## Authentication

**JWT (RS256)** — Synapse validates tokens from a configured OIDC provider. The JWT subject and claims are mapped to an `AstrocyteContext` passed to all memory operations.

Matches Astrocyte gateway's `jwt_oidc` auth mode so the same token works across both services in gateway deployments.

**MCP access** — API key auth with per-key bank scoping. Agent identities are tracked as `agent:{name}` principals in Astrocyte audit logs.

---

## Decision log

| Decision | Chosen | Alternatives considered | Reason |
|----------|--------|------------------------|--------|
| Backend language | Python | TypeScript (Node) | Astrocyte library compatibility; shared ecosystem |
| Web framework | FastAPI | Django, Flask | Async-native; SSE; auto OpenAPI |
| Web frontend | Svelte | React, Vue | Smaller bundle; better SSE reactive model; lighter for dev tool |
| Desktop | Flutter | Tauri, Electron | One codebase with mobile; native rendering; no JS bridge |
| Mobile | Flutter | React Native, Expo | Shared with desktop; performance; no bridge |
| Flutter web | Not used | Flutter web | Bundle size; browser feel; Svelte is better for web |
| Package manager (Py) | uv | pip, Poetry | Speed; Astrocyte consistency |
| Package manager (JS) | pnpm + Turborepo | npm, yarn, nx | Monorepo-native; build caching |
| LLM access | OpenRouter (default) | LiteLLM, direct SDKs | Multi-model; single auth; council flexibility |
| Streaming | SSE | WebSocket, polling | Sufficient for one-directional stage events; simpler than WS |
| Auth | JWT RS256 / OIDC | API key only | Matches Astrocyte gateway; multi-tenant ready |
