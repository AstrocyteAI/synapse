# Synapse architecture

This document defines the layer boundaries, component responsibilities, data flow, and relationship to Astrocyte for the Synapse open-source self-hosted system.

For the council deliberation model, see `council-engine.md`. For technology decisions, see `tech-stack.md`. For the monorepo layout, see `project-structure.md`.

---

## 1. What Synapse is

Synapse is a **multi-agent deliberation system**. It orchestrates councils of AI agents to reason collectively on a question, retains verdicts in Astrocyte memory, and surfaces relevant past decisions when new councils begin.

Synapse owns:
- The **council session lifecycle** — starting, running, and closing deliberation sessions
- The **deliberation pipeline** — structured stages for gathering, ranking, and synthesising agent opinions; multi-round cycles and red team mode
- The **template engine** — built-in and custom council templates with field inheritance
- The **chat layer** — three modes: starting a council via chat, participating during a council (human-in-the-loop), and chatting with a closed verdict via Astrocyte `reflect()`
- The **thread event log** — append-only, cursor-paginated Postgres store of every chat event in a session; the authoritative replay record (distinct from Astrocyte memory, which is the semantic search index)
- The **real-time layer** — Centrifugo sidecar handling all WebSocket and SSE connections; FastAPI publishes events, Centrifugo delivers to clients
- The **event bus and webhook dispatcher** — outbound HMAC-signed webhook delivery of council lifecycle events; export integrations (Notion, Confluence, GitHub, Linear, Markdown)
- The **scheduler** — one-time, recurring (cron), and externally triggered councils
- The **notification system** — email notifications (council concluded, approvals, conflicts, weekly digest) with per-user preferences
- The **RBAC layer** — five roles with JWT claim mapping; API key management with scope enforcement
- The **analytics engine** — member performance, decision velocity, consensus distribution, topic clustering
- The **MCP server** — council tools for agent-to-agent access
- The **frontend API** — REST endpoints and Centrifugo channel tokens consumed by web, desktop, mobile, and messaging integration clients

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
                         │  REST (all API calls)
                         │  WebSocket / SSE (via Centrifugo)
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
│  │  MCP Server  │  │  REST API    │  │  Auth (JWT)  │  │
│  │  (agent      │  │  FastAPI     │  │  python-jose │  │
│  │   access)    │  │              │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  AstrocyteGatewayClient (httpx, gateway only)   │   │
│  │   retain · recall · reflect · forget            │   │
│  └──────────────────────┬──────────────────────────┘   │
│                          │  HTTP publish                 │
│  ┌───────────────────────▼─────────────────────────┐   │
│  │           Centrifugo  (Go sidecar)              │   │
│  │   WebSocket · SSE · presence · history          │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────┘
                          │  HTTP (gateway mode only)
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
- Persists session metadata to PostgreSQL; full transcripts go to Astrocyte

**Orchestrator** (`council/orchestrator.py`):
- Coordinates the three deliberation stages in sequence
- Publishes stage events to Centrifugo after each stage completes — all connected clients receive the event regardless of which backend worker ran the stage
- Calls `AstrocyteGatewayClient.recall()` before Stage 1 to surface relevant precedents
- Calls `AstrocyteGatewayClient.retain()` after Stage 3 to persist the verdict

**Stages** (`council/stages/`):
- `gather.py` — Stage 1: query all council members in parallel via `asyncio.gather`
- `rank.py` — Stage 2: anonymised peer review; each member ranks the others; aggregate scores computed
- `synthesise.py` — Stage 3: chairman model synthesises a final verdict given all Stage 1 responses and Stage 2 rankings

### 3.2 Thread event log

The thread event log is Synapse's chat storage — an append-only `thread_events` table in Postgres that records every event in a conversation in order. It is the authoritative replay record for the chat UI.

Two tables:

- **`threads`** — the chat container. Every council session creates one thread (`council_id` FK). Future standalone chat (no council) also creates threads. Decouples the chat surface from the council lifecycle.
- **`thread_events`** — the event log. `BIGSERIAL` PK is both the global ordering primitive and the pagination cursor. Partitioned by `(thread_id, id DESC)` for efficient history queries.

Event types: `user_message`, `council_started`, `stage_progress`, `member_response`, `ranking_summary`, `verdict`, `reflection`, `precedent_hit`, `summon_requested`, `member_summoned`, `system_event`.

