# Synapse

**A new kind of chat for the AI age — humans and agents, thinking and acting together.**

Synapse is a group chat platform where humans and AI agents participate as first-class members — talking, deliberating, and taking action together. Built on [Astrocyte](../astrocyte), it retains every decision in governed memory so future sessions can recall what was previously decided.

The name is deliberate: in neuroscience, a synapse is the connection point between neurons where computation happens. Astrocytes mediate and maintain the environment around those synapses. Synapse is the deliberation layer that Astrocyte makes possible.

```
Human ────┐
Agent A ──┼──→ Synapse Council Engine ──→ Verdict + action
Agent B ──┘          │
                      │  retain / recall
                      ▼
                  Astrocyte
              (governed memory)
```

## What Synapse does

- **Councils** — orchestrate multiple AI agents or LLMs to deliberate on a question in structured stages: gather individual opinions, peer-rank them, synthesise a final verdict
- **Chat** — three modes: chat to *start* a council, chat *during* a council as a human participant, and chat *with* the verdict after it closes (powered by Astrocyte `reflect()`)
- **Persistent memory** — every council session is retained in Astrocyte; future councils recall relevant past decisions before deliberating
- **Governed deliberation** — Astrocyte's policy layer (PII barriers, rate limits, access control) applies to all memory operations; MIP routes decisions to the right memory banks
- **Multi-surface access** — a Svelte web UI for the browser, a Flutter desktop app for rich council observation, a Flutter mobile app for notifications and approvals, and an MCP server for agent-to-agent access
- **Messaging integrations** — Slack, Discord, Telegram, Teams, Google Chat, Lark, WeCom, and more: start a council with a slash command, receive verdict cards, approve decisions, and ask follow-up questions in thread without leaving your chat app
- **Council templates** — built-in templates (architecture-review, security-audit, code-review, red-team, product-decision, solo) with custom template support and inheritance
- **Multi-round deliberation** — draft → critique → refine cycles with convergence detection; red team mode for structured adversarial risk analysis
- **Decision workflows** — conflict detection against precedents, human approval chains, council chains, auto-promotion thresholds, and GDPR-compliant demotion
- **Scheduling** — one-time, recurring (cron), and externally triggered councils; APScheduler-based
- **Analytics** — member performance leaderboard, decision velocity, consensus distribution, topic clustering, knowledge coverage dashboard
- **RBAC** — five roles (viewer → member → approver → admin → owner) with JWT claim mapping and Astrocyte bank-level enforcement
- **Webhooks and exports** — HMAC-signed outbound events for every council lifecycle event; export integrations for Notion, Confluence, GitHub, Linear, and Markdown vaults
- **SDK** — `synapse-py` (PyPI) and `synapse-ts` (npm), both generated from the OpenAPI schema
- **Email notifications** — council concluded, approval requests, conflict alerts, weekly digest; configurable per-user preferences
- **Multi-tenancy and billing** — per-tenant isolation via Astrocyte `tenant_id`, quota enforcement, Stripe subscription management; self-hosted single-tenant mode available

## What Synapse is not

Synapse is **not** a memory framework. It does not implement `retain` / `recall` / `reflect` — that is Astrocyte's job. Synapse owns the deliberation protocol, session lifecycle, and multi-agent orchestration.

Synapse is **not** an LLM gateway. It calls LLMs to run councils but does not route or normalise general completion requests.

## Architecture overview

```
┌───────────────────────────────────────────────────┐
│                   Frontends                       │
│  Svelte (web) │ Flutter (desktop) │ Flutter (mobile) │
└───────────────┬───────────────────────────────────┘
                │  REST / SSE / WebSocket
┌───────────────▼───────────────────────────────────┐
│             Synapse Backend  (FastAPI)             │
│                                                   │
│   Council Engine   │   MCP Server   │   Auth      │
│   (orchestration,  │   (agent-to-   │   (JWT)     │
│    stages, stream) │    agent)      │             │
└───────────────┬───────────────────────────────────┘
                │  Python library or HTTP gateway
┌───────────────▼───────────────────────────────────┐
│                   Astrocyte                       │
│     retain │ recall │ reflect │ forget            │
│     MIP routing │ Policy │ Governance             │
└───────────────┬───────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────┐
│         Storage  (pgvector, Neo4j, …)             │
└───────────────────────────────────────────────────┘
```

## Frontends

| Surface | Technology | Primary use |
|---------|-----------|-------------|
| Web | Svelte + SvelteKit | Browser-based council dashboard, memory explorer |
| Desktop | Flutter | Rich council observation, local Astrocyte dev experience |
| Mobile | Flutter | Notifications, read councils, approve decisions |

## Deployment modes

Synapse connects to Astrocyte in one of two modes, selected by configuration:

| Mode | How | Best for |
|------|-----|---------|
| **Library** | Astrocyte imported as Python package, runs in-process | Development, single-node |
| **Gateway** | Synapse calls `astrocyte-gateway-py` over HTTP | Production, multi-tenant, polyglot |

The council engine is identical in both modes. Only the `AstrocyteClient` transport changes.

## License

Synapse is open source under the [Apache License 2.0](LICENSE).

All content under any `ee/` directory is licensed under the [Synapse Enterprise Edition License](apps/backend/ee/LICENSE) — proprietary, requires a Cerebro subscription for production use. Development and testing use is permitted without a subscription.

| Directory | License |
|---|---|
| Everything outside `ee/` | Apache 2.0 |
| `apps/backend/ee/` | Synapse EE License (proprietary) |

Enterprise features (multi-tenancy, SAML SSO, compliance audit trails, DSAR automation) are unlocked by setting `SYNAPSE_LICENSE_KEY` on your self-hosted instance. Contact [odeoncg.ai](https://odeoncg.ai) for a license key.

---

## Further reading

- [Architecture](docs/_design/architecture.md) — layer boundaries, component responsibilities, data flow
- [Council engine](docs/_design/council-engine.md) — deliberation stages, session lifecycle, memory integration
- [Chat](docs/_design/chat.md) — three chat modes, human-in-the-loop, WebSocket, chat with verdict
- [Deliberation](docs/_design/deliberation.md) — multi-round cycles, red team mode, verdict metadata
- [Templates](docs/_design/templates.md) — built-in templates, custom templates, inheritance
- [Workflows](docs/_design/workflows.md) — decision lifecycle, conflict detection, approval chains
- [Scheduling](docs/_design/scheduling.md) — scheduled, recurring, and triggered councils
- [Analytics](docs/_design/analytics.md) — member leaderboard, decision velocity, topic clustering
- [RBAC](docs/_design/rbac.md) — roles, permissions, JWT claim mapping
- [Webhooks](docs/_design/webhooks.md) — outbound events, export integrations (Notion, Confluence, GitHub)
- [SDK](docs/_design/sdk.md) — synapse-py and synapse-ts client libraries
- [Notifications](docs/_design/notifications.md) — email notifications, weekly digest, per-user preferences
- [Multi-tenancy](docs/_design/multi-tenancy.md) — tenant isolation, quotas, Stripe billing
- [Integrations](docs/_design/integrations.md) — Slack, Teams, Lark bots: commands, verdict cards, thread chat
- [Tech stack](docs/_design/tech-stack.md) — technology decisions and rationale
- [Project structure](docs/_design/project-structure.md) — monorepo layout and conventions
