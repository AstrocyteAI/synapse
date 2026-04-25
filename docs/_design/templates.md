# Council templates

This document defines the council template system — pre-configured council setups for common decision types.

---

## 1. Overview

A template captures a reusable council configuration: members, chairman, roles, tags, approval settings, and prompt guidance. Instead of configuring a council from scratch every time, users reference a template by name.

```
/council --template security-audit Is our OAuth implementation correct?
```

Templates are defined in `synapse.yaml` or managed via the API. Built-in templates ship with Synapse; teams extend them with custom templates scoped to their workspace.

---

## 2. Template schema

```yaml
templates:
  - name: architecture-review
    description: Balanced evaluation of architectural proposals
    council_type: llm
    members:
      - model_id: anthropic/claude-opus-4-7
        name: The Advocate
        role: argue for the proposed approach and highlight its strengths
      - model_id: anthropic/claude-opus-4-7
        name: The Skeptic
        role: find weaknesses, risks, and edge cases in the proposal
      - model_id: openai/gpt-4o
        name: The Pragmatist
        role: assess implementation feasibility and team capacity
    chairman:
      model_id: google/gemini-2-pro
      name: Chair
    tags: [architecture]
    stage2_anonymise: true
    max_precedents: 5
    approval:
      required: true
      quorum: 1                        # 1 approver required
      auto_promote_confidence: high    # skip approval if confidence is high
    prompt_guidance: |
      Focus on long-term maintainability and operational burden.
      Consider the team's current capabilities.
```

**Template fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier used in commands and API |
| `description` | No | Human-readable description shown in UI |
| `council_type` | No | `llm`, `agent`, `mixed`, `solo` (default: `llm`) |
| `members` | No | Member list; falls back to `default_members` if omitted |
| `chairman` | No | Chairman config; falls back to `default_chairman` |
| `tags` | No | Tags applied to all councils using this template |
| `stage2_anonymise` | No | Override global setting |
| `max_precedents` | No | Override global setting |
| `approval` | No | Approval workflow config (see `workflows.md`) |
| `prompt_guidance` | No | Additional instructions appended to all stage prompts |

---

## 3. Built-in templates

Synapse ships with a set of opinionated built-in templates. These can be used as-is or overridden in `synapse.yaml`.

### `architecture-review`
Three-member council with advocate, skeptic, and pragmatist personas. Balanced evaluation of architectural proposals.

### `security-audit`
Security-focused members. Emphasis on attack surface, threat modelling, and compliance.

```yaml
- name: security-audit
  members:
    - model_id: anthropic/claude-opus-4-7
      name: The Attacker
      role: think like an adversary — find every way this can be exploited
    - model_id: openai/gpt-4o
      name: The Defender
      role: propose mitigations and security controls
    - model_id: google/gemini-2-pro
      name: The Compliance Reviewer
      role: check against OWASP, SOC2, GDPR, and relevant standards
  chairman:
    model_id: anthropic/claude-opus-4-7
    name: Security Chair
  tags: [security]
  approval:
    required: true
    quorum: 1
```

### `code-review`
Three general-purpose members reviewing code quality, correctness, and maintainability.

```yaml
- name: code-review
  members:
    - model_id: openai/gpt-4o
      name: GPT-4o
    - model_id: anthropic/claude-sonnet-4-6
      name: Claude
    - model_id: google/gemini-2-pro
      name: Gemini
  tags: [code]
  prompt_guidance: |
    Focus on correctness, edge cases, readability, and test coverage.
    Call out any security concerns explicitly.
```

### `red-team`
Adversarial council. All members are given attacking personas. Output is a risk surface, not a recommendation. See `deliberation.md` for full detail.

```yaml
- name: red-team
  members:
    - model_id: anthropic/claude-opus-4-7
      name: Attacker 1
      role: find technical failure modes
    - model_id: openai/gpt-4o
      name: Attacker 2
      role: find process and human failure modes
    - model_id: google/gemini-2-pro
      name: Attacker 3
      role: find external dependency and supply chain risks
  chairman:
    model_id: anthropic/claude-opus-4-7
    name: Red Team Lead
  council_type: red_team
  tags: [red-team, risk]
  approval:
    required: false
```

### `product-decision`
Product-focused council balancing user needs, business value, and technical feasibility.

```yaml
- name: product-decision
  members:
    - model_id: anthropic/claude-opus-4-7
      name: User Advocate
      role: represent user needs and experience
    - model_id: openai/gpt-4o
      name: Business Analyst
      role: assess business value, revenue impact, and market fit
    - model_id: google/gemini-2-pro
      name: Tech Lead
      role: evaluate technical feasibility and engineering cost
  tags: [product]
```

### `solo`
Single-member council. No peer ranking. Fast reflection using Astrocyte memory.

```yaml
- name: solo
  council_type: solo
  members:
    - model_id: anthropic/claude-opus-4-7
      name: Claude
  tags: [solo]
```

---

## 4. Custom templates

Teams define custom templates in `synapse.yaml` under `templates:`. Custom templates override built-in templates of the same name.

Custom templates can also be created and managed via API:

```http
POST /v1/templates
{
  "name": "incident-retrospective",
  "description": "Post-incident review council",
  "members": [...],
  "chairman": {...},
  "tags": ["incident", "retrospective"],
  "prompt_guidance": "Focus on timeline, root cause, and prevention."
}
```

```http
GET  /v1/templates          — list all templates (built-in + custom)
GET  /v1/templates/{name}   — get template detail
PUT  /v1/templates/{name}   — update custom template
DELETE /v1/templates/{name} — delete custom template (built-ins cannot be deleted)
```

---

## 5. Using templates

**Chat / web:**
```
/council --template security-audit Is our session management secure?
```

**Messaging integrations:**
```
/council --template product-decision Should we add dark mode?
```

**API:**
```http
POST /v1/councils
{
  "question": "Should we adopt event sourcing?",
  "template": "architecture-review"
}
```

**Scheduling:**
```yaml
recurring_councils:
  - name: weekly-security-review
    schedule: "0 10 * * MON"
    question: "Any new security concerns this week?"
    template: security-audit
```

**Overriding template fields at runtime:** individual fields can be overridden per council without modifying the template:

```http
POST /v1/councils
{
  "question": "Should we rewrite in Rust?",
  "template": "architecture-review",
  "overrides": {
    "chairman": { "model_id": "openai/gpt-4o", "name": "Chair" },
    "max_precedents": 10
  }
}
```

---

## 6. Template inheritance

Templates can extend other templates:

```yaml
- name: security-audit-strict
  extends: security-audit
  approval:
    required: true
    quorum: 2                   # Override: require 2 approvers instead of 1
  prompt_guidance: |
    Also check for HIPAA compliance.
    Flag any PHI handling immediately.
```

Fields not specified in the child template are inherited from the parent.

---

## Further reading

- [Council engine](council-engine.md) — member identity and naming, council types
- [Deliberation](deliberation.md) — red team mode, multi-round deliberation
- [Workflows](workflows.md) — approval configuration referenced in templates
- [Scheduling](scheduling.md) — recurring and triggered councils that use templates
