# Council engine

This document defines the deliberation model, session lifecycle, stage pipeline, anonymisation strategy, and memory integration for the Synapse council engine.

For layer boundaries and component responsibilities, see `architecture.md`.

---

## 1. What a council is

A **council** is a structured deliberation session where multiple AI agents or LLM models reason collectively on a question. Councils produce a **verdict** — a synthesised answer that reflects the collective reasoning of all members — which is retained in Astrocyte memory for future recall.

The model draws from two reference implementations:

- **llm-council** (Karpathy) — a 3-stage pipeline: parallel gather → anonymised peer ranking → chairman synthesis. Clean, lightweight, proven.
- **agents-council** (MrLesk) — session-based multi-agent coordination over MCP with async polling and agent summoning.

Synapse combines both: the structured 3-stage pipeline from llm-council with the session model and MCP interface from agents-council, and adds Astrocyte-backed persistent memory that neither reference implementation has.

---

## 2. Session lifecycle

```
start_council(question)
    │
    ▼
[PENDING] ──→ [STAGE_1: gathering] ──→ [STAGE_2: ranking] ──→ [STAGE_3: synthesising]
                                                                       │
                                                               [CLOSED: verdict retained]
```

**States:**

| State | Description |
|-------|-------------|
| `pending` | Session created, precedents being recalled from Astrocyte |
| `stage_1` | Gathering individual responses from all council members in parallel |
| `stage_2` | Members peer-reviewing and ranking each other's responses |
| `stage_3` | Chairman synthesising the final verdict |
| `closed` | Verdict produced and retained to Astrocyte |
| `failed` | Unrecoverable error (all members failed, or chairman failed) |

Sessions can also be **closed early** via `close_council()` — the current stage output becomes the final record.

---

## 3. The three stages

### Stage 1: Gather

All council members receive the same question simultaneously. Relevant precedents recalled from Astrocyte are injected into the system prompt as context.

```
[Recall precedents from Astrocyte]
         │
         ▼
Question + precedents ──→ member_1.complete()  ─┐
                      ──→ member_2.complete()  ─┼── asyncio.gather
                      ──→ member_3.complete()  ─┘
         │
         ▼
Collect responses (graceful: continue if a member fails)
```

**Why precedents in Stage 1:** agents deliberate with institutional memory rather than a blank slate. The council for "should we use event sourcing?" is informed by what past councils decided about the same architecture question.

**Graceful degradation:** if a member fails to respond, Stage 1 continues with the successful responses. Only if all members fail does Stage 1 fail.

### Stage 2: Rank

Each member evaluates all Stage 1 responses and produces a ranked ordering. Responses are anonymised before distribution — members see "Response A", "Response B", not which member produced which response. This prevents prestige bias.

```
Stage 1 responses
    │
    ▼
Anonymise: Response A, B, C, …  (label_to_member mapping retained in session)
    │
    ▼
Ranking prompt ──→ member_1.rank()  ─┐
               ──→ member_2.rank()  ─┼── asyncio.gather
               ──→ member_3.rank()  ─┘
    │
    ▼
Parse rankings (structured format required in prompt)
Compute aggregate scores (average rank position per response)
```

**Anonymisation implementation:**
```python
labels = [chr(65 + i) for i in range(len(stage1_responses))]  # A, B, C, …
label_to_member = {"Response A": "member_id_1", …}
```

De-anonymisation for display happens client-side. The chairman in Stage 3 receives anonymised labels and never knows which response came from which model — the same guarantee holds for synthesis.

**Ranking prompt format** — members must emit a parseable `FINAL RANKING:` section:
```
FINAL RANKING:
1. Response B
2. Response A
3. Response C
```

The prompt enforces this format explicitly. The parser has a fallback: if the structured section is missing, it scans the full response for "Response X" patterns in order.

### Stage 3: Synthesise

The chairman model receives all Stage 1 responses (anonymised) and all Stage 2 rankings, then produces a final synthesised verdict.