The write path: user messages are appended immediately by the chat router; council lifecycle events are appended by the orchestrator as the pipeline progresses. Centrifugo delivery and Postgres writes are decoupled — the event log is the source of truth; Centrifugo is the delivery mechanism.

History retrieval uses cursor-based pagination on the `id` column (`before_id` / `after_id`) — never SQL `OFFSET`. This is O(1) regardless of history depth, the same pattern used by Discord (Snowflake scan), Slack (`ts`-bounded scan), and Telegram (`pts` cursor).

See `chat.md` section 8 for the full storage design.

### 3.4 AstrocyteGatewayClient

A Python module that wraps all Astrocyte operations via HTTP. Synapse connects to Astrocyte exclusively in **Gateway mode** — there is no in-process library mode.

```python
class AstrocyteGatewayClient:
    async def recall(self, query: str, bank_id: str, context: AstrocyteContext,
                     max_results: int = 5) -> list[MemoryHit]: ...

    async def retain(self, content: str, bank_id: str, tags: list[str],
                     context: AstrocyteContext) -> RetainResult: ...

    async def reflect(self, query: str, banks: list[str],
                      context: AstrocyteContext) -> ReflectResult: ...

    async def forget(self, bank_id: str, memory_ids: list[str],
                     context: AstrocyteContext) -> ForgetResult: ...
```

Every call receives an `AstrocyteContext` constructed from the validated JWT:
```python
context = AstrocyteContext(
    principal=f"user:{jwt.sub}",
    tenant_id=jwt.synapse_tenant,
    role=highest_role(jwt.synapse_roles),
)
```

HTTP calls are made via `httpx` (async). The gateway URL and auth token are read from environment config.

### 3.5 Centrifugo (real-time sidecar)

Centrifugo is a Go binary that manages all persistent client connections — WebSocket for council participants (Modes 1 + 2) and SSE for read-only observers. FastAPI never holds WebSocket connections; it only publishes events.

**Publishing a stage event from Python:**
```python
await centrifugo.publish(
    channel=f"council:{council_id}",
    data={"type": "stage1_complete", "responses": [...]}
)
```

**Client connection flow:**
1. Client calls `GET /v1/centrifugo/token` — FastAPI returns a short-lived Centrifugo connection JWT
2. Client connects to Centrifugo directly with the JWT
3. Client subscribes to `council:{id}` channel
4. FastAPI publishes events; Centrifugo delivers to all subscribers

Centrifugo provides **presence** (who is connected to a channel) and **history** (reconnecting clients catch up on missed events automatically).

### 3.6 MCP Server

Exposes council primitives as MCP tools for agent-to-agent access. Any MCP-capable client (Claude Code, Cursor, Windsurf) can join councils without additional integration.

Tools:
- `start_council` — create a new council session with an initial question
- `join_council` — add an agent to an active session
- `contribute` — submit a response or opinion to the current council stage
- `recall_precedent` — search past council decisions relevant to a query
- `close_council` — finalise the session and persist the verdict

### 3.7 REST API

Consumed by web, desktop, and mobile frontends. All API calls go to FastAPI. Real-time events flow via Centrifugo.

| Endpoint | Transport | Purpose |
|----------|-----------|---------|
| `POST /v1/councils` | REST | Start a new council |
| `GET /v1/councils` | REST | List councils |
| `GET /v1/councils/{id}` | REST | Fetch full council transcript |
| `GET /v1/councils/{id}/thread` | REST | Get the thread ID for a council |
| `GET /v1/centrifugo/token` | REST | Issue Centrifugo connection JWT for a client |
| `POST /v1/threads/{id}/messages` | REST | Send a user message (Modes 1+2) |
| `GET /v1/threads/{id}/events` | REST | Paginated thread history (`before_id` / `after_id` / `limit`) |
| `POST /v1/councils/{id}/chat` | REST | Chat with closed verdict — Mode 3 (`reflect()`) |
| `GET /v1/memory/search` | REST | Search past council decisions |
| `GET /v1/templates` | REST | List and fetch council templates |
| `GET /v1/schedules` | REST | List scheduled and recurring councils |
| `POST /v1/triggers/{name}` | REST | External webhook trigger for a council |
| `GET /v1/webhooks` | REST | Webhook registration and delivery logs |
| `GET /v1/analytics` | REST | Usage, member performance, and consensus metrics |
| `GET /v1/usage` | REST | Per-tenant usage for quota and billing (EE) |
| `POST /v1/api-keys` | REST | API key management (admin+) |
| `GET /health` | REST | Health check |

