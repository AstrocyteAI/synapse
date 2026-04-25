# Chat

This document defines the three chat modes in Synapse, their interaction models, backend requirements, and per-surface capabilities.

---

## 1. Overview

Synapse supports three distinct chat interaction modes. They are not mutually exclusive — a single UI session can move between all three:

| Mode | When | What happens |
|------|------|--------------|
| **Chat to start** | No active council | User's message triggers a new council; the council deliberates autonomously |
| **Chat during** | Council in progress | User joins as a participant; contributes context or redirects a stage in real time |
| **Chat with verdict** | Council closed | User asks follow-up questions; Astrocyte `reflect()` synthesises answers from retained council memory |

```
[User types a message]
         │
         ├── no active council  ──→  Mode 1: start a council
         │
         ├── council in progress ──→  Mode 2: join as participant
         │
         └── council closed ──────→  Mode 3: reflect on verdict
```

---

## 2. Mode 1 — Chat to start a council

The chat input is the primary entry point for creating a council. The user types a question; Synapse automatically convenes a council, runs the three stages, and streams the result back into the chat thread.

**User experience:**
```
You:      Should we use event sourcing for the order service?

Synapse:  Starting council (3 members) …

          [Stage 1 – gathering]  GPT-4o · Claude · Gemini responding …
          [Stage 2 – ranking]    Peer review in progress …
          [Stage 3 – synthesis]  Chairman synthesising …

          Verdict: The council recommends event sourcing for the order service.
          Rationale: All three members agreed on auditability and replay benefits.
          Confidence: High (aggregate rank consensus).

          [View full council →]
```

**Backend:** standard `POST /v1/councils` triggered by a chat message. SSE streams stage progress back to the chat thread. No new endpoints required beyond what council creation already uses.

**Memory:** precedents relevant to the question are recalled before Stage 1 and surfaced in the chat thread alongside the verdict ("Based on 2 past decisions …").

---

## 3. Mode 2 — Chat during a council (human-in-the-loop)

The user joins an active council as a named participant. They can inject context the agents are missing, redirect a stage, ask a clarifying question that all members then respond to, or veto a stage result and request a re-run.

**User experience:**
```
[Stage 1 in progress — 2 of 3 members responded]

You:   Wait — the order service also needs to integrate with a legacy
       Oracle system that doesn't support event replay. Factor that in.

Synapse: Injecting context for remaining members …

          GPT-4o (updated):  Given the Oracle constraint, I now recommend
                             a hybrid approach …
```

**Interaction types:**

| Action | Effect |
|--------|--------|
| Send a message | Injected as additional context for the current stage |
| `@redirect` | Restarts the current stage with the human's message as an updated question |
| `@veto` | Cancels the current stage result; requests human confirmation before re-running |
| `@close` | Closes the council immediately; the current stage output becomes the record |
| `@add [member]` | Summons an additional model or agent into the council. The summoned member receives full session context (question, precedents, Stage 1 responses so far) and joins the deliberation at the current stage boundary. |

**Agent-initiated summons** — council members can also request summons autonomously by including a `<<summon>>` tag in their Stage 1 response. The summon surfaces in the chat thread as a `summon_requested` entry. If `summon_approval: human` is configured, the human is prompted to approve or reject before the new member joins. If `summon_approval: auto`, it is handled silently and the `member_summoned` entry appears in the thread. See `council-engine.md` section 10 for the full summon design.

**Backend requirement — WebSocket:**

Mode 2 is bi-directional. SSE (server → client only) is insufficient. The backend adds a WebSocket endpoint alongside the existing SSE stream:

```
WS  /v1/councils/{id}/chat
```

The WebSocket handles:
- Inbound: human messages, directives (`@redirect`, `@veto`, `@close`, `@add`)
- Outbound: stage progress events (same payload as SSE), member responses as they arrive, council state changes

The SSE stream endpoint remains for read-only observers (desktop side panels, mobile). WebSocket is only required for active participants.

**Session model:** the human participant is tracked in the council session the same way an agent is — with a name (`human:{user_id}`), a `lastSeen` cursor, and contribution records. Their messages are included in the Stage 2 ranking alongside agent responses if they contributed in Stage 1.

---

## 4. Mode 3 — Chat with verdict

After a council closes, the chat thread continues as a conversation with the retained council memory. The user asks follow-up questions; Astrocyte `reflect()` synthesises answers from the `councils` bank scoped to that session.