```
All Stage 1 responses (anonymised)
All Stage 2 rankings + aggregate scores
         │
         ▼
chairman.complete(synthesis_prompt)
         │
         ▼
Verdict
         │
         ▼
AstrocyteClient.retain(verdict, bank_id="councils", tags=[…])
```

**Chairman selection:** configurable. The chairman can be one of the council members or a separate model designated for synthesis. Defaults to the highest-ranked model in the council config. The chairman is not blinded — it sees which response ranked where, but still does not know which member produced which response.

---

## 4. Human-in-the-loop chat

Humans can join an active council as a named participant via a WebSocket connection. The human's contributions are treated identically to agent contributions — they appear in Stage 1 responses, are included in Stage 2 peer ranking, and inform the chairman's synthesis.

**Participant identity:** `human:{user_id}` — tracked in the session alongside agent members, with the same cursor fields (`lastSeen`, `lastRequestSeen`, `lastFeedbackSeen`).

**Directives** — the human can send structured commands during a session:

| Directive | Effect |
|-----------|--------|
| `@redirect [new question]` | Restarts the current stage with an updated question |
| `@veto` | Cancels the current stage result; requests confirmation before re-running |
| `@close` | Closes the session immediately; current output becomes the record |
| `@add [member]` | Summons an additional model or agent into the council |

Directives are parsed server-side before the message is injected as context. A plain message (no directive) is injected as additional context for the remaining members in the current stage.

**Chat with verdict (Mode 3):** after a council closes, the human can ask follow-up questions via `POST /v1/councils/{id}/chat`. The handler calls `AstrocyteClient.reflect()` scoped to that council's retained memory. This is stateless — no conversation history is managed server-side; the client owns the thread.

---

## 5. Deliberation modes

The council engine supports two deliberation modes depending on the use case:

### Synchronous (pipeline)

The default. Stages run sequentially; the caller awaits the full verdict. Best for question-answering, architecture decisions, code review councils.

### Asynchronous (session-based)

Agents join an active session and contribute asynchronously. The orchestrator collects contributions until a quorum is reached or a timeout fires, then advances the stage. Best for councils involving live agents that check in at different times rather than being queried in parallel.

Async mode uses cursor-based polling (agents call `get_session_data(cursor)` to receive only new contributions since their last check) — the same pattern as agents-council.

---

## 6. Memory integration

Astrocyte memory is woven into the council at three points:

**Before Stage 1 — recall precedents:**
```python
precedents = await client.recall(
    query=council_question,
    bank_id="precedents",
    max_results=5,
    max_tokens=2000,
)
```
Returned hits are formatted and injected into the Stage 1 system prompt.

**After Stage 3 — retain verdict:**
```python
await client.retain(
    content=format_verdict(session),
    bank_id="councils",
    tags=["council", session.topic_tag, session.council_type],
    metadata={
        "session_id": session.id,
        "council_type": session.council_type,
        "member_count": len(session.members),
        "closed_at": session.closed_at.isoformat(),
    },
)
```

**On demand — recall precedent (MCP tool):**
Agents can call `recall_precedent(query)` at any time outside a council to search past decisions. This hits the `precedents` bank — the curated subset promoted from `councils`.

---

## 7. Council types

The engine supports multiple council types, each with different member composition and synthesis strategy:

| Type | Members | Chairman | Use case |
|------|---------|---------|---------|
| `llm` | Multiple LLM models (via OpenRouter) | Configurable model | Question answering, analysis |
| `agent` | Multiple AI agent instances | Designated agent | Multi-agent task coordination |
| `mixed` | LLMs + agents | LLM model | Agents contribute context; LLMs synthesise |
| `solo` | Single member | Same member | Quick recall + reflection without deliberation overhead |

Council type is set at session creation and determines which orchestration path the engine follows.

---

## 8. Streaming

The council engine emits SSE events at each stage boundary. Frontends receive progressive updates without waiting for the full verdict.

