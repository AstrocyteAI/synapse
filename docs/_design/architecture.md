# Synapse architecture

This document defines the layer boundaries, component responsibilities, data flow, and relationship to Astrocyte for the Synapse system.

For the council deliberation model, see `council-engine.md`. For technology decisions, see `tech-stack.md`. For the monorepo layout, see `project-structure.md`.

---

## 1. What Synapse is

Synapse is a **multi-agent deliberation system**. It orchestrates councils of AI agents to reason collectively on a question, retains verdicts in Astrocyte memory, and surfaces relevant past decisions when new councils begin.

Synapse owns:
- The **council session lifecycle** — starting, running, and closing deliberation sessions
- The **deliberation pipeline** — structured stages for gathering, ranking, and synthesising agent opinions; multi-round cycles and red team mode
- The **template engine** — built-in and custom council templates with field inheritance
- The **chat layer** — three modes: starting a council via chat, participating during a council (human-in-the-loop), and chatting with a closed verdict via Astrocyte `reflect()`
- The **streaming layer** — real-time stage progress to connected frontends via SSE; bi-directional WebSocket for human participants
- The **event bus and webhook dispatcher** — outbound HMAC-signed webhook delivery of council lifecycle events; export integrations (Notion, Confluence, GitHub, Linear, Markdown)
- The **scheduler** — one-time, recurring (cron), and externally triggered councils
- The **notification system** — email notifications (council concluded, approvals, conflicts, weekly digest) with per-user preferences
- The **RBAC layer** — five roles with JWT claim mapping; API key management with scope enforcement
- The **analytics engine** — member performance, decision velocity, consensus distribution, topic clustering
- The **billing integration** — Stripe subscription management, quota enforcement, per-tenant usage metering
- The **MCP server** — council tools for agent-to-agent access
- The **frontend API** — REST, SSE, and WebSocket endpoints consumed by web, desktop, mobile, and messaging integration clients

Synapse does **not** own:
- Memory storage, retrieval, or synthesis — that is Astrocyte
- LLM routing or normalisation — that is the LLM provider (OpenRouter, LiteLLM, direct SDKs)
- Agent orchestration graphs or tool loops — that is the calling agent framework

---

## 2. Layer model

```
┌─────────────────────────────────────────────────────────┐
│                      Frontends                          │
│   Svelte (web)  │  Flutter (desktop)  │  Flutter (mobile) │
│                                                         │
│   Council dashboard · Chat · Memory explorer · Notifications │
└────────────────────────┬────────────────────────────────┘
                         │  REST + SSE + WebSocket
┌────────────────────────▼────────────────────────────────┐
│                  Synapse Backend                        │
│                  FastAPI  ·  Python 3.12+               │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Council Engine                     │   │
│  │  session.py · orchestrator.py · stages/         │   │
│  │  gather → rank → synthesise                     │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  MCP Server  │  │  REST + SSE  │  │  Auth (JWT)  │  │
│  │  (agent      │  │  WebSocket   │  │              │  │
│  │   access)    │  │  (chat)      │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │           AstrocyteClient (abstraction)         │   │
│  │   retain · recall · reflect · forget            │   │
│  └──────────────────────┬──────────────────────────┘   │
└─────────────────────────┼───────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
    ┌─────────▼──────┐    ┌───────────▼────────┐
    │ Library mode   │    │  Gateway mode       │
    │ (in-process)   │    │  HTTP → astrocyte-  │
    │                │    │  gateway-py         │
    └─────────┬──────┘    └───────────┬─────────┘
              └───────────┬───────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                     Astrocyte                           │
│   retain │ recall │ reflect │ forget                    │
│   MIP routing · Policy · PII barriers · Governance      │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│              Storage backends                           │
│         pgvector · Neo4j · Elasticsearch                │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Component responsibilities

### 3.1 Council Engine

The core of Synapse. Manages session state and runs the deliberation pipeline.

**Session management** (`council/session.py`):
- Creates and closes council sessions
- Tracks participants (agents or LLM models), status, and stage
- Persists session metadata; full transcripts go to Astrocyte

**Orchestrator** (`council/orchestrator.py`):
- Coordinates the three deliberation stages in sequence
- Emits SSE events at each stage boundary for streaming frontends
- Calls `AstrocyteClient.recall()` before Stage 1 to surface relevant precedents
- Calls `AstrocyteClient.retain()` after Stage 3 to persist the verdict

**Stages** (`council/stages/`):
- `gather.py` — Stage 1: query all council members in parallel via `asyncio.gather`
- `rank.py` — Stage 2: anonymised peer review; each member ranks the others; aggregate scores computed
- `synthesise.py` — Stage 3: chairman model synthesises a final verdict given all Stage 1 responses and Stage 2 rankings

### 3.2 AstrocyteClient

A thin abstraction that decouples the council engine from Astrocyte's deployment mode.

```python
class AstrocyteClient(Protocol):
    async def retain(self, content, bank_id, tags, metadata) -> RetainResult: ...
    async def recall(self, query, bank_id, max_results) -> list[MemoryHit]: ...
    async def reflect(self, query, banks) -> ReflectResult: ...
    async def forget(self, bank_id, memory_ids) -> ForgetResult: ...