**Real-time transport by chat mode:**
- Mode 1 (start via chat) — client connects to Centrifugo channel `council:{id}`; stage events arrive as Centrifugo messages; human input is sent to FastAPI via REST
- Mode 2 (human-in-the-loop) — same Centrifugo channel for incoming events; directives (`@redirect`, `@veto`, `@add`) sent to FastAPI via REST
- Mode 3 (chat with verdict) — pure REST; stateless request/response via Astrocyte `reflect()`

### 3.8 Frontends

Three surfaces, one backend API:

**Svelte web** — primary browser interface. Chat is the primary entry point: users type a question, a council is convened, stages stream back into the chat thread via Centrifugo. The same thread supports human-in-the-loop participation (Mode 2) and post-verdict reflection (Mode 3). Memory explorer and admin views sit alongside the chat surface.

**Flutter desktop** — rich client for deep council observation. Full chat capability plus per-member reasoning traces, ranking matrix, memory graph, MIP routing traces, and observability dashboard. Designed for developers and operators who want depth beyond the web UI.

**Flutter mobile** — lightweight read surface. Mode 3 chat only (ask follow-up questions on past verdicts). Push notifications for concluded councils and pending approvals. Not a council creation or participation surface.

---

## 4. Data flow

### 4.1 Council start

```
User (web/desktop) → POST /v1/councils
  → Council Engine: create session
  → AstrocyteGatewayClient.recall(query, bank_id="precedents")
      → retrieve relevant past decisions
  → Stage 1: gather (parallel LLM queries with precedents in context)
  → centrifugo.publish(council:{id}, stage1_complete) → clients render responses
  → Stage 2: rank (anonymised peer review, aggregate scores)
  → centrifugo.publish(council:{id}, stage2_complete) → clients render rankings
  → Stage 3: synthesise (chairman produces verdict)
  → centrifugo.publish(council:{id}, stage3_complete) → clients render verdict
  → AstrocyteGatewayClient.retain(verdict, bank_id="councils", tags=[...])
  → centrifugo.publish(council:{id}, council.closed)
```

### 4.2 Chat flows

**Mode 1 — chat to start:**
```
User message → POST /v1/councils (with question)
  → Council Engine: create session
  → Client subscribes to Centrifugo channel council:{id}
  → Recall precedents from Astrocyte
  → Run stages (progress events published to Centrifugo)
  → Verdict arrives in client's Centrifugo subscription
```

**Mode 2 — human-in-the-loop:**
```
User directive → POST /v1/councils/{id}/directives
  → @redirect → restart current stage with updated question
  → @veto → cancel stage result, await confirmation
  → @add [member] → summon additional model into session at next stage boundary
  → @close → close immediately; current output becomes record
  → Stage continues; updated events published to Centrifugo

Agent-initiated summon (no human directive required):
  → council member includes <<summon>> tag in Stage 1 response
  → orchestrator detects at stage boundary, processes summon
  → if summon_approval: human → emit summon_requested event → await @approve / @reject
  → summoned member receives full context, produces response, joins pool
  → Stage 2 proceeds with expanded member set
```

**Mode 3 — chat with verdict:**
```
User message → POST /v1/councils/{id}/chat (council closed)
  → AstrocyteGatewayClient.reflect(query, banks=["councils"], scope=council_id)
  → Optionally: AstrocyteGatewayClient.recall(query, bank_id="precedents")
  → Synthesised answer + source citations returned (REST response)
```

### 4.3 Agent access via MCP

```
Agent → start_council(question)
  → Council Engine: create session, run stages
  → Returns: session_id, verdict
Agent → recall_precedent(query)
  → AstrocyteGatewayClient.recall(query, bank_id="precedents")
  → Returns: ranked memory hits from past councils
```

### 4.4 Precedent recall

Before every Stage 1 gather, Synapse calls Astrocyte to surface relevant past decisions. These are injected into the council prompt so agents deliberate with institutional memory — not from a blank slate.

```python
precedents = await astrocyte.recall(
    query=council_question,
    bank_id="precedents",
    context=context,
    max_results=5,
)
# Injected into Stage 1 system prompt as context
```

---

## 5. Memory bank layout

Three-tier verdict memory, plus per-agent context:

