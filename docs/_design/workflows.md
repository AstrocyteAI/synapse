# Decision workflows

This document defines approval chains, conflict detection, council chains, and the full decision lifecycle in Synapse.

---

## 1. Decision lifecycle

A council session produces a verdict. That verdict moves through a lifecycle before becoming an authoritative precedent in Astrocyte memory.

```
council_closed
    │
    ▼
[conflict_check]  ── conflict detected ──→  flagged (human review required)
    │
    │ no conflict
    ▼
[approval_required?]
    │
    ├── no  ──→  auto_retained  ──→  [promote_eligible?]
    │                                      │
    │                                      ├── yes (confidence ≥ threshold)
    │                                      │    ──→  promoted (in precedents bank)
    │                                      │
    │                                      └── no ──→  retained (in councils bank only)
    │
    └── yes ──→  pending_approval
                    │
                    ├── approved ──→  retained ──→  [promote_eligible?]
                    ├── rejected ──→  rejected (retained with rejected tag)
                    └── timed_out ──→  auto_promote or auto_reject (configurable)
```

---

## 2. Conflict detection

Before a verdict is retained to Astrocyte, Synapse checks whether it contradicts an existing precedent.

**How it works:**

```python
# After Stage 3 closes:
precedents = await client.recall(
    query=verdict_text,
    bank_id="precedents",
    max_results=5,
)
conflicts = detect_conflicts(verdict_text, precedents)
```

`detect_conflicts()` uses an LLM to assess whether the new verdict and any recalled precedent are semantically contradictory — not merely different topics.

**Conflict states:**

| State | Meaning | Action required |
|-------|---------|----------------|
| `no_conflict` | No contradiction found | Proceed normally |
| `potential_conflict` | Possible contradiction, low confidence | Flag; human can acknowledge and proceed |
| `conflict` | Clear contradiction with existing precedent | Block retention until acknowledged |

**Conflict notification:** when a conflict is detected, the council originator receives a notification (web alert, messaging integration message) showing:
- The new verdict
- The conflicting precedent(s)
- The nature of the contradiction (LLM-generated explanation)
- Options: acknowledge and retain anyway, reject the new verdict, or trigger a new council to resolve the conflict

**Conflict acknowledgement:**

```http
POST /v1/councils/{id}/acknowledge-conflict
{
  "action": "retain_anyway",      # or "reject" or "re-council"
  "note": "Supersedes the 2024 decision — context has changed"
}
```

When `retain_anyway` is chosen, the conflicting precedent is automatically tagged `superseded` and the new verdict is retained with a `supersedes: [precedent_id]` reference.

---

## 3. Approval chains

Approval governs whether a verdict is retained and whether it is promoted to the `precedents` bank. Configured per template or per council.

### 3.1 Approval configuration

```yaml
approval:
  required: true
  mode: quorum                      # single | quorum | unanimous
  quorum: 1                         # required approvers (for quorum mode)
  approvers:                        # optional: specific user IDs or roles
    - role: admin
    - user: alice@example.com
  timeout_hours: 48
  on_timeout: auto_promote          # auto_promote | auto_reject | escalate
  auto_promote_confidence: high     # skip approval if consensus is "high"
  auto_promote_consensus: 0.9       # or numeric threshold
```

### 3.2 Approval modes

| Mode | Behaviour |
|------|-----------|
| `single` | Any one approver can approve |
| `quorum` | At least `quorum` approvers must approve |
| `unanimous` | All configured approvers must approve |

### 3.3 Approval actions

Approvers act via:
- **Web UI** — approve/reject button on verdict card
- **Desktop app** — same
- **Mobile app** — approve/reject via notification action
- **Messaging integrations** — button on verdict card in Slack/Discord/Teams/etc.
- **API** — `POST /v1/councils/{id}/approve` or `POST /v1/councils/{id}/reject`

### 3.4 Auto-promotion bypass

If `auto_promote_confidence` or `auto_promote_consensus` is set, verdicts meeting the threshold skip approval and are promoted directly:

```
consensus_score = 0.92  ≥  auto_promote_consensus = 0.9
→ Skip approval → Promote to precedents immediately
```

This allows high-confidence decisions to move fast while requiring human review for contentious ones.

### 3.5 Timeout handling

If no action is taken within `timeout_hours`:
- `auto_promote` — promote as if approved (used for non-critical decisions with a deadline)
- `auto_reject` — discard the verdict (used when a decision must not proceed without explicit sign-off)
- `escalate` — notify the next approval tier (e.g., escalate from team lead to CTO)

---

## 4. Council chains

A council chain links multiple councils sequentially, where the output of one feeds as input to the next. Chains enable structured multi-stage decision workflows.

**Example — red team → standard council:**

```yaml
chains:
  - name: robust-architecture-decision
    steps:
      - template: red-team
        question_from: "{{chain.question}}"
        output_as: risk_surface

      - template: architecture-review
        question_from: "{{chain.question}}"
        context: |
          The following risks were identified by a red team review:
          {{risk_surface.risks | format_risks}}
        on_complete: close_chain
```

**Triggering a chain:**

```http
POST /v1/chains/robust-architecture-decision/run
{
  "question": "Should we adopt event sourcing for the order service?"
}
```

**Chain step output variables:**
- `{{step.verdict}}` — the prose verdict from a step
- `{{step.risks}}` — structured risks (red team output)
- `{{step.consensus_score}}` — numeric consensus
- `{{step.confidence_label}}` — high / medium / low

**Chain states:**

```
running_step_1 → step_1_complete → running_step_2 → step_2_complete → chain_complete
```

Each step is a full council session. All sessions in a chain are linked by `chain_id` and can be viewed together in the web/desktop UI.

---

## 5. Decision promotion and demotion

### Promotion

A verdict in the `councils` bank is promoted to `precedents` when:
- A human approver explicitly approves it
- Auto-promotion threshold is met
- An admin promotes it manually via API or UI

Promotion retains the full verdict in `councils` and creates a curated entry in `precedents` with:
- Distilled verdict text (LLM-summarised to ≤200 words)
- Tags and topic classification
- Promoted by / promoted at metadata
- Link back to the full council session

### Demotion

A precedent can be demoted (removed from `precedents`) if superseded, found to be incorrect, or no longer applicable:

```http
POST /v1/precedents/{id}/demote
{
  "reason": "Superseded by council cncl_xyz456",
  "superseded_by": "cncl_xyz456"
}
```

Demotion tags the entry `demoted` in Astrocyte but does not delete it. The full history is preserved.

---

## 6. Audit trail

Every state transition in the decision lifecycle is recorded:

| Event | Recorded |
|-------|---------|
| Council created | creator, timestamp, question, template |
| Stage completed | stage, duration, member responses |
| Conflict detected | conflicting precedent IDs, conflict type |
| Conflict acknowledged | acknowledger, action taken, note |
| Approval requested | approvers notified, timeout |
| Approved / rejected | approver, timestamp, note |
| Auto-promoted | trigger (confidence / consensus threshold), values |
| Promoted to precedents | promoter, distilled text |
| Demoted | demoter, reason, superseded_by |

All audit events are retained in Astrocyte with tag `audit` and are available via:

```http
GET /v1/councils/{id}/audit
GET /v1/precedents/{id}/audit
```

---

## Further reading

- [Council engine](council-engine.md) — session lifecycle, stage pipeline
- [Deliberation](deliberation.md) — red team mode used in council chains
- [Templates](templates.md) — approval configuration in templates
- [RBAC](rbac.md) — who can approve, promote, and demote decisions
- [Analytics](analytics.md) — decision velocity, approval time metrics
