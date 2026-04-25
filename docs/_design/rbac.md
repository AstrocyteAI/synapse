# Role-based access control

This document defines the RBAC model for Synapse — roles, permissions, JWT claim mapping, and integration with Astrocyte's access control layer.

---

## 1. Roles

Synapse defines five roles. Roles are assigned per workspace (tenant) and are independent across tenants in multi-tenant deployments.

| Role | Who | Inherits from |
|------|-----|--------------|
| `viewer` | Read-only observers | — |
| `member` | Standard team members | `viewer` |
| `approver` | Decision reviewers | `member` |
| `admin` | Workspace administrators | `approver` |
| `owner` | Billing and tenant owners | `admin` |

---

## 2. Permissions

### Council operations

| Permission | viewer | member | approver | admin | owner |
|-----------|:------:|:------:|:--------:|:-----:|:-----:|
| View council list and history | ✓ | ✓ | ✓ | ✓ | ✓ |
| View council transcripts | ✓ | ✓ | ✓ | ✓ | ✓ |
| Start a council | — | ✓ | ✓ | ✓ | ✓ |
| Join council as participant (Mode 2) | — | ✓ | ✓ | ✓ | ✓ |
| Chat with verdict (Mode 3) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Cancel a council | — | own | ✓ | ✓ | ✓ |
| Close a council early | — | own | ✓ | ✓ | ✓ |

### Decision operations

| Permission | viewer | member | approver | admin | owner |
|-----------|:------:|:------:|:--------:|:-----:|:-----:|
| View verdicts and precedents | ✓ | ✓ | ✓ | ✓ | ✓ |
| Approve / reject a verdict | — | — | ✓ | ✓ | ✓ |
| Promote verdict to precedents | — | — | ✓ | ✓ | ✓ |
| Demote a precedent | — | — | — | ✓ | ✓ |
| Acknowledge conflict | — | — | ✓ | ✓ | ✓ |

### Memory operations

| Permission | viewer | member | approver | admin | owner |
|-----------|:------:|:------:|:--------:|:-----:|:-----:|
| Search memory (recall) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Browse memory banks | ✓ | ✓ | ✓ | ✓ | ✓ |
| Forget / delete memories | — | — | — | ✓ | ✓ |

### Configuration

| Permission | viewer | member | approver | admin | owner |
|-----------|:------:|:------:|:--------:|:-----:|:-----:|
| View templates | ✓ | ✓ | ✓ | ✓ | ✓ |
| Create / edit custom templates | — | — | — | ✓ | ✓ |
| View schedules | ✓ | ✓ | ✓ | ✓ | ✓ |
| Create / edit schedules | — | ✓ | ✓ | ✓ | ✓ |
| View MIP rules (read-only) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Edit MIP rules | — | — | — | ✓ | ✓ |
| Manage webhooks | — | — | — | ✓ | ✓ |
| Manage API keys | — | — | — | ✓ | ✓ |

### Analytics

| Permission | viewer | member | approver | admin | owner |
|-----------|:------:|:------:|:--------:|:-----:|:-----:|
| View analytics dashboard | ✓ | ✓ | ✓ | ✓ | ✓ |
| Export analytics data | — | — | — | ✓ | ✓ |

### User and tenant management

| Permission | viewer | member | approver | admin | owner |
|-----------|:------:|:------:|:--------:|:-----:|:-----:|
| View team members | ✓ | ✓ | ✓ | ✓ | ✓ |
| Invite users | — | — | — | ✓ | ✓ |
| Assign roles | — | — | — | ✓ | ✓ |
| Remove users | — | — | — | ✓ | ✓ |
| View billing and usage | — | — | — | — | ✓ |
| Manage subscription | — | — | — | — | ✓ |
| Delete workspace | — | — | — | — | ✓ |

`own` — a member can perform this action on resources they created.

---

## 3. JWT claim mapping

Synapse validates JWT tokens from the configured OIDC provider. Roles are mapped from JWT claims.

**Claim mapping (configurable in `synapse.yaml`):**

```yaml
auth:
  mode: jwt_oidc
  jwks_url: ${OIDC_JWKS_URL}
  issuer: ${OIDC_ISSUER}
  audience: synapse
  role_claim: synapse_roles          # JWT claim containing role list
  tenant_claim: synapse_tenant       # JWT claim containing tenant ID
  fallback_role: member              # Role assigned if claim is missing
```

**JWT payload example:**

```json
{
  "sub": "user_abc123",
  "email": "alice@example.com",
  "synapse_tenant": "tenant_acme",
  "synapse_roles": ["member", "approver"],
  "iat": 1730000000,
  "exp": 1730003600
}
```

Multiple roles are supported. The effective permissions are the union of all assigned roles.

**Astrocyte context construction:**

```python
context = AstrocyteContext(
    principal=f"user:{jwt.sub}",
    actor=ActorIdentity(
        actor_id=jwt.sub,
        role=highest_role(jwt.synapse_roles),
        type="human",
    ),
    tenant_id=jwt.synapse_tenant,
)
```

This context is passed to all Astrocyte calls so per-bank access control is enforced at the memory layer as well as the API layer.

---

## 4. API key access

API keys are used by:
- Messaging integration bots (one key per integration)
- Scheduled and triggered councils (one key per trigger)
- External services calling the Synapse API
- SDK users in programmatic workflows

**API key properties:**

```json
{
  "key_id": "key_abc123",
  "name": "slack-integration",
  "role": "member",
  "scopes": ["councils:write", "memory:read"],
  "tenant_id": "tenant_acme",
  "created_by": "user_abc123",
  "expires_at": null
}
```

API keys carry a role and an optional scope list. The effective permissions are the intersection of the role's permissions and the key's scopes.

**API key management:**

```http
POST   /v1/api-keys           — create (admin+)
GET    /v1/api-keys           — list (admin+)
DELETE /v1/api-keys/{id}      — revoke (admin+)
```

---

## 5. MCP access

MCP clients (Claude Code, Cursor, Windsurf) authenticate with an API key. The key determines which council tools are available and which memory banks can be read/written.

Agent identities appear in Astrocyte audit logs as `agent:{key_name}`.

---

## 6. Astrocyte bank access grants

Synapse configures Astrocyte bank access grants in `astrocyte.yaml` to match the RBAC model:

```yaml
banks:
  - id: councils
    access_grants:
      - principal: "role:viewer"
        permissions: [read]
      - principal: "role:member"
        permissions: [read]
      - principal: "role:admin"
        permissions: [read, write, forget]
      - principal: "synapse-backend"
        permissions: [read, write, forget, admin]

  - id: precedents
    access_grants:
      - principal: "role:viewer"
        permissions: [read]
      - principal: "role:approver"
        permissions: [read, write]
      - principal: "role:admin"
        permissions: [read, write, forget]

  - id: agents
    access_grants:
      - principal: "agent:*"
        permissions: [read, write]           # Scoped to own bank by MIP
      - principal: "role:admin"
        permissions: [read, write, forget]
```

Synapse Backend always calls Astrocyte with the user's `AstrocyteContext`, so Astrocyte enforces per-principal access control at the memory layer independently of the API layer.

---

## Further reading

- [Architecture](architecture.md) — AuthN / AuthZ layer, JWT validation
- [Multi-tenancy](multi-tenancy.md) — per-tenant role isolation
- [Workflows](workflows.md) — who can approve, promote, demote decisions
- [Webhooks](webhooks.md) — API key scopes for integration access