**User experience:**
```
[Council closed — verdict rendered]

You:      Why did the chairman weight Claude's response highest?

Synapse:  Claude's response was ranked first by 2 of 3 members in Stage 2.
          It was the only response that explicitly addressed the Oracle
          integration constraint and proposed a concrete migration path.

You:      What did GPT-4o get wrong?

Synapse:  GPT-4o assumed full event replay capability was available.
          It ranked third because it did not account for the legacy
          system constraint raised during deliberation.

You:      Show me similar past decisions.

Synapse:  Found 2 related decisions in the precedents bank:
          · "Hybrid event sourcing for legacy-constrained services" (2025-11-03)
          · "Oracle integration patterns for event-driven systems" (2025-09-18)
```

**Backend:** new endpoint:

```
POST /v1/councils/{id}/chat
{
  "message": "Why did the chairman weight Claude's response highest?"
}
```

Handler:
1. Calls `AstrocyteClient.reflect(query=message, banks=["councils"], session_scope=council_id)`
2. Returns synthesised answer with source citations
3. Optionally calls `AstrocyteClient.recall(query=message, bank_id="precedents")` to surface related past decisions

This is stateless per request — no conversation history is maintained server-side beyond what is already in Astrocyte memory. The chat thread history is managed client-side.

---

## 5. Capability by surface

| Chat capability | Web | Desktop | Mobile |
|----------------|:---:|:-------:|:------:|
| Chat to start a council (Mode 1) | ✓ | ✓ | — |
| Watch council stream in chat thread | ✓ | ✓ | — |
| Join council as participant (Mode 2) | ✓ | ✓ | — |
| `@redirect` / `@veto` / `@close` directives | ✓ | ✓ | — |
| `@add` to summon a member mid-session | ✓ | ✓ | — |
| Chat with verdict (Mode 3) | ✓ | ✓ | ✓ |
| Related precedents surfaced in chat | ✓ | ✓ | ✓ |
| Full stage detail in chat thread | — | ✓ | — |

Mobile supports Mode 3 only — reading verdicts and asking follow-up questions. Joining an active council from mobile is out of scope for Phase 3.

---

## 6. Chat thread model

The chat thread is a unified view that mixes user messages, council stage events, and verdict output. It is not a separate UI component — it *is* the primary interaction surface.

```
thread entry types:
  user_message        human turn
  council_started     council convened from this message
  stage_progress      stage N starting / complete (collapsible)
  member_response     individual member output (expandable)
  ranking_summary     Stage 2 aggregate (expandable)
  verdict             Stage 3 output (prominent)
  reflection          Mode 3 answer with sources
  precedent_hit       related past decision surfaced
  summon_requested    agent or chairman requested a specialist (pending approval)
  member_summoned     new member joined and contributed their response
  system_event        @redirect, @veto, @add, @close, summon cap reached, etc.
```

Stage progress and member responses are **collapsible** by default — the thread stays readable as a conversation while full detail is one click away.

---

## 7. Transport summary

| Mode | Transport | Direction |
|------|-----------|-----------|
| Mode 1 (start) | SSE | Server → client |
| Mode 2 (during) | WebSocket | Bi-directional |
| Mode 3 (verdict) | REST (POST) | Request / response |

WebSocket is only required for Mode 2. Modes 1 and 3 work without it. The WebSocket connection for Mode 2 degrades gracefully to polling if the client cannot maintain a persistent connection (mobile background state).

---

## 8. Thread storage

### 8.1 Design rationale

Research into Discord, Slack, Facebook Messenger, Microsoft Teams, Telegram, and WhatsApp reveals six canonical patterns that every major chat platform converges on independently of their technology stack. Synapse's thread storage is designed around all six.

**Pattern 1 — Conversation-scoped partition key**

Messages are partitioned by conversation, not by user. Discord partitions on `(channel_id, time_bucket)`. Slack shards MySQL on `channel_id`. Teams partitions Cosmos DB on thread ID. Partitioning by user would require fan-in reads across N user partitions to reconstruct a conversation timeline — O(N) reads for every history load. Partitioning by conversation makes history reads a single-partition scan.

Synapse: `thread_events` is indexed on `(thread_id, id DESC)`. All queries for a thread's history hit one index partition.

**Pattern 2 — Time-embedded monotonic message ID**

Every platform uses message IDs that are both unique and sortable by creation time. Discord uses 64-bit Snowflake IDs (41-bit millisecond timestamp + worker + sequence). Slack uses `ts` (Unix seconds.fractional, unique per channel). Telegram uses a per-conversation `pts` counter. The ID serves double duty: it is the identity of the event AND the sort key, eliminating a secondary timestamp index.

Synapse: `thread_events.id` is a `BIGSERIAL` — a monotonically increasing integer assigned by Postgres on insert. It is both the event identity and the pagination cursor.

**Pattern 3 — Append-only log, cursor-paginated**