```

Two implementations:
- `LibraryClient` — imports `astrocyte-py` and calls methods in-process (development, single-node)
- `GatewayClient` — calls `astrocyte-gateway-py` over HTTP (production, multi-tenant)

Selected via `SYNAPSE_ASTROCYTE_MODE=library|gateway`. The council engine never branches on this.

### 3.3 MCP Server

Exposes council primitives as MCP tools for agent-to-agent access. Any MCP-capable client (Claude Code, Cursor, Windsurf) can join councils without additional integration.

Tools:
- `start_council` — create a new council session with an initial question
- `join_council` — add an agent to an active session
- `contribute` — submit a response or opinion to the current council stage
- `recall_precedent` — search past council decisions relevant to a query
- `close_council` — finalise the session and persist the verdict

### 3.4 REST API + real-time endpoints

Consumed by web, desktop, and mobile frontends.

| Endpoint | Transport | Purpose |
|----------|-----------|---------|
| `POST /v1/councils` | REST | Start a new council |
| `GET /v1/councils` | REST | List councils |
| `GET /v1/councils/{id}` | REST | Fetch full council transcript |
| `GET /v1/councils/{id}/stream` | SSE | Stage progress stream (read-only observers) |
| `WS /v1/councils/{id}/chat` | WebSocket | Bi-directional chat — Mode 1, Mode 2 (human participant) |
| `POST /v1/councils/{id}/chat` | REST | Chat with closed verdict — Mode 3 (`reflect()`) |
| `GET /v1/memory/search` | REST | Search past council decisions |
| `GET /v1/templates` | REST | List and fetch council templates |
| `GET /v1/schedules` | REST | List scheduled and recurring councils |
| `POST /v1/triggers/{name}` | REST | External webhook trigger for a council |
| `GET /v1/webhooks` | REST | Webhook registration and delivery logs |
| `GET /v1/analytics` | REST | Usage, member performance, and consensus metrics |
| `GET /v1/usage` | REST | Per-tenant usage for quota and billing |
| `POST /v1/api-keys` | REST | API key management (admin+) |
| `GET /health` | REST | Health check |

**Transport by chat mode:**
- Mode 1 (start via chat) — WebSocket; council stream events flow back over the same connection
- Mode 2 (human-in-the-loop) — WebSocket; user messages and directives (`@redirect`, `@veto`, `@add`) sent inbound; stage events returned outbound
- Mode 3 (chat with verdict) — REST; stateless request/response via Astrocyte `reflect()`

### 3.5 Frontends

Three surfaces, one backend API:

**Svelte web** — primary browser interface. Chat is the primary entry point: users type a question, a council is convened, stages stream back into the chat thread. The same thread supports human-in-the-loop participation (Mode 2) and post-verdict reflection (Mode 3). Memory explorer and admin views sit alongside the chat surface.

**Flutter desktop** — rich client for deep council observation. Full chat capability plus per-member reasoning traces, ranking matrix, memory graph, MIP routing traces, and observability dashboard. Designed for developers and operators who want depth beyond the web UI.

**Flutter mobile** — lightweight read surface. Mode 3 chat only (ask follow-up questions on past verdicts). Push notifications for concluded councils and pending approvals. Not a council creation or participation surface.

---

## 4. Data flow

### 4.1 Council start

```
User (web/desktop) → POST /v1/councils
  → Council Engine: create session
  → AstrocyteClient.recall(query, bank_id="precedents")
      → retrieve relevant past decisions
  → Stage 1: gather (parallel LLM queries with precedents in context)
  → SSE: stage1_complete → frontend renders individual responses
  → Stage 2: rank (anonymised peer review, aggregate scores)
  → SSE: stage2_complete → frontend renders rankings
  → Stage 3: synthesise (chairman produces verdict)
  → SSE: stage3_complete → frontend renders verdict
  → AstrocyteClient.retain(verdict, bank_id="councils", tags=[...])
  → SSE: complete
```

### 4.2 Chat flows

**Mode 1 — chat to start:**
```
User message → WS /v1/councils/{id}/chat
  → Council Engine: create session
  → Recall precedents from Astrocyte
  → Run stages (progress events stream back over WS)
  → Verdict returned into chat thread
