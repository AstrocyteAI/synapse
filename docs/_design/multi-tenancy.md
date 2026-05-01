# Multi-tenancy

**Synapse is a single-tenant Enterprise Edition backend.** Multi-tenancy is **not** implemented in this codebase and is **not** on the roadmap.

For deployments that need multiple isolated tenants on shared infrastructure (a SaaS or service-provider model), use **Cerebro** — a separate Elixir/Phoenix backend that implements the same Synapse REST contract with full multi-tenancy, quotas, and billing built in.

---

## 1. What "single-tenant" means in Synapse

One Synapse deployment serves one organisation. Every user authenticated against that deployment is implicitly part of the same tenant. There is no tenant administration UI, no quota enforcement, no per-tenant billing.

Operators control isolation by running **one Synapse process per organisation**, typically with a dedicated database and Astrocyte gateway. Two organisations sharing one Synapse deployment is not a supported configuration.

## 2. Why `tenant_id` columns still exist

Synapse models (`council_sessions`, `audit_events`, `notification_preferences`, etc.) carry a nullable `tenant_id` column. This is **not** a multi-tenancy mechanism — it exists for two reasons:

1. **Contract alignment.** Synapse and Cerebro both implement `synapse-v1.openapi.json`. Keeping the same column shape means an operator can migrate from self-hosted Synapse to managed Cerebro without a schema rewrite.
2. **Future audit grouping.** A single-tenant Synapse can still group audit rows by department or environment via `tenant_id` — used as a categorisation tag, not a security boundary.

Synapse routers do filter by `tenant_id` where the user's JWT carries one (defense in depth), but isolation is **not** the threat model here. A malicious caller with a valid JWT for the deployment is assumed to have access to the deployment's data.

## 3. When to use Cerebro instead

Switch to Cerebro when any of these are true:

- You need to host more than one customer on shared infrastructure
- You need plan-based quotas (councils/day, members/council, storage caps)
- You need Stripe-backed subscription billing and usage metering
- You need a super-admin panel for tenant lifecycle (provision, suspend, delete)
- You need Singapore/EU data-residency segregation across tenants

Cerebro is a separate Elixir/Phoenix backend in its own repository (`~/AstrocyteAI/cerebro`). It exposes the same REST contract as Synapse, so the Svelte web, Flutter desktop/mobile, and SDK clients work against either backend unchanged.

See `cerebro/docs/_design/deployment-modes.md` for Cerebro's hosted SaaS and on-premise single-tenant deployment options.

## 4. EE features that Synapse *does* implement

Single-tenancy ≠ no enterprise features. Synapse EE includes:

| Feature | Lives in |
|---|---|
| Email + ntfy notification dispatch | `synapse/notifications/` |
| Audit log (append-only) | `synapse/audit.py` + `synapse/routers/audit_logs.py` |
| API keys with SHA-256 hashing | `synapse/auth/jwt.py` |
| Outbound webhooks with HMAC signing | `synapse/webhooks/` |
| OIDC/SAML-compatible JWT auth | `synapse/auth/jwt.py` |
| Feature licensing via `FeatureFlags` | `synapse/ee_hooks.py` (OSS) and `ee/license/` (proprietary) |

What Synapse does **not** implement and will not implement: multi-tenancy, quota enforcement, Stripe billing. Those belong in Cerebro.

---

## Further reading

- `cerebro-spec.md` (Cerebro repo) — Cerebro product specification
- `cerebro/docs/_design/deployment-modes.md` — Cerebro hosted vs on-prem modes
- `architecture.md` — Synapse component architecture
- `rbac.md` — single-tenant role model in Synapse