Chat history is a time-ordered log. It is never updated (edits are new events). Pagination uses a cursor — the last-seen event ID — not SQL `OFFSET`. Offset queries degrade as history grows (`OFFSET 10000` scans and discards 10,000 rows every time). Cursor queries on a clustered primary key are O(1) regardless of history depth.

Synapse: history queries use `before_id` / `after_id` bounds on the `id` column. `OFFSET` is never used.

**Pattern 4 — Persist first, deliver second**

For platforms with server-side storage (Discord, Slack, Teams, Telegram, Facebook Messenger), the invariant is: write to durable storage before acknowledging delivery. Slack states this explicitly in their engineering blog. Facebook Messenger's Iris queue encodes it structurally: two named cursors — one for persistence, one for delivery — advance independently on the same log.

Synapse: the orchestrator writes to `thread_events` (Postgres) and publishes to Centrifugo as two independent operations. Postgres is the source of truth. Centrifugo is delivery. If Centrifugo is unavailable, events are still persisted and clients can recover on reconnect.

**Pattern 5 — Real-time delivery is a separate system from persistence**

Every platform separates the persistence path from the real-time delivery path. Discord: ScyllaDB (storage) + Gateway WebSocket servers (delivery) are decoupled. Slack: MySQL/Vitess (persistence) + Channel Servers / Gateway Servers (delivery). Transient events — typing indicators, presence, read receipts — bypass the persistence path entirely and go directly to the delivery layer.

Synapse: FastAPI writes to Postgres and publishes to Centrifugo independently. Transient events (typing indicators) are published to Centrifugo directly without touching `thread_events`. Persistent events (messages, stage outcomes) are written to Postgres first, then published.

**Pattern 6 — Fan-out on write for small groups; store-once for large**

For direct messages and small group chats, platforms fan-out on write: the server copies the message to each recipient's delivery queue at send time, enabling O(1) reads per recipient. WhatsApp spawns a parallel Erlang process per recipient. For large groups (Discord channels with thousands of members), messages are stored once and delivered via subscriptions.

Synapse: council sessions are small (typically 3–7 participants). Centrifugo handles fan-out delivery to all channel subscribers — one publish from FastAPI reaches all connected clients. There is no per-recipient copy; the event log stores each event once.

---

Chat thread storage serves a fundamentally different purpose from Astrocyte memory:

| | Thread storage (Postgres) | Astrocyte memory |
|---|---|---|
| **Purpose** | Replay the conversation as it happened | Search by meaning across conversations |
| **Access pattern** | Sequential read from a cursor (time-ordered log) | Semantic similarity search |
| **Scope** | One thread — ordered, complete, lossless | Cross-session — ranked by relevance |
| **Append-only?** | Yes — events are never updated or deleted | No — memories can be promoted, demoted, or forgotten |
| **Who reads it** | Client chat UI (history reload, reconnect recovery) | Council agents (pre-Stage 1), Mode 3 reflect, MCP tools |

A council transcript in Astrocyte is a summarised, semantically-indexed copy of what happened. The thread event log is the authoritative, replay-safe record.

### 8.2 Data model

Two tables, one clean separation of concerns:

**`threads`** — the chat container. Every council session creates exactly one thread. Future standalone chat sessions (not backed by a council) also create threads. The table decouples the chat surface from the council lifecycle so standalone chat can be added without a schema change.

```
threads
  id          UUID          PK
  council_id  UUID          FK → council_sessions.id (nullable — null for standalone chat)
  tenant_id   VARCHAR(128)
  created_by  VARCHAR(256)  principal who opened the thread
  title       TEXT          optional display title (derived from question if council-backed)
  created_at  TIMESTAMPTZ
```

**`thread_events`** — the event log. Append-only. `BIGSERIAL` primary key is the global ordering primitive and the pagination cursor.

```
thread_events
  id          BIGSERIAL     PK  ← global cursor; used for pagination (before_id / after_id)
  thread_id   UUID          FK → threads.id
  event_type  VARCHAR(64)   see event type table below
  actor_id    VARCHAR(256)  user:{sub} | agent:{model_id} | system
  actor_name  VARCHAR(256)  display name
  content     TEXT          message text; null for non-message events
  metadata    JSONB         event-specific structured payload
  created_at  TIMESTAMPTZ
```

Index: `(thread_id, id DESC)` — supports the primary query pattern: "give me the N most recent events in this thread before cursor X."

### 8.3 Event types

