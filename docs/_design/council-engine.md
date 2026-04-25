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
                      ──→ member_2.complete()  ─┼── Task.async_stream
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
               ──→ member_2.rank()  ─┼── Task.async_stream
               ──→ member_3.rank()  ─┘
    │
    ▼
Parse rankings (structured format required in prompt)
Compute aggregate scores (average rank position per response)
```

**Anonymisation implementation:**
```python
labels = [chr(65 + i) for i in range(len(stage1_responses))]
# => ["A", "B", "C", …]
label_to_member = {f"Response {label}": member_id
                   for label, member_id in zip(labels, member_ids)}
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

**Quorum configuration:**

```yaml
council:
  async:
    quorum: majority          # majority | all | N (absolute count)
    stage_timeout_seconds: 300
    on_timeout: advance       # advance (with responses so far) | cancel
```

**Cursor-based polling:** agents call `GET /v1/councils/{id}/state?cursor={cursor}` to receive only new contributions since their last check. Each response returns a `next_cursor` the agent stores for its next poll. This avoids re-processing already-seen data.

```
Agent A joins session → receives cursor=0
Agent A polls state?cursor=0 → receives any new contributions, returns cursor=12
Agent A polls state?cursor=12 → ...
```

**Stage advancement rules:**
- When quorum is reached, the orchestrator closes contribution collection and advances to the next stage. Agents that have not yet contributed are excluded from that stage.
- When `stage_timeout_seconds` elapses without quorum, the `on_timeout` policy applies: `advance` proceeds with responses received so far; `cancel` closes the council with a `timeout` status.

**Contribution deduplication:** if an agent submits more than once to a stage, only the first submission is accepted. Subsequent submissions return `409 Conflict` with the existing contribution.

---

## 6. Memory integration

Astrocyte memory is woven into the council at three points:

**Before Stage 1 — recall precedents:**
```python
precedents = await astrocyte.recall(
    council_question,
    bank_id="precedents",
    context=context,
    max_results=5,
    max_tokens=2000,
)
```
Returned hits are formatted and injected into the Stage 1 system prompt.

**After Stage 3 — retain verdict (two writes):**
```python
# Full transcript → councils bank (auditing, Mode 3 reflect)
await astrocyte.retain(
    format_full_transcript(session),
    bank_id="councils",
    tags=["council", session.topic_tag, session.council_type],
    context=context,
)

# Concise verdict summary → decisions bank (agent search, conflict detection)
await astrocyte.retain(
    format_verdict_summary(session),   # LLM-summarised to ≤200 words
    bank_id="decisions",
    tags=["verdict", session.topic_tag, session.council_type],
    context=context,
)
```

The `decisions` bank holds the searchable, concise verdicts that agents and the conflict detector query. The `councils` bank holds the full verbatim transcript for auditing and Mode 3 chat. Promotion to `precedents` happens from `decisions`, not `councils`.

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
| `solo` | Single member | Same member | Single-model recall + synthesis; no peer ranking overhead |

Council type is set at session creation and determines which orchestration path the engine follows.

### Solo council execution model

`solo` bypasses Stage 2 (ranking) entirely — there is only one member, so peer review has no meaning. The pipeline is:

```
Recall precedents from Astrocyte
    │
    ▼
Stage 1: single member responds to the question (with precedents in context)
    │
    ▼
Stage 3: same member synthesises a verdict from its own Stage 1 response
    │
    ▼
Retain to councils + decisions banks
```

The single member acts as both contributor and chairman. `stage2_complete` is emitted immediately after `stage1_complete` with an empty rankings payload so clients do not need special-case logic for the missing stage.

**When to use `solo`:**
- Quick lookups where deliberation overhead is not justified
- Single-specialist domains where only one model is relevant
- Triggered councils where speed matters more than breadth (e.g., deploy-triggered security check)

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
| `directive_applied` | `@redirect` / `@veto` / `@add` / `@close` directive executed |
| `summon_requested` | Agent or chairman summon detected; awaiting approval |
| `summon_approved` | Human approved a pending summon |
| `summon_rejected` | Human rejected a pending summon |
| `member_summoned` | Summoned member joined and produced their response |
| `summon_cap_reached` | `max_summoned_members` limit reached |
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

