# Webhooks and export integrations

This document defines Synapse's general-purpose outbound webhook system and export integrations that write council verdicts to external knowledge bases.

---

## 1. Outbound webhooks

Synapse emits signed webhook events to registered URLs when council lifecycle events occur. Any external system — CI/CD pipelines, Zapier, custom services — can subscribe.

### 1.1 Events

| Event | When |
|-------|------|
| `council.created` | A council session is created |
| `council.stage_complete` | A stage finishes (stage_1, stage_2, stage_3) |
| `council.closed` | Verdict produced; session closed |
| `council.conflict_detected` | New verdict conflicts with an existing precedent |
| `council.approved` | Verdict approved by a human approver |
| `council.rejected` | Verdict rejected |
| `council.promoted` | Verdict promoted to `precedents` bank |
| `council.demoted` | Precedent demoted |
| `schedule.fired` | A recurring or scheduled council was triggered |
| `trigger.received` | An external trigger was received |

### 1.2 Webhook registration

```yaml
# synapse.yaml
webhooks:
  - name: ci-pipeline
    url: ${CI_WEBHOOK_URL}
    secret: ${CI_WEBHOOK_SECRET}
    events:
      - council.promoted
    filter:
      tags: [architecture]            # Only fire for architecture decisions

  - name: zapier-all-verdicts
    url: ${ZAPIER_WEBHOOK_URL}
    secret: ${ZAPIER_WEBHOOK_SECRET}
    events:
      - council.closed
      - council.promoted

  - name: github-pr-comment
    url: ${GITHUB_WEBHOOK_URL}
    secret: ${GITHUB_WEBHOOK_SECRET}
    events:
      - council.closed
    filter:
      tags: [code-review]
```

Also managed via API:
```http
POST   /v1/webhooks        — register (admin+)
GET    /v1/webhooks        — list
PUT    /v1/webhooks/{id}   — update
DELETE /v1/webhooks/{id}   — remove
POST   /v1/webhooks/{id}/test — send a test event
```

### 1.3 Payload

```json
{
  "event": "council.promoted",
  "webhook_id": "wh_abc123",
  "timestamp": "2025-11-03T14:30:00Z",
  "council": {
    "id": "cncl_abc123",
    "question": "Should we adopt event sourcing?",
    "verdict": "The council recommends event sourcing …",
    "confidence_label": "high",
    "consensus_score": 0.87,
    "tags": ["architecture", "order-service"],
    "template": "architecture-review",
    "closed_at": "2025-11-03T14:22:00Z",
    "promoted_at": "2025-11-03T14:30:00Z"
  }
}
```

### 1.4 Signature verification

Each request includes a `X-Synapse-Signature` header with an HMAC-SHA256 signature of the raw request body, keyed with the webhook secret:

```
X-Synapse-Signature: sha256=abc123…
```

Receivers should verify the signature before processing. Same pattern as GitHub webhook signatures.

### 1.5 Delivery guarantees

- **At-least-once delivery** — Synapse retries failed deliveries with exponential backoff (1s, 5s, 30s, 5m, 30m)
- **Delivery log** — each webhook delivery attempt is logged (`GET /v1/webhooks/{id}/deliveries`)
- **Dead letter** — after 5 failed attempts, the event is marked `failed` and an admin notification is sent

---

## 2. Export integrations

Export integrations write council verdicts directly to external knowledge management systems. They are implemented as webhook consumers backed by Synapse's official export adapters.

### 2.1 Notion

Writes verdicts to a Notion database. Each promoted verdict becomes a Notion page.

**Configuration:**

```yaml
exports:
  notion:
    enabled: true
    token: ${NOTION_TOKEN}
    database_id: ${NOTION_DATABASE_ID}
    on: [council.promoted]
    page_template: |
      # {{verdict.question}}

      **Verdict:** {{verdict.text}}
      **Confidence:** {{verdict.confidence_label}}
      **Date:** {{verdict.closed_at}}
      **Tags:** {{verdict.tags | join(", ")}}
```

**Page properties mapped:**
- Title → council question
- Status → confidence label
- Tags → multi-select from council tags
- Date → council closed_at
- Council ID → relation to audit database (optional)

### 2.2 Confluence

Writes verdicts to a Confluence space. Each verdict creates or updates a page under a configurable parent page.

```yaml
exports:
  confluence:
    enabled: true
    base_url: ${CONFLUENCE_BASE_URL}
    token: ${CONFLUENCE_TOKEN}
    space_key: ARCH
    parent_page_id: ${CONFLUENCE_PARENT_PAGE_ID}
    on: [council.promoted]
    group_by_tag: true              # Creates child pages per tag (e.g. /architecture, /security)
```

### 2.3 GitHub

Posts verdict as a comment on a PR (for code-review councils) or creates a Discussion entry (for architecture decisions).

```yaml
exports:
  github:
    enabled: true
    token: ${GITHUB_TOKEN}
    repo: org/repo
    on: [council.closed]
    filter:
      tags: [code-review]
    target: pr_comment              # pr_comment | discussion | issue_comment
    pr_number_from: trigger.pr_number   # Extract PR number from the trigger payload
```

### 2.4 Linear

Creates a decision record in Linear linked to an issue.

```yaml
exports:
  linear:
    enabled: true
    api_key: ${LINEAR_API_KEY}
    team_id: ${LINEAR_TEAM_ID}
    on: [council.promoted]
    label: decision
    link_issue_from: trigger.issue_id
```

### 2.5 Markdown vault (Obsidian / local files)

Exports promoted verdicts as Markdown files to a local directory or S3 bucket. Designed for teams using Obsidian, Foam, or similar tools as their knowledge base.

```yaml
exports:
  markdown:
    enabled: true
    output_dir: ${MARKDOWN_EXPORT_PATH}   # local path or s3://bucket/prefix
    on: [council.promoted]
    filename_template: "{{closed_at | date}}-{{question | slugify}}.md"
    frontmatter: true
```

**Output example:**

```markdown
---
date: 2025-11-03
tags: [architecture, order-service]
confidence: high
consensus: 0.87
template: architecture-review
council_id: cncl_abc123
---

# Should we adopt event sourcing?

The council recommends event sourcing for the order service …

## Member responses
…
```

---

## 3. Project structure additions

```
apps/backend/synapse/
└── webhooks/
    ├── __init__.py
    ├── dispatcher.py       # Event emission + delivery with retry
    ├── registry.py         # Webhook CRUD and filtering
    ├── signing.py          # HMAC-SHA256 signing and verification
    ├── delivery_log.py     # Delivery attempt tracking
    └── exports/
        ├── __init__.py
        ├── notion.py
        ├── confluence.py
        ├── github.py
        ├── linear.py
        └── markdown.py
```

---

## Further reading

- [Integrations](integrations.md) — messaging platform integrations (also use the webhook event bus internally)
- [Scheduling](scheduling.md) — triggered councils that receive inbound webhooks from external systems
- [Notifications](notifications.md) — email delivery uses the same event bus
- [RBAC](rbac.md) — webhook management requires admin role
