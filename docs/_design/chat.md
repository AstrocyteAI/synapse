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
| `@add [member]` | Summons an additional model or agent into the council mid-session |

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
  system_event        @redirect, @veto, member added, etc.
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

## Further reading

- [Council engine](council-engine.md) — session lifecycle, human participant model, stage directives
- [Architecture](architecture.md) — WebSocket endpoint, streaming layer, REST API
- [Project structure](project-structure.md) — chat components in web and Flutter app