## 10. Agent summons

A council member, the chairman, or a human participant can summon an additional specialist into an active session. Summons extend the council with new expertise without restarting it.

### 10.1 Summon sources

| Source | Mechanism | When |
|--------|-----------|------|
| Human participant | `@add [member]` directive (Mode 2) | Any point during an active council |
| Council member | `<<summon>>` tag in Stage 1 response | Detected after Stage 1 responses collected |
| Chairman | `<<summon>>` tag in Stage 3 response | Detected before verdict is finalised |

### 10.2 Agent-initiated summons

A council member can signal during Stage 1 that a specialist is needed by including a structured tag at the end of their response:

```
<<summon: model_id="anthropic/claude-opus-4-7", name="Security Expert",
  reason="This decision has security implications that need specialist review">>
```

The orchestrator strips the tag from the response before Stage 2 distribution (so it does not appear in peer ranking), collects all summon requests from all members, and processes them at the stage boundary before advancing to Stage 2.

### 10.3 Chairman-initiated summons

The chairman can pause Stage 3 synthesis if the Stage 1 responses and Stage 2 rankings leave an important dimension unaddressed:

```
<<summon: model_id="openai/gpt-4o", name="Implementation Lead",
  reason="Need implementation feasibility input before finalising">>
```

When a chairman summon is detected:
1. Stage 3 pauses
2. The summoned member receives the full Stage 1 transcript and reason as context
3. The summoned member produces a focused Stage 1-style response
4. A targeted mini Stage 2 ranking is run (summoned response ranked against the existing top response)
5. Stage 3 resumes with the additional data

### 10.4 Summon flow (Stage 1)

```
Stage 1 responses collected
    │
    ▼
Parse <<summon>> tags (strip from display text)
    │
    ├── no summons → proceed to Stage 2 as normal
    │
    └── summons detected
            │
            ├── summon_approval: human
            │       │
            │       ▼
            │   emit summon_requested event → await human decision
            │       │ approved → continue   │ rejected → drop, proceed
            │
            └── summon_approval: auto
                    │
                    ▼
            Check max_summoned_members cap
                    │
                    ├── cap reached → emit summon_cap_reached, drop request
                    │
                    └── within cap → emit member_summoned event
                            │
                            ▼
                    Summoned member receives:
                      - original question + precedents
                      - summary of Stage 1 responses so far
                      - reason they were summoned
                            │
                            ▼
                    Summoned member produces Stage 1 response
                            │
                            ▼
                    Response added to pool → Stage 2 proceeds with full pool
```

### 10.5 Summoned member prompt

A summoned member receives a specialised prompt rather than the standard Stage 1 prompt:

```python
summoned_prompt = f"""
You have been summoned to join a council deliberation already in progress.

Question: {council_question}

Relevant past decisions:
{formatted_precedents}

The following responses have already been submitted by other council members:
{formatted_stage1_responses}

You were summoned because: {summon_reason}

Please provide your assessment. Focus on aspects not yet covered or dimensions
the existing responses have not addressed.
"""
```

### 10.6 Summon events

| Event | When |
|-------|------|
| `summon_requested` | Member or chairman summon detected; awaiting approval (`summon_approval: human`) |
| `summon_approved` | Human approved the summon request |
| `summon_rejected` | Human rejected the summon request |
| `member_summoned` | Summoned member joined and produced their response |
| `summon_cap_reached` | `max_summoned_members` limit reached; request dropped |

### 10.7 Summons in multi-round mode

Summoned members become full session members from the round they join. They are included in all subsequent rounds automatically — there is no re-summoning needed. Their identity and contributions persist in the session transcript and in Astrocyte memory.

### 10.8 Configuration

```yaml
council:
  summons:
    allow_agent_summons: true       # members can request summons via <<summon>> tag
    allow_chairman_summons: true    # chairman can pause Stage 3 to summon
    summon_approval: auto           # auto | human
    max_summoned_members: 3         # cap per council session
    summoned_member_timeout_seconds: 60
```

Per-council override:

```http
POST /v1/councils
{
  "question": "Should we adopt GraphQL?",
  "summons": { "allow_agent_summons": false }
}
```

---

## 11. Configuration

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
