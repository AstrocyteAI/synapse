# DSAR — Data Subject Access Request pipeline

Synapse offers a **basic DSAR tier** for single-tenant deployments: HMAC-SHA256-signed fulfilment certificates and single-system erasure across Synapse's Postgres tables plus a single Astrocyte gateway. It exists so a regulated single-tenant Synapse customer (HIPAA, GDPR, MAS Notice 626) can attest to having honoured a subject's right of erasure / access / rectification.

For JWS-detached certificates (RS256, externally verifiable against a published JWKS), cross-tenant DSAR queues, or multi-system erasure attestation, upgrade to **Cerebro Enterprise**. The "you've outgrown Synapse" checklist lives in `cerebro/docs/_design/migration.md §1a`.

---

## 1. Lifecycle

```
                ┌─ approve ──→ approved ── complete ──→ completed (terminal)
                │                                       — pipeline runs,
   pending ─────┤                                       — certificate signed
                │
                └─ reject ───→ rejected (terminal)
```

All transitions are guarded by `synapse.dsar.state_machine.InvalidStatusTransition`. Trying to approve a rejected request, or complete a pending one, fails fast at the data layer instead of producing a row in an inconsistent state.

The state machine is in `synapse/dsar/state_machine.py`; the persistence shape is `DSARRequest` in `synapse/db/models.py` (migration `0009_dsar_requests.py`).

---

## 2. Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/v1/dsar` | any user | Anyone with a valid token may file a request — operators don't gatekeep the *filing*, only the *fulfilment*. |
| `GET` | `/v1/dsar` | admin | List, with optional `?status=` filter |
| `GET` | `/v1/dsar/{id}` | admin | Detail + signed certificate |
| `PATCH` | `/v1/dsar/{id}/approve` | admin | Pending → approved |
| `PATCH` | `/v1/dsar/{id}/reject` | admin | Pending → rejected (terminal) |
| `PATCH` | `/v1/dsar/{id}/complete` | admin | Approved → completed; runs the erasure pipeline + signs the certificate |

`PATCH .../complete` is where the work happens. The request body is empty; the router triggers the pipeline synchronously, signs the certificate from the resulting actions list, and stamps the row.

---

## 3. Erasure pipeline

When `PATCH .../complete` runs against an approved erasure request, the worker (`synapse/dsar/worker.py:run_erasure`) performs six actions in order. Each is independent: a failure on one doesn't roll back the others.

| Action | What it does |
|---|---|
| `synapse_audit_events` | `DELETE FROM audit_events WHERE actor_principal = :p` (scoped by `tenant_id` if set on the request) |
| `synapse_council_members` | Strips the subject from each council's `members` JSON list. Council row itself preserved — verdicts already reference it; breaking the link corrupts the audit chain. If the subject was the council's `created_by`, replaced with `user:erased`. |
| `synapse_notification_prefs` | `DELETE FROM notification_preferences WHERE principal = :p` |
| `synapse_device_tokens` | `DELETE FROM device_tokens WHERE principal = :p` |
| `synapse_api_keys` | `UPDATE api_keys SET revoked_at = NOW() WHERE created_by = :p AND revoked_at IS NULL`. Soft-delete only — audit references would orphan if the row went away. |
| `astrocyte_forget_principal` | `POST /v1/dsar/forget_principal` to the configured Astrocyte gateway. Erases all memory rows tagged `principal:{subject}` across the tenant's banks. Returns per-bank deletion counts which land in the certificate. |

Each action records `{system, action, status, started_at, completed_at|failed_at, ...}` in the certificate's `actions` array.

For non-erasure requests (access / rectification), the pipeline records a single `no_op` action so the certificate still ships and operators can attest "we considered the request and took the appropriate action."

### 3.1 Soft failure on Astrocyte image lag

If the Astrocyte gateway returns 404 or 501 for `/v1/dsar/forget_principal`, the worker records the action as `astrocyte_pending` rather than `failed`. This is the operator-recoverable case: the published Astrocyte image lags Synapse's expectations and the cross-system call simply isn't available yet. Synapse-side erasure has already completed; an operator pins a newer Astrocyte image (or builds from local source — see `cerebro/docs/_design/deployment-modes.md §4.1`) and re-runs the DSAR.

Hard errors (network failures, 5xx other than 501) record `failed` with the error message. The DSAR is still marked `completed` in Synapse — the certificate is the source of truth for what got erased.

---

## 4. Certificate format

The wire shape is identical to the basic Cerebro tier (and also covered by `synapse/dsar/certificate.py`):

```json
{
  "version": 1,
  "format": "synapse-dsar-cert-v1",
  "payload": {
    "request_id": "<uuid>",
    "tenant_id": "<id>" | null,
    "subject_principal": "user:abc",
    "request_type": "erasure",
    "requested_at": "...",
    "completed_by": "user:reviewer",
    "completed_at": "...",
    "actions": [...]
  },
  "signature": {
    "alg": "HMAC-SHA256",
    "value": "<base64url(HMAC(secret, canonical_json(payload)))>"
  }
}
```

