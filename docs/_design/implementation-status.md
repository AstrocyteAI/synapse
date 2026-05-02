# Synapse implementation status

A snapshot of what's shipped across the three client surfaces (FastAPI backend, SvelteKit web, Flutter app) and what's deliberately deferred. Source of truth when answering "is X done?".

Last reviewed: 2026-05-02.

---

## 1. Backend (FastAPI · Python)

### 1.1 B-slices — single-tenant Synapse contract

| Slice | Scope | Status |
|---|---|---|
| **B1** | Council session CRUD + thread chat | ✅ |
| **B2** | LLM dispatcher + verdict synthesis | ✅ |
| **B3** | Astrocyte memory binding (`couuncil`/`precedent`/`workspace` banks) | ✅ |
| **B4** | RBAC + JWT auth + API keys (SHA-256 hashed) | ✅ |
| **B5** | Approval workflow + signed action links | ✅ |
| **B6** | Outbound webhooks with HMAC signing + retry | ✅ |
| **B7** | Centrifugo realtime (council events, presence) | ✅ |
| **B8** | Templates + scheduling | ✅ |
| **B9** | OpenAPI contract + drift guard | ✅ |
| **B10** | Notification dispatcher (email + ntfy) | ✅ |
| **B11** | Audit-log engine (cursor pagination, deprecation alias) | ✅ |
| **B12** | Migration export CLI (`migrate_export.py`) | ✅ |
| **S-MT1** | Defense-in-depth tenant isolation across routers + repo helpers | ✅ |
| **S-DSAR** | Basic DSAR pipeline — HMAC-SHA256 certificates, single-system erasure (Synapse Postgres + one Astrocyte). Customers needing JWS dual-mode certificates, cross-tenant DSAR queues, or multi-system erasure attestation should upgrade to Cerebro Enterprise — see [`multi-tenancy.md` §5](multi-tenancy.md) and `cerebro/docs/_design/migration.md`. | ✅ |

### 1.2 X-slices — backend-agnostic contract

| Slice | Scope | Status |
|---|---|---|
| **X-1** | OpenAPI contract drift guard (`@known_unimplemented` allowlist) | ✅ |
| **X-2** | `/v1/info` BackendInfo endpoint (clients detect backend type) | ✅ |
| **X-3** | Contract parity tests vs `synapse-v1.openapi.json` | ✅ |
| **X-4** | Migration export CLI | ✅ |
| **X-5** | Coherence sweep (audit alias, council.approved emit, dispatch_summon, council.failed, tenant scoping) | ✅ |

### 1.3 Multi-tenancy posture

Synapse is **single-tenant EE**. `tenant_id` columns exist for contract alignment with Cerebro and as an audit grouping tag — not as a security boundary. See [`multi-tenancy.md`](multi-tenancy.md).

---

## 2. Web (SvelteKit 5 · `apps/web/`)

| Slice | Scope | Route | Status |
|---|---|---|---|
| **W1** | Login + JWT capture | `/login` | ✅ |
| **W2** | Council list + detail | `/councils`, `/councils/[id]` | ✅ |
| **W3** | Create council + member roster | `/councils/new` | ✅ |
| **W4** | Thread chat (Centrifugo live) | `/councils/[id]/chat` | ✅ |
| **W5** | Verdict view + approve/reject | `/councils/[id]/verdict` | ✅ |
| **W6** | Memory search across banks | `/memory` | ✅ |
| **W7** | Analytics (consensus distribution, velocity, members) | `/analytics` | ✅ |
| **W8** | Backend badge (X-2 driven) | global header | ✅ |
| **W9** | Notification preferences + feed | `/settings/notifications`, `/notifications` | ✅ |
| **W10** | Admin audit log viewer | `/admin/audit-log` | ✅ |

State: Svelte 5 runes (`$state`, `$derived`, `$effect`); `authStore` + `backendStore` as the only globals.

---

## 3. Flutter app (`apps/synapse_app/`)

| Slice | Scope | Status |
|---|---|---|
| **F1** | Council list + detail + thread chat (mobile + macOS) | ✅ |
| **F2** | Memory search + analytics screens | ✅ |
| **F3 Phase 1** | Push via ntfy long-poll + `flutter_local_notifications` | ✅ |
| **F3 Phase 2** | Native APNs for iOS-killed-app delivery | ❌ — see §5 |
| **F-extend** | Backend badge, notification preferences UI, device registration | ✅ |

`NotificationService` (`lib/core/notifications/notification_service.dart`):

- `initialize()` — permission prompt + topic seed + local-notifications plugin init (idempotent)
- `ensureTopic()` — UUID-v4 topic persisted via `shared_preferences`
- `startListening()` / `stopListening()` — long-poll `https://ntfy.sh/{topic}/json` and surface as OS notifications

Wired from `_SynapseAppState.initState` in `lib/app.dart`. Routes added: `/notifications`, `/settings/notifications`, `/memory`, `/analytics`.

Known limitation: ntfy long-poll drops when the iOS app is fully killed. Native APNs is the F3-Phase-2 fix; deferred until an iOS-critical use case justifies the credential management.

---

## 4. Astrocyte gateway integration

| Endpoint | Purpose | Status |
|---|---|---|
| `POST /v1/recall` | Multi-bank memory recall | ✅ |
| `POST /v1/imprint` | Council/verdict persistence with tags | ✅ |
| `POST /v1/reflect` | Aggregations for analytics + digest | ✅ |
| `POST /v1/dsar/forget_principal` | DSAR erasure across all `principal:{principal}`-tagged memories in a tenant's banks | ✅ — `astrocyte_gateway/app.py`, 6 tests in `test_dsar_forget_principal.py` |

Synapse uses banks `councils`, `precedents`, `workspace`. Cerebro uses tenant-prefixed banks (`{tenant_id}:councils`, etc.). The `forget_principal` endpoint enumerates the tenant's banks and erases all rows tagged `principal:{principal}`.

---

## 5. Open work

In priority order:

1. **F3 Phase 2 — iOS APNs.** Native push channel for when the app is killed. Requires APNs auth key + a backend dispatch path that picks ntfy vs APNs by platform. ~3 days.
2. **Cross-backend e2e migration test.** Spin up Synapse + Cerebro side-by-side in CI, run `migrate_export.py`, import into Cerebro, assert round-trip integrity. ~1 day.
3. **Background isolate for ntfy when app suspended (Android).** iOS lifecycle limits this; Android has more headroom. ~1 day.
4. **MT-1 isolation hardening.** Defense-in-depth `tenant_id` filtering on every router (currently partial). Single-tenant doesn't *need* it, but free hardening for the migration story. ~½ day.

---

## 6. What this codebase will not do

| Item | Why |
|---|---|
| Multi-tenancy | That's Cerebro — a separate Elixir/Phoenix backend with the same REST contract |
| Quota enforcement | Cerebro |
| Stripe billing | Cerebro |
| Tenant admin UI | Cerebro Control Plane (`apps/control_plane/`) |

---

## See also

- [`architecture.md`](architecture.md) — component architecture
- [`backend-contract.md`](backend-contract.md) — `synapse-v1.openapi.json` contract
- [`notifications.md`](notifications.md) — email + ntfy + preferences
- [`multi-tenancy.md`](multi-tenancy.md) — single-tenant positioning + when to switch to Cerebro
- `../../cerebro/docs/_design/implementation-status.md` — Cerebro counterpart