| Event | When |
|-------|------|
| `session_created` | Session initialised |
| `precedents_ready` | Astrocyte recall complete; Stage 1 starting |
| `stage1_complete` | All member responses collected |
| `stage2_complete` | Rankings computed, aggregate scores ready |
| `stage3_complete` | Verdict synthesised |
| `session_closed` | Verdict retained to Astrocyte |
| `human_joined` | Human participant connected via WebSocket |
| `human_message` | Human contributed context to current stage |
| `directive_applied` | `@redirect` / `@veto` / `@add` directive executed |
| `member_added` | New member summoned via `@add` |
| `error` | Stage or member failure |

Events carry the stage payload so frontends can render each stage as it completes rather than waiting for the full pipeline.

---

## 9. Member identity and naming

Each council member has a display name separate from their model identity. This matters in three situations: messaging integrations (where model IDs are unreadable), persona-based councils (same model, different roles), and agent councils (distinct agent instances need distinct names).

**Member fields:**

| Field | Required | Purpose |
|-------|----------|---------|
| `model_id` | Yes | The LLM or agent being called (`openai/gpt-4o`, `agent:service-x`) |
| `name` | No | Display name shown in UI and messaging integrations |
| `role` | No | One-line role descriptor injected into the system prompt |
| `system_prompt_override` | No | Full persona or specialisation prompt |

If `name` is omitted, a readable default is derived from the model ID:
- `openai/gpt-4o` → `"GPT-4o"`
- `anthropic/claude-sonnet-4-6` → `"Claude"`
- `google/gemini-2-pro` → `"Gemini"`
- `agent:my-service` → `"my-service"`

**Names are display-only.** The full model identity (`model_id`) is always preserved in transcripts and Astrocyte memory. Stage 2 anonymisation (`Response A / B / C`) replaces names during peer review regardless of naming — this is intentional to prevent prestige bias.

**Example — persona-based council (same model, different roles):**

```yaml
council:
  default_members:
    - model_id: anthropic/claude-opus-4-7
      name: The Advocate
      role: argue for the proposed approach, highlight its strengths
    - model_id: anthropic/claude-opus-4-7
      name: The Skeptic
      role: find weaknesses, edge cases, and risks in the proposal
    - model_id: openai/gpt-4o
      name: The Pragmatist
      role: focus on implementation feasibility and team capacity
  default_chairman:
    model_id: google/gemini-2-pro
    name: Chair
```

**Example — mixed LLM + agent council:**

```yaml
council:
  default_members:
    - model_id: openai/gpt-4o
      name: Atlas
    - model_id: agent:security-reviewer
      name: Guardian
      role: evaluate security implications
    - model_id: anthropic/claude-sonnet-4-6
      name: Claude
```

In messaging integrations, member names appear in stage progress updates and verdict cards instead of raw model IDs. In the web and desktop UI, both name and model ID are shown.

---

## 10. Configuration

Council defaults are set in `synapse.yaml`:

```yaml
council:
  default_members:
    - model_id: openai/gpt-4o
      name: Atlas
    - model_id: anthropic/claude-sonnet-4-6
      name: Claude
    - model_id: google/gemini-2-pro
      name: Gemini
  default_chairman:
    model_id: anthropic/claude-opus-4-7
    name: Chair
  llm_provider: openrouter          # or litellm, direct
  stage2_anonymise: true
  stage1_timeout_seconds: 60
  stage2_timeout_seconds: 60
  stage3_timeout_seconds: 90
  max_precedents: 5
  max_precedent_tokens: 2000

memory:
  mode: library                     # or gateway
  gateway_url: ${ASTROCYTE_GATEWAY_URL}
  gateway_token: ${ASTROCYTE_TOKEN}
```

Individual councils can override members, names, roles, and chairman at session creation.

---

## Further reading

- [Architecture](architecture.md) — full layer model and data flow
- [Chat](chat.md) — three chat modes, directives, WebSocket, Mode 3 reflect
- [Tech stack](tech-stack.md) — LLM provider choices and rationale
- llm-council (Karpathy) — reference for the 3-stage pipeline and anonymisation pattern
- agents-council (MrLesk) — reference for the session model and MCP interface