The signature covers a **canonical** JSON encoding of `payload` — sorted keys, no whitespace, `(",", ":")` separators — so a verifier in any language re-derives the same byte sequence. The Cerebro Elixir signer uses the equivalent rules.

### 4.1 Verifying a certificate

```python
from synapse.dsar.certificate import verify

with open("certificate.json") as f:
    cert = json.load(f)

# secret comes from the deployment's SYNAPSE_DSAR_SIGNING_SECRET
# env var (or wherever your operator stores it)
ok = verify(cert, secret=secret)
assert ok, "certificate is forged or has been tampered with"
```

`verify` returns `False` on any structural problem (wrong format, swapped secret, malformed base64, tampered payload) rather than raising — verifiers usually want a boolean for audit reports, not stack traces.

### 4.2 Certificate identity vs row identity

The fulfilment certificate is signed by the **completer** (`completed_by`). The DSAR row's `reviewed_by` field carries the **approver**. These can differ when one operator approves and a different operator runs `/complete` (e.g. one approves at end of business; another fulfils overnight). The state machine deliberately does not overwrite `reviewed_by` on completion — both audit trails are preserved.

---

## 5. Configuration

| Env var | Required | Notes |
|---|---|---|
| `SYNAPSE_DSAR_SIGNING_SECRET` | **yes** for production | HMAC-SHA256 secret used to sign fulfilment certificates. The router fails closed with **HTTP 503** on `/complete` if this is empty — better an explicit failure than an unsigned certificate. Generate with `openssl rand -hex 32` and store in your secrets manager. |
| `ASTROCYTE_GATEWAY_URL` | yes | Already required by other Synapse paths. The worker reuses the same client. |
| `ASTROCYTE_TOKEN` | yes | Same. |

Rotating `SYNAPSE_DSAR_SIGNING_SECRET` is a deliberate operational event: previously-issued certificates remain verifiable against the *old* secret only. Operators should archive the old secret alongside the certificates it signed.

---

## 6. What this tier deliberately does not do

- **No JWS detached signatures.** A verifier needs the deployment's HMAC secret. For externally-verifiable attestation against a published JWKS, upgrade to Cerebro Enterprise.
- **No cross-tenant queue.** Synapse is single-tenant; one queue per deployment.
- **No operator UI.** REST endpoints + admin tooling. Cerebro's Control Plane has the review modal, certificate viewer, per-tenant filters.
- **No async job mode for fulfilment.** The pipeline runs synchronously inside `PATCH /complete`. For Synapse-scale workloads (under ~10k councils per request) this is fast enough; if it stops being fast enough, that's a signal to upgrade to Cerebro (Phase 3 has async job polling).
- **No audit-log mirroring to a write-once external sink.** Synapse's audit log lives in Postgres; operators who need long-term tamper-proof retention should mirror events to S3 / Glacier at the application boundary. The hookpoint exists in `synapse/audit.py` but the mirror itself is operator-owned.

---

## 7. DSAR + migration to Cerebro Enterprise

DSAR is **deployment-scoped**. A subject who files a DSAR on Synapse and is then migrated to Cerebro must file again under Cerebro — Synapse-side erasure does not propagate.

Two specific implications:

| Scenario | What happens |
|---|---|
| Subject files DSAR on Synapse, request marked completed, then operator migrates the workspace to Cerebro | The Synapse-side erasure is real and signed. Cerebro starts with the *post-erasure* data set (the rows are already gone in Synapse, so they don't appear in the migration bundle). The certificate stays with Synapse — archive the certificate JSON + the signing secret before decommissioning, otherwise the certificate becomes meaningless. |
| Subject files DSAR on Synapse, then operator migrates the workspace mid-flight (request is in `pending` or `approved` state) | The DSAR row itself does NOT migrate to Cerebro — `dsar_requests` is not in the migration bundle. The subject must file again on Cerebro. Operators should drain the DSAR queue (approve/reject/complete every pending request) before initiating migration. |

The reason DSARs aren't in the migration bundle: **DSAR is a one-shot operational event with cryptographic signing tied to the deployment.** Re-issuing a Cerebro certificate for a Synapse-fulfilled DSAR would require Cerebro's signing identity to attest to actions Cerebro didn't perform, which is exactly the kind of trust break the certificate is meant to prevent. Better to archive the Synapse certificate alongside the signing secret and start fresh on Cerebro.

For the inverse direction — Cerebro Enterprise customers who downsize to single-tenant Synapse — same rule: the Cerebro DSAR queue stays in Cerebro; new DSARs on Synapse are signed under Synapse's HMAC secret.

See `cerebro/docs/_design/migration.md §5` for the full "what cannot be migrated" table.

---

## See also

- [`multi-tenancy.md`](multi-tenancy.md) — basic vs full DSAR comparison
- `cerebro/docs/_design/migration.md` — when to upgrade and how
- `cerebro/docs/_design/control-plane.md` — Cerebro's full DSAR tier
- `synapse/dsar/` — implementation
- `tests/dsar/` — unit-level tests on certificate, state machine, worker
- `tests/routers/test_dsar_router.py` — endpoint-level tests