| `event_type` | Actor | `content` | `metadata` |
|---|---|---|---|
| `user_message` | `user:{sub}` | message text | `{}` |
| `council_started` | `system` | null | `{council_id, question, member_count}` |
| `stage_progress` | `system` | null | `{stage, status}` — status: `started` \| `complete` |
| `member_response` | `agent:{model_id}` | response text | `{stage, label}` — label: A/B/C (anonymous in Stage 2) |
| `ranking_summary` | `system` | null | `{aggregate_scores, consensus_score}` |
| `verdict` | `system` | verdict text | `{confidence_label, dissent_detected, consensus_score}` |
| `reflection` | `system` | synthesised answer | `{sources: [{memory_id, score}]}` |
| `precedent_hit` | `system` | null | `{memory_id, content_preview, score}` |
| `summon_requested` | `agent:{model_id}` | null | `{requested_model_id, reason}` |
| `member_summoned` | `system` | null | `{model_id, member_name, summoned_by}` |
| `system_event` | `system` | null | `{action}` — action: `redirect` \| `veto` \| `close` \| `add` \| `summon_cap_reached` |

### 8.4 History retrieval

Thread history is fetched with cursor-based pagination — never SQL `OFFSET`. The query pattern:

```sql
-- Load up to 50 events before a cursor (newest-first within the page)
SELECT * FROM thread_events
WHERE thread_id = :thread_id AND id < :before_id
ORDER BY id DESC
LIMIT 50;
```

```sql
-- Load up to 50 events after a cursor (for live-reload after reconnect)
SELECT * FROM thread_events
WHERE thread_id = :thread_id AND id > :after_id
ORDER BY id ASC
LIMIT 50;
```

The `id` value from the first/last event in a page is the next cursor. Clients always have a complete, gap-free view by requesting events `after_id = last_known_id` on reconnect.

### 8.5 Write path

Thread events are written in two places:

1. **User messages** — the chat router writes a `user_message` event immediately when a request is received, before dispatching to the council engine
2. **Council lifecycle events** — the orchestrator writes `council_started`, `stage_progress`, `member_response`, `ranking_summary`, `verdict`, `summon_requested`, `member_summoned`, and `system_event` entries as the pipeline progresses

Centrifugo real-time delivery is **decoupled** from the thread event write. The orchestrator writes to Postgres and publishes to Centrifugo as two independent operations. The event log is the source of truth; Centrifugo is the delivery mechanism.

### 8.6 New endpoints

```
POST /v1/threads/{thread_id}/messages          Send a user message (Modes 1+2)
GET  /v1/threads/{thread_id}/events            Paginated history (cursor: before_id / after_id / limit)
GET  /v1/councils/{id}/thread                  Convenience — returns the thread_id for a council
```

### 8.7 Relationship to Astrocyte memory

Thread events are not written to Astrocyte one-by-one. Instead, Synapse selectively formats and retains the semantically meaningful content at two points:

**At council close** (`orchestrator._retain_to_astrocyte`):

```
thread_events (user_message, member_response, verdict)
        │
        ▼  format_full_transcript()
        │  — includes human turns (Mode 2) + agent responses + verdict
        ├──→ retain → councils bank   (full deliberation context)
        │
        ▼  format_verdict_summary()
        └──→ retain → decisions bank  (concise verdict + confidence)
```

Human `user_message` turns from Mode 2 are interleaved with agent responses in the transcript. Future councils recalling that session see the full deliberation context — what the human contributed, not just what the agents said.

**At each Mode 3 reflection** (chat router, `POST /v1/councils/{id}/chat`):

```
user question + reflection answer + sources
        │
        └──→ retain → councils bank  (appended to the session's memory)
```

Post-verdict Q&A is retained as it happens so it remains queryable by future councils.

**What stays in Postgres only** — structural events with no semantic recall value: `council_started`, `stage_progress`, `ranking_summary`, `summon_requested`, `member_summoned`, `system_event`. These matter for UI replay; they don't need to be in the semantic index.

| Thread event | In Postgres? | In Astrocyte? | Bank | When retained |
|---|:---:|:---:|---|---|
| `user_message` | ✓ | ✓ | `councils` | Council close (in transcript) |
| `council_started` | ✓ | — | — | Structural only |
| `stage_progress` | ✓ | — | — | Structural only |
| `member_response` | ✓ | ✓ | `councils` | Council close (in transcript) |
| `ranking_summary` | ✓ | ✓ | `councils` | Council close (in transcript) |
| `verdict` | ✓ | ✓ | `councils` + `decisions` | Council close |
| `reflection` | ✓ | ✓ | `councils` | At point of occurrence (Mode 3) |
| `precedent_hit` | ✓ | sourced from | `precedents` | Read path |
| `summon_requested` | ✓ | — | — | Structural only |
| `member_summoned` | ✓ | — | — | Structural only |
| `system_event` | ✓ | — | — | Structural only |

---

## Further reading

- [Council engine](council-engine.md) — session lifecycle, human participant model, stage directives
- [Architecture](architecture.md) — WebSocket endpoint, streaming layer, REST API
- [Project structure](project-structure.md) — chat components in web and Flutter app