```

**Mode 2 — human-in-the-loop:**
```
User message → WS /v1/councils/{id}/chat (council in progress)
  → Injected as context for current stage members
  → @redirect → restart current stage with updated question
  → @veto → cancel stage result, await confirmation
  → @add [member] → summon additional model into session
  → Stage continues; updated responses stream back over WS
```

**Mode 3 — chat with verdict:**
```
User message → POST /v1/councils/{id}/chat (council closed)
  → AstrocyteClient.reflect(query, banks=["councils"], scope=council_id)
  → Optionally: AstrocyteClient.recall(query, bank_id="precedents")
  → Synthesised answer + source citations returned
```

### 4.3 Agent access via MCP

```
Agent → start_council(question)
  → Council Engine: create session, run stages
  → Returns: session_id, verdict
Agent → recall_precedent(query)
  → AstrocyteClient.recall(query, bank_id="precedents")
  → Returns: ranked memory hits from past councils
```

### 4.3 Precedent recall

Before every Stage 1 gather, Synapse calls Astrocyte to surface relevant past decisions. These are injected into the council prompt so agents deliberate with institutional memory — not from a blank slate.

```python
precedents = await client.recall(
    query=council_question,
    bank_id="precedents",
    max_results=5,
)
# Injected into Stage 1 system prompt as context
```

---

## 5. Memory bank layout

| Bank | Contents | Written by | Read by |
|------|----------|-----------|--------|
| `councils` | Full session transcripts (all stages, all responses) | Council Engine (after close) | Admin, desktop UI |
| `decisions` | Extracted verdicts and rationale | Council Engine | All agents, web UI |
| `precedents` | Curated high-quality decisions promoted from `decisions` | Admin action | Council Engine (pre-Stage 1), MCP tool |
| `agents` | Per-agent context and identity | Agent-scoped | Per-agent only |

MIP routing rules in `mip.yaml` enforce which bank retained content lands in based on content type and tags. Application code does not make routing decisions.

---

## 6. Astrocyte deployment modes

Synapse supports both Astrocyte deployment modes with no change to council logic.

| Mode | `SYNAPSE_ASTROCYTE_MODE` | Transport |
|------|--------------------------|-----------|
| Library | `library` | In-process Python call |
| Gateway | `gateway` | HTTP to `astrocyte-gateway-py` |

In library mode, `astrocyte.yaml` is loaded directly by the Synapse process. In gateway mode, Synapse holds only the gateway URL and auth token; Astrocyte configuration is managed by the gateway deployment.

Enterprise deployments that route outbound HTTP through a credential gateway or MITM-capable TLS stack configure this in `astrocyte.yaml` under `outbound_transport` — transparent to Synapse.

---

## 7. Authentication and authorisation

**AuthN** — Synapse validates JWT tokens (RS256) from the configured OIDC provider. The JWT subject and claims are mapped to an `AstrocyteContext` (principal, actor, tenant) and passed to all Astrocyte calls for per-bank access control enforcement.

**AuthZ** — enforced by Astrocyte per bank. Synapse does not duplicate access control logic; it passes identity through.

MCP access uses API key auth with per-key bank scoping. Agent identities appear as `agent:{name}` principals in Astrocyte audit logs.

---

## Further reading

- [Council engine](council-engine.md) — deliberation stages in detail, anonymisation strategy, chairman selection
- [Chat](chat.md) — three chat modes, human-in-the-loop directives, WebSocket, Mode 3 reflect
- [Deliberation](deliberation.md) — multi-round cycles, red team mode, verdict metadata schema
- [Templates](templates.md) — built-in templates, custom templates, inheritance
- [Workflows](workflows.md) — decision lifecycle state machine, conflict detection, approval chains
- [Scheduling](scheduling.md) — scheduled, recurring, and triggered councils
- [Analytics](analytics.md) — member leaderboard, decision velocity, topic clustering
- [RBAC](rbac.md) — roles, permissions, JWT claim mapping, API key scopes
- [Webhooks](webhooks.md) — outbound events, HMAC signing, export integrations
- [SDK](sdk.md) — synapse-py and synapse-ts client libraries
- [Notifications](notifications.md) — email notifications, weekly digest, per-user preferences
- [Multi-tenancy](multi-tenancy.md) — tenant isolation, quotas, Stripe billing
- [Integrations](integrations.md) — Slack, Teams, Lark bots; event bus; webhook registration
- [Tech stack](tech-stack.md) — why FastAPI, Flutter, Svelte, and the library/gateway split
- [Project structure](project-structure.md) — monorepo layout, package conventions, build tooling
- [ADRs](adr/) — recorded architectural decisions
