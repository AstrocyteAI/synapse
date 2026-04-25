# Scheduling and recurrence

This document defines scheduled councils, recurring councils, and triggered councils in Synapse.

---

## 1. Overview

Councils are not always ad-hoc. Teams need to run regular reviews on a schedule, trigger councils automatically from external events, or queue a council to start at a specific time. Synapse supports three scheduling modes:

| Mode | Description | Example |
|------|-------------|---------|
| **Scheduled** | One-time council at a future datetime | `--at "Friday 9am"` |
| **Recurring** | Council on a cron schedule | Weekly architecture review |
| **Triggered** | Council fired by an external event | PR opened, deploy succeeded, metric threshold crossed |

---

## 2. Scheduled councils

A council can be queued to start at a specific datetime. The session is created immediately (status: `scheduled`) and the orchestrator starts it at the configured time.

**Via chat / messaging integration:**

```
/council --at "2025-11-07 09:00" Should we ship the payment refactor this sprint?
/council --at "Friday 9am" Weekly team sync: what are the biggest blockers?
```

**Via API:**

```http
POST /v1/councils
{
  "question": "Should we ship the payment refactor this sprint?",
  "scheduled_at": "2025-11-07T09:00:00Z",
  "template": "architecture-review"
}
```

**Session states for scheduled councils:**

```
scheduled → pending → stage_1 → stage_2 → stage_3 → closed
```

Scheduled councils can be cancelled before they start via `DELETE /v1/councils/{id}` or `/cancel` in the originating chat thread.

---

## 3. Recurring councils

A recurring council runs on a cron schedule. Each firing creates a new council session; the question can be static or templated with dynamic context.

**Configuration (`synapse.yaml`):**

```yaml
recurring_councils:
  - name: weekly-architecture-review
    schedule: "0 9 * * MON"          # Every Monday at 9am UTC
    question: "What architecture decisions need to be made this week?"
    template: architecture-review
    notify:
      channels:
        - slack:#engineering
        - discord:#architecture
      on: [council_closed]

  - name: monthly-security-audit
    schedule: "0 10 1 * *"           # 1st of every month at 10am
    question: "Are there any new security concerns to address this month?"
    template: security-audit
    notify:
      channels:
        - slack:#security
      on: [council_closed]
```

**Dynamic questions** — the question can include template variables resolved at fire time:

```yaml
question: "Sprint {{sprint_number}}: what are the top technical risks?"
context_provider: jira          # Fetches sprint number from Jira at fire time
```

Recurring councils are managed via:
- `GET /v1/schedules` — list all recurring schedules
- `POST /v1/schedules` — create a recurring schedule
- `PUT /v1/schedules/{id}` — update schedule or question
- `DELETE /v1/schedules/{id}` — remove schedule
- `POST /v1/schedules/{id}/fire` — manually trigger one firing

---

## 4. Triggered councils

A council is automatically started when an external event occurs. Synapse exposes a trigger endpoint that external systems call; the trigger maps to a council configuration.

**Trigger endpoint:**

```http
POST /v1/triggers/{trigger_id}
X-Synapse-Signature: sha256=...
Content-Type: application/json

{
  "event": "pr_opened",
  "pr_number": 42,
  "pr_title": "feat: new payment provider integration",
  "author": "alice",
  "diff_url": "https://github.com/org/repo/pull/42/files"
}
```

**Trigger configuration:**

```yaml
triggers:
  - name: pr-code-review
    secret: ${PR_TRIGGER_SECRET}
    question_template: |
      Review this pull request: {{pr_title}} by {{author}}.
      Diff: {{diff_url}}
    template: code-review
    notify:
      channels:
        - slack:#pull-requests
      on: [council_closed]

  - name: deploy-retrospective
    secret: ${DEPLOY_TRIGGER_SECRET}
    question_template: |
      We just deployed to production. Any concerns or observations
      about the {{service}} deployment at {{deployed_at}}?
    template: architecture-review
    auto_close_after_minutes: 30
```

**Common trigger sources:**

| Source | Integration | Event |
|--------|------------|-------|
| GitHub Actions | Webhook to `/v1/triggers/{id}` | PR opened, deploy succeeded |
| GitLab CI | Webhook | Pipeline completed |
| PagerDuty | Webhook | Incident opened/resolved |
| Datadog | Webhook | Monitor alert triggered |
| Zapier / Make | HTTP action | Any connected service |
| Custom CI/CD | HTTP POST | Any build event |

---

## 5. Backend implementation

**Scheduler:** APScheduler (`apscheduler`) running inside the FastAPI process for simple deployments; Celery Beat for production deployments with Redis as the broker.

**Recurring schedule storage:** stored in the `schedules` table (PostgreSQL) alongside the council database, not in Astrocyte (operational data, not memory).

**Trigger authentication:** HMAC-SHA256 signature on the request body using a per-trigger secret. Same pattern as GitHub webhooks.

**Missed firings:** if Synapse is down when a recurring council should have fired, the next startup checks for missed schedules and fires them immediately (configurable: skip missed firings or fire on restart).

---

## 6. Project structure additions

```
apps/backend/synapse/
└── scheduling/
    ├── __init__.py
    ├── scheduler.py        # APScheduler / Celery Beat integration
    ├── recurring.py        # Recurring council management
    ├── triggers.py         # Trigger endpoint handler + HMAC verification
    └── models.py           # Schedule and Trigger Pydantic models
```

New API routes:
- `GET|POST /v1/schedules` — recurring schedule management
- `GET|PUT|DELETE /v1/schedules/{id}` — individual schedule
- `POST /v1/schedules/{id}/fire` — manual trigger
- `POST /v1/triggers/{id}` — external event trigger endpoint

---

## Further reading

- [Templates](templates.md) — pre-configured council setups used by scheduled and triggered councils
- [Notifications](notifications.md) — how council results are delivered after scheduled runs
- [Webhooks](webhooks.md) — general outbound webhook system used by trigger callbacks
