# Deliberation quality

This document defines multi-round deliberation, red team mode, and richer verdict metadata — capabilities that improve the quality and expressiveness of council outputs beyond the standard single-pass pipeline.

---

## 1. Multi-round deliberation

The standard council pipeline is a single pass: gather → rank → synthesise. Some decisions benefit from iteration — a first-pass verdict is critiqued, refined, and a final verdict emerges.

### 1.1 Draft → critique → refine

```
Round 1:  gather → rank → synthesise  →  draft verdict
                                              │
Round 2:  draft verdict fed back as          │
          Stage 1 context                    ▼
          gather (critique) → rank →  refined verdict
          synthesise
```

The round 1 chairman verdict becomes additional context for round 2 Stage 1. Members now respond to a concrete proposal rather than an open question — critiques are sharper, agreements are more informed.

**Configuration:**

```yaml
council:
  multi_round:
    enabled: true
    max_rounds: 3
    convergence_threshold: 0.85     # Stop early if consensus score ≥ 0.85
    round_2_prompt_prefix: |
      The following draft verdict was produced in the previous round.
      Critique it, identify weaknesses, and suggest improvements.
```

**Per-council override:**

```http
POST /v1/councils
{
  "question": "Should we adopt a microservices architecture?",
  "multi_round": { "max_rounds": 2 }
}
```

### 1.2 Convergence threshold and early stopping

If the aggregate consensus score (see section 3) exceeds `convergence_threshold` at the end of any round, deliberation stops early regardless of `max_rounds`. This prevents unnecessary rounds when members already agree.

**Default:** `convergence_threshold: 0.85`. This corresponds to "high consensus" (≥ 0.8) with some headroom. Lowering it (e.g. `0.70`) stops earlier but risks premature closure on contentious questions. Raising it (e.g. `0.95`) forces more rounds but produces higher-confidence verdicts — appropriate for irreversible decisions.

**UX:** when early stopping triggers, the verdict carries a `converged_early: true` flag. The UI displays "Converged after N rounds" rather than showing the configured `max_rounds`. This makes it clear the council didn't terminate unexpectedly.

### 1.3 Summoned members in multi-round deliberation

Members summoned during round 1 (via `@add`, agent `<<summon>>` tag, or chairman summon) become full session members and participate in all subsequent rounds automatically. Their round 1 response is included in every subsequent round's context alongside original members — there is no re-summoning. This means a round 2 that begins with a summoned domain specialist present benefits from that specialist's critique of the draft verdict.

### 1.4 Divergence detection

If consensus score *decreases* between rounds (members diverging rather than converging), the orchestrator flags this and optionally halts:

```yaml
multi_round:
  on_divergence: warn      # warn | halt | continue
```

`warn` — adds a `divergence_detected: true` flag to the verdict metadata and continues. **Default.** Suitable for exploratory or advisory councils where surfacing disagreement is itself useful.
`halt` — closes the session after the current round and surfaces the divergence to the human. Best for high-stakes decisions where a split verdict should not be auto-retained.
`continue` — ignores divergence and runs all configured rounds. Use only when you want the full round history regardless of trajectory.

**Divergence threshold:** a score *decrease* of more than `0.05` between consecutive rounds triggers the divergence flag. Noise-level fluctuations (< 0.05) are ignored.

---

## 2. Red team mode

A red team council is not a deliberation — it is an **attack**. All members are given adversarial personas and tasked with finding every way a proposal can fail. The chairman synthesises an attack surface, not a recommendation.

Red team is a council type (`council_type: red_team`), not a stage modifier. It uses the same pipeline but with different prompts and a different output structure.

### 2.1 Stage differences from standard council

| Stage | Standard | Red team |
|-------|---------|---------|
| Stage 1 prompt | "Evaluate this proposal" | "Find every way this can fail" |
| Stage 2 | Rank by quality of analysis | Rank by severity and novelty of risks identified |
| Stage 3 prompt | "Synthesise a verdict" | "Produce a structured risk surface" |
| Output | Verdict + rationale | Risk register (category, severity, likelihood, mitigation) |

### 2.2 Risk output format

The chairman in red team mode produces a structured risk register rather than a prose verdict:

```json
{
  "council_type": "red_team",
  "risks": [
    {
      "category": "security",
      "description": "JWT tokens are not rotated after privilege escalation",
      "severity": "critical",
      "likelihood": "high",
      "identified_by": ["Attacker 1", "Attacker 2"],
      "mitigation": "Implement token rotation on role change"
    },
    {
      "category": "reliability",
      "description": "No circuit breaker on the payment provider integration",
      "severity": "high",
      "likelihood": "medium",
      "identified_by": ["Attacker 3"],
      "mitigation": "Add circuit breaker with fallback to queue"
    }
  ],
  "summary": "3 critical risks, 4 high risks identified. Primary concern is …"
}
```

### 2.3 Red team + standard council workflow

The recommended pattern for high-stakes decisions:

```
1. Run red team council  →  risk surface
2. Feed risk surface as context into standard council
3. Standard council deliberates with full knowledge of the risks
4. Verdict is informed by the attack surface
```

This can be automated via a council chain (see `workflows.md`).

### 2.4 Built-in red team template

See `templates.md` for the `red-team` built-in template. Red team can also be triggered ad-hoc:

```
/council --type red-team What are the risks of our current auth implementation?
```

---

## 3. Richer verdict metadata

Every council verdict carries structured metadata beyond the prose synthesis. This enables analytics, conflict detection, and richer display in frontends and messaging integrations.

### 3.1 Consensus score

A numeric measure (0–1) of how aligned member rankings were in Stage 2.

```
1.0  — perfect agreement (all members ranked identically)
0.5  — partial agreement
0.0  — complete disagreement (rankings were inverse)
```

**Calculation:** Kendall's W (coefficient of concordance) across all Stage 2 ranking lists.

Mapped to labels for display:
- `≥ 0.8` → `"high"`
- `0.5–0.79` → `"medium"`
- `< 0.5` → `"low"`

### 3.2 Dissent flag

Set to `true` when at least one member's ranking was a statistical outlier — i.e., their preferences diverged significantly from the group consensus. Surfaces a note in the verdict UI: "Note: one member held a significantly different view."

The dissenting member's Stage 1 response is highlighted in the full transcript so users can inspect the minority position.

### 3.3 Uncertainty markers

Sections of the Stage 3 verdict where member responses contradicted each other are marked as uncertain. The chairman is prompted to flag these explicitly:

```
[UNCERTAIN] The optimal database strategy is unclear — two members recommended
PostgreSQL while one recommended a document store. Consider a follow-up council
specifically on data architecture.
```

Uncertainty markers are extracted and stored as structured metadata alongside the prose verdict.

### 3.4 Revision count

The number of deliberation rounds completed before the verdict was closed. Stored in verdict metadata for analytics (decisions requiring more rounds may indicate higher complexity or lower member alignment).

### 3.5 Full verdict schema

```json
{
  "council_id": "cncl_abc123",
  "question": "Should we adopt event sourcing?",
  "verdict": "The council recommends event sourcing for the order service …",
  "confidence_label": "high",
  "consensus_score": 0.87,
  "dissent_detected": false,
  "dissenting_member": null,
  "uncertainty_markers": [],
  "revision_count": 1,
  "member_count": 3,
  "council_type": "llm",
  "duration_seconds": 187,
  "closed_at": "2025-11-03T14:22:00Z",
  "tags": ["architecture", "order-service"],
  "template": "architecture-review",
  "stage1_responses": [...],
  "stage2_rankings": [...],
  "aggregate_scores": {...}
}
```

---

## 4. Verdict display

Frontends and messaging integrations use verdict metadata to enrich display:

| Metadata | Web / Desktop | Messaging integrations |
|---------|--------------|----------------------|
| `consensus_score` | Numeric + label badge | Label only (`High consensus`) |
| `dissent_detected` | Warning banner + highlight outlier | ⚠ icon on verdict card |
| `uncertainty_markers` | Inline annotations in verdict text | Separate line below verdict |
| `revision_count` | Shown if > 1 (`2 rounds`) | Shown if > 1 |
| `confidence_label` | Coloured badge | Text label |

---

## Further reading

- [Council engine](council-engine.md) — standard 3-stage pipeline, member naming
- [Templates](templates.md) — red-team built-in template, multi-round configuration
- [Workflows](workflows.md) — council chains (red team → standard council automation)
- [Analytics](analytics.md) — consensus trends, dissent heatmap, revision count analysis