| Bank | Contents | Written by | Read by |
|------|----------|-----------|--------|
| `councils` | Full session transcripts — all stages, all member responses, rankings | Council Engine (after close) | Admin, desktop UI, Mode 3 reflect |
| `decisions` | Extracted concise verdict + rationale (≤200 words, LLM-summarised) | Council Engine (after close) | All agents, web UI, conflict detection |
| `precedents` | Curated high-quality decisions promoted from `decisions` | Promotion workflow (human or auto) | Council Engine (pre-Stage 1), MCP `recall_precedent` tool |
| `agents` | Per-agent context and identity | Agent-scoped | Per-agent only |

**Write pattern after Stage 3:**

```python
# Full transcript → councils bank
# Includes human turns (Mode 2) + agent responses + verdict
await astrocyte.retain(format_full_transcript(session, human_turns), bank_id="councils", ...)

# Concise verdict → decisions bank (for agent search and conflict detection)
await astrocyte.retain(format_verdict_summary(session), bank_id="decisions", ...)
```

**Write pattern on Mode 3 reflection** (chat router, per Q&A exchange):

```python
# Post-verdict Q&A → councils bank (appended to session memory)
await astrocyte.retain(format_reflection(question, answer, sources), bank_id="councils", ...)
```

**Promotion path:** `decisions` → `precedents`. The promotion workflow (see `workflows.md`) promotes a concise `decisions` entry into `precedents` when confidence is high or a human approves. The full transcript in `councils` is never promoted — it remains the audit record.

MIP routing rules in `mip.yaml` enforce which bank retained content lands in based on content type and tags. Application code does not make routing decisions.

---

## 6. Astrocyte deployment

Synapse connects to Astrocyte exclusively in **Gateway mode**. Gateway mode is language-agnostic HTTP — the Python backend calls the Astrocyte gateway over HTTP the same way any other language would.

| Config key | Purpose |
|---|---|
| `ASTROCYTE_GATEWAY_URL` | Base URL of the running `astrocyte-gateway-py` service |
| `ASTROCYTE_TOKEN` | Auth token for gateway requests |

Synapse holds no Astrocyte configuration beyond the URL and token. Storage providers, MIP routing rules, and bank policies are managed by the Astrocyte gateway deployment.

**Local development stack** (`docker-compose.yml`):
```
synapse-backend   (FastAPI, port 8000)
centrifugo        (Go, port 8001 WS / port 8000 API)
astrocyte-gateway (Python, port 8002)
postgres          (PostgreSQL + pgvector, port 5432)
```

All four services start together with `docker compose up`.

---

## 7. Authentication and authorisation

**AuthN** — Synapse validates JWT tokens (RS256) from the configured OIDC provider via `python-jose`. The JWT subject and claims are mapped to an `AstrocyteContext` (principal, tenant_id, role) and passed to all Astrocyte calls for per-bank access control enforcement.

**AuthZ** — enforced by Astrocyte per bank. Synapse does not duplicate access control logic; it passes identity through.

**Centrifugo auth** — clients obtain a short-lived Centrifugo connection JWT from `GET /v1/centrifugo/token` after authenticating with Synapse. The JWT is signed with `CENTRIFUGO_TOKEN_SECRET` and carries the user ID and allowed channels.

MCP access uses API key auth with per-key bank scoping. Agent identities appear as `agent:{name}` principals in Astrocyte audit logs.

---

## Further reading

- [Council engine](council-engine.md) — deliberation stages in detail, anonymisation strategy, chairman selection
- [Chat](chat.md) — three chat modes, human-in-the-loop directives, Centrifugo, Mode 3 reflect
- [Deliberation](deliberation.md) — multi-round cycles, red team mode, verdict metadata schema
- [Templates](templates.md) — built-in templates, custom templates, inheritance
- [Workflows](workflows.md) — decision lifecycle state machine, conflict detection, approval chains
- [Scheduling](scheduling.md) — scheduled, recurring, and triggered councils
- [Analytics](analytics.md) — member leaderboard, decision velocity, topic clustering
- [RBAC](rbac.md) — roles, permissions, JWT claim mapping, API key scopes
- [Webhooks](webhooks.md) — outbound events, HMAC signing, export integrations
- [SDK](sdk.md) — synapse-py and synapse-ts client libraries
- [Notifications](notifications.md) — email notifications, weekly digest, per-user preferences
- [Multi-tenancy](multi-tenancy.md) — tenant isolation, quotas, Stripe billing (EE)
- [Integrations](integrations.md) — Slack, Teams, Lark bots; event bus; webhook registration
- [Tech stack](tech-stack.md) — technology decisions and rationale
- [Project structure](project-structure.md) — monorepo layout, package conventions, build tooling
- [ADRs](adr/) — recorded architectural decisions
