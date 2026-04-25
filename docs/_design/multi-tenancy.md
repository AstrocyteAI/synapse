# Multi-tenancy and billing

This document defines workspace isolation, usage tracking, quota enforcement, and billing in Synapse for SaaS deployments.

---

## 1. Overview

Multi-tenancy enables a single Synapse deployment to serve multiple independent organisations (tenants). Each tenant has:
- Complete isolation of councils, verdicts, and memory banks
- Independent RBAC configuration
- Separate usage quotas and billing
- Their own MIP routing rules and council templates (optional)

Multi-tenancy is relevant for **hosted SaaS deployments**. Self-hosted single-tenant deployments can disable it entirely.

---

## 2. Tenant model

A **tenant** maps to a workspace — typically one organisation or team. Users belong to one or more tenants.

```
Tenant (org/workspace)
  ├── Users (with roles)
  ├── API keys
  ├── Councils
  ├── Astrocyte banks (isolated by tenant_id)
  ├── Templates (built-in + custom)
  ├── Webhooks
  ├── Notification preferences
  └── Billing subscription
```

### 2.1 Tenant isolation in Astrocyte

Every Astrocyte call from Synapse includes a `tenant_id` in the `AstrocyteContext`. Astrocyte enforces bank-level isolation — a query from `tenant_acme` cannot access banks belonging to `tenant_beta`.

```python
context = AstrocyteContext(
    principal=f"user:{user_id}",
    tenant_id=jwt.synapse_tenant,   # enforces isolation at memory layer
)
```

Bank naming convention in multi-tenant mode: `{tenant_id}:councils`, `{tenant_id}:precedents`, etc.

### 2.2 Tenant provisioning

Tenants are provisioned automatically on first login via OIDC (the tenant claim in the JWT creates the tenant record) or manually via the admin API.

```http
POST /v1/admin/tenants
{
  "name": "Acme Corp",
  "slug": "acme",
  "plan": "team",
  "owner_email": "alice@acme.com"
}
```

---

## 3. Usage tracking

Synapse tracks usage per tenant for quota enforcement and billing.

### 3.1 Tracked metrics

| Metric | Unit | Billed? |
|--------|------|--------|
| Councils created | count | ✓ |
| LLM tokens consumed | tokens (input + output) | ✓ |
| Astrocyte storage | MB | ✓ (above free tier) |
| Webhook deliveries | count | — |
| API calls | count | — (rate limited, not billed) |

### 3.2 Usage API

```http
GET /v1/usage
  ?from=2025-11-01&to=2025-11-30
→ {
    "councils_created": 142,
    "llm_tokens": 4820000,
    "storage_mb": 128,
    "period": { "from": "...", "to": "..." }
  }
```

Usage data is refreshed every hour. Real-time usage (for quota checks) uses a fast Redis counter.

---

## 4. Quotas

Quotas prevent runaway usage and enable fair resource allocation across tenants.

### 4.1 Quota types

| Quota | Scope | Default (team plan) |
|-------|-------|---------------------|
| `councils_per_day` | Per tenant | 50 |
| `councils_per_user_per_day` | Per user | 10 |
| `max_members_per_council` | Per council | 5 |
| `max_rounds_per_council` | Per council | 3 |
| `api_requests_per_minute` | Per API key | 60 |
| `storage_mb` | Per tenant | 1000 |

### 4.2 Quota enforcement

Quotas are checked before council creation and before each API request:

```python
await quota_service.check(tenant_id, "councils_per_day")
# Raises QuotaExceededError if limit reached
```

Quota checks use Redis atomic counters with TTL-based reset (daily quotas reset at midnight UTC).

### 4.3 Quota exceeded behaviour

When a quota is exceeded:
- API returns `429 Too Many Requests` with a `Retry-After` header
- The response body includes which quota was exceeded and when it resets
- Workspace admin receives a notification

### 4.4 Custom quotas

Admins can request quota increases via the billing portal or by contacting support. Custom quotas override plan defaults and are stored per tenant.

---

## 5. Plans

| Plan | Councils/day | Members/council | Storage | Price |
|------|-------------|----------------|---------|-------|
| **Free** | 5 | 3 | 100 MB | $0 |
| **Team** | 50 | 5 | 1 GB | $49/month |
| **Pro** | 500 | 10 | 10 GB | $199/month |
| **Enterprise** | Unlimited | Unlimited | Custom | Contact |

Plans map to quota configurations stored in the billing database.

---

## 6. Billing integration

Billing uses [Stripe](https://stripe.com) for subscription management and usage-based billing.

### 6.1 Subscription management

```yaml
billing:
  provider: stripe
  stripe_secret_key: ${STRIPE_SECRET_KEY}
  stripe_webhook_secret: ${STRIPE_WEBHOOK_SECRET}
  stripe_publishable_key: ${STRIPE_PUBLISHABLE_KEY}
```

**Billing portal:** available at `/billing` in the web UI (owner role only). Powered by Stripe Customer Portal — no custom billing UI needed.

### 6.2 Usage-based billing

LLM token consumption above plan thresholds is billed as overage at the end of each billing period. Usage snapshots are sent to Stripe as `usage_records` on a daily meter.

```python
stripe.billing.meter_events.create(
    event_name="synapse_llm_tokens",
    payload={
        "stripe_customer_id": tenant.stripe_customer_id,
        "value": daily_token_count,
    },
    timestamp=end_of_day_unix,
)
```

### 6.3 Stripe webhook events handled

| Event | Action |
|-------|--------|
| `customer.subscription.created` | Provision tenant, set plan quotas |
| `customer.subscription.updated` | Update plan quotas |
| `customer.subscription.deleted` | Downgrade to free plan |
| `invoice.payment_failed` | Notify owner, start grace period |
| `invoice.payment_succeeded` | Clear any payment-failed flags |

---

## 7. Tenant administration

### 7.1 Super-admin panel

A super-admin interface (separate from per-tenant admin) for Synapse operators:

```http
GET  /v1/admin/tenants              — list all tenants
GET  /v1/admin/tenants/{id}         — tenant detail + usage
PUT  /v1/admin/tenants/{id}/quotas  — set custom quotas
POST /v1/admin/tenants/{id}/suspend — suspend tenant
DELETE /v1/admin/tenants/{id}       — delete tenant (GDPR)
```

Super-admin routes require a `super_admin` role, distinct from tenant-level `owner`.

### 7.2 Data deletion (GDPR)

Tenant deletion triggers:
1. `Astrocyte.forget()` for all banks in the tenant scope
2. Deletion of all Synapse operational records (councils, schedules, webhooks)
3. Stripe subscription cancellation
4. Confirmation email to the tenant owner

Deletion is irreversible. A 30-day soft-delete period (data retained but inaccessible) is offered before permanent deletion for Enterprise tenants.

---

## 8. Self-hosted deployments

For self-hosted Synapse, multi-tenancy and billing can be disabled:

```yaml
# synapse.yaml
multi_tenancy:
  enabled: false

billing:
  enabled: false
```

In single-tenant mode, all users share one workspace and all quotas are disabled. No Stripe integration is required.

---

## Further reading

- [RBAC](rbac.md) — per-tenant role isolation and owner permissions
- [Architecture](architecture.md) — tenant_id in AstrocyteContext for memory isolation
- [Notifications](notifications.md) — payment failure and quota exceeded notifications
- [Webhooks](webhooks.md) — per-tenant webhook configuration
