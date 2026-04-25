# Notifications

This document defines email notifications, per-user preferences, and the weekly digest in Synapse.

---

## 1. Overview

Not every team member lives in a messaging platform. Email ensures council verdicts, approval requests, and digests reach everyone regardless of which chat apps they use.

Email notifications complement — they do not replace — messaging platform integrations. A user who has both Slack and email configured receives notifications through both unless they opt out of one.

---

## 2. Notification types

### 2.1 Council concluded

Sent when a council closes and produces a verdict.

**Recipients:** the council creator + any watchers configured on the session.

**Contents:**
- Question
- Verdict (full text)
- Confidence label and consensus score
- Member count and duration
- Link to full council in web UI
- Approve / reject buttons (if approval is required)

### 2.2 Approval requested

Sent when a verdict enters `pending_approval` state and the recipient is a configured approver.

**Recipients:** all approvers for the council (role-based or explicitly configured).

**Contents:**
- Question and verdict
- Why approval is required (template config)
- Approve / reject links (signed, one-click action — no login required)
- Approval deadline (timeout_hours)

### 2.3 Conflict detected

Sent when a new verdict conflicts with an existing precedent.

**Recipients:** council creator + workspace admins.

**Contents:**
- New verdict
- Conflicting precedent(s) with explanation of the contradiction
- Acknowledge and retain / reject / re-council action links

### 2.4 Approval timeout warning

Sent 6 hours before an approval timeout fires.

**Recipients:** configured approvers who have not yet acted.

### 2.5 Decision promoted

Sent when a verdict is promoted to the `precedents` bank.

**Recipients:** council creator + workspace members who opted in to promotion notifications.

### 2.6 Weekly digest

A summary of council activity over the past week. Sent every Monday morning (configurable day/time per workspace).

**Contents:**
- Councils started and completed this week
- Decisions promoted to precedents
- Pending approvals (with links)
- Average consensus score for the week
- Top topic clusters
- One highlighted verdict ("Decision of the week" — highest consensus score)

**Recipients:** all workspace members who have not opted out.

---

## 3. Per-user notification preferences

Each user can configure which notifications they receive and via which channels.

**Preference schema:**

```json
{
  "user_id": "user_abc123",
  "email": "alice@example.com",
  "notifications": {
    "council_concluded": {
      "email": true,
      "slack": true
    },
    "approval_requested": {
      "email": true,
      "slack": true,
      "mobile_push": true
    },
    "conflict_detected": {
      "email": true,
      "slack": false
    },
    "decision_promoted": {
      "email": false,
      "slack": true
    },
    "weekly_digest": {
      "email": true,
      "slack": false
    }
  },
  "digest_day": "monday",
  "digest_time": "09:00",
  "digest_timezone": "Asia/Singapore"
}
```

Preferences are managed via:
- Web UI settings page (`/settings/notifications`)
- Desktop app settings
- `PUT /v1/users/me/notifications`

---

## 4. Email rendering

Emails are rendered using a template engine (Jinja2) with a responsive HTML layout.

**Design principles:**
- One clear action per email (approve, view, acknowledge)
- Verdict text rendered in a readable block
- Approve / reject buttons are signed links — no login required for the action
- Plain-text fallback for all emails
- Synapse branding with workspace name in the header

**Signed action links:**

Approve/reject links embed a signed JWT with the action, council ID, and user ID. The link is valid for the approval timeout duration. No session cookie is required — clicking the link performs the action directly.

```
https://synapse.example.com/actions/approve?token=eyJ...
```

---

## 5. Email delivery

**Provider:** configurable SMTP or transactional email service.

```yaml
# synapse.yaml
email:
  provider: smtp                    # smtp | sendgrid | resend | ses
  from: "Synapse <noreply@synapse.example.com>"
  smtp:
    host: ${SMTP_HOST}
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    tls: true
  # or:
  sendgrid:
    api_key: ${SENDGRID_API_KEY}
  resend:
    api_key: ${RESEND_API_KEY}
```

**Delivery queue:** emails are queued and sent asynchronously. Failed deliveries retry with exponential backoff (same pattern as webhooks). Delivery status is logged.

---

## 6. Digest scheduling

The weekly digest is sent via the Synapse scheduler (see `scheduling.md`). The digest is generated fresh each send using Astrocyte `reflect()` over the past week's `councils` bank entries.

Workspace admins can customise the digest schedule:

```yaml
notifications:
  digest:
    day: monday
    time: "09:00"
    timezone: "Asia/Singapore"
    enabled: true
```

---

## 7. Project structure additions

```
apps/backend/synapse/
└── notifications/
    ├── __init__.py
    ├── dispatcher.py       # Routes notification events to email + push
    ├── email/
    │   ├── sender.py       # SMTP / provider adapter
    │   ├── templates/      # Jinja2 HTML + text templates
    │   │   ├── council_concluded.html
    │   │   ├── approval_requested.html
    │   │   ├── conflict_detected.html
    │   │   ├── weekly_digest.html
    │   │   └── base.html
    │   └── signing.py      # Signed action link generation + verification
    └── preferences.py      # User preference management
```

---

## Further reading

- [Webhooks](webhooks.md) — the event bus that triggers notification dispatch
- [Workflows](workflows.md) — approval chain events that trigger approval_requested emails
- [Scheduling](scheduling.md) — weekly digest scheduling
- [RBAC](rbac.md) — notification preferences are per-user; no role restriction on preferences
