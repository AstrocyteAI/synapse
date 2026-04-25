# SDK

This document defines the Synapse client SDKs — `synapse-py` (Python) and `synapse-ts` (TypeScript) — and the OpenAPI-based generation strategy.

---

## 1. Overview

Synapse publishes two first-party client libraries generated from the backend's OpenAPI schema:

| Package | Language | Published to | Used by |
|---------|----------|-------------|--------|
| `synapse-py` | Python | PyPI | Messaging integrations, external Python apps, scheduled scripts |
| `synapse-ts` | TypeScript | npm | Web frontend, external TypeScript apps |

Both are generated from `/openapi.json` and published as part of the CI/CD pipeline on every backend release. The `synapse-client-py` used internally by messaging integrations is the same package as `synapse-py`.

---

## 2. `synapse-py` — Python SDK

### 2.1 Installation

```bash
pip install synapse-py
# or
uv add synapse-py
```

### 2.2 Usage

```python
from synapse import SynapseClient

client = SynapseClient(
    base_url="https://synapse.example.com",
    api_key="sk_...",
)

# Start a council
council = await client.councils.create(
    question="Should we adopt event sourcing?",
    template="architecture-review",
)

# Poll for completion (or use the async stream)
async for event in client.councils.stream(council.id):
    if event.type == "council.closed":
        print(event.council.verdict)
        break

# Chat with a verdict (Mode 3)
response = await client.councils.chat(
    council_id=council.id,
    message="Why did the chairman weight Claude's response highest?",
)
print(response.answer)

# Recall precedents
hits = await client.memory.recall(
    query="event sourcing decisions",
    bank_id="precedents",
    max_results=5,
)
for hit in hits:
    print(hit.text, hit.score)
```

### 2.3 Async streaming

```python
async with client.councils.connect(council_id) as ws:
    async for event in ws:
        match event.type:
            case "stage1_complete":
                print("Stage 1 done:", event.responses)
            case "stage2_complete":
                print("Rankings:", event.aggregate_scores)
            case "stage3_complete":
                print("Verdict:", event.verdict)
            case "council.closed":
                break
```

### 2.4 Sync client

For scripts and non-async contexts:

```python
from synapse import SynapseClientSync

client = SynapseClientSync(base_url="...", api_key="...")
council = client.councils.create(question="...", template="architecture-review")
result = client.councils.wait_for_verdict(council.id, timeout=300)
print(result.verdict)
```

---

## 3. `synapse-ts` — TypeScript SDK

### 3.1 Installation

```bash
npm install synapse-ts
# or
pnpm add synapse-ts
```

### 3.2 Usage

```typescript
import { SynapseClient } from 'synapse-ts';

const client = new SynapseClient({
  baseUrl: 'https://synapse.example.com',
  apiKey: 'sk_...',
});

// Start a council
const council = await client.councils.create({
  question: 'Should we adopt event sourcing?',
  template: 'architecture-review',
});

// Stream events
const stream = client.councils.stream(council.id);
for await (const event of stream) {
  if (event.type === 'council.closed') {
    console.log(event.council.verdict);
    break;
  }
}

// Chat with verdict (Mode 3)
const response = await client.councils.chat(council.id, {
  message: 'Why did the chairman rank Claude highest?',
});
console.log(response.answer);

// Recall precedents
const hits = await client.memory.recall({
  query: 'event sourcing decisions',
  bankId: 'precedents',
  maxResults: 5,
});
```

### 3.3 React hook (for web frontend)

```typescript
import { useCouncil, useMemorySearch } from 'synapse-ts/react';

function CouncilPage({ councilId }: { councilId: string }) {
  const { council, events, isLoading } = useCouncil(councilId);

  return (
    <div>
      {events.map(event => <EventCard key={event.id} event={event} />)}
      {council?.verdict && <VerdictCard verdict={council.verdict} />}
    </div>
  );
}
```

---

## 4. Generation pipeline

Both SDKs are generated from the backend's OpenAPI schema using `openapi-generator`.

```
apps/backend → /openapi.json
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
   synapse-py               synapse-ts
   (openapi-generator        (openapi-generator
    python client)            typescript-fetch client)
         │                     │
    PyPI release           npm release
```

**Generation script (`packages/api-client/generate.sh`):**

```bash
#!/bin/bash
# Fetch schema from running backend
curl http://localhost:8000/openapi.json -o openapi.json

# Generate Python client
openapi-generator generate \
  -i openapi.json \
  -g python \
  -o ./python \
  --package-name synapse

# Generate TypeScript client
openapi-generator generate \
  -i openapi.json \
  -g typescript-fetch \
  -o ./typescript \
  --additional-properties=npmName=synapse-ts
```

**CI/CD:** generation runs automatically on every backend API change (detected by OpenAPI schema diff). PRs that change the backend API surface auto-generate updated clients and include them in the PR.

---

## 5. Versioning

SDKs are versioned in lockstep with the Synapse backend:
- `synapse-py 1.2.0` is compatible with `synapse-backend 1.2.x`
- Minor version bumps add new endpoints; patch bumps fix bugs
- Breaking changes increment the major version

The `openapi.json` includes a `x-synapse-version` extension that the SDK reads to warn on version mismatch.

---

## 6. `synapse-client-py` (internal)

The messaging integrations (`apps/integrations/*/client.py`) initially have inline Synapse API clients. After Phase 1 integrations ship, these are extracted into `synapse-py` and the integration packages declare `synapse-py` as a dependency.

This consolidation happens in Integration Phase 5 (see `integrations.md`).

---

## 7. Project structure

```
packages/
└── api-client/
    ├── generate.sh           # Generation script
    ├── openapi.json          # Cached schema (committed for reproducibility)
    ├── python/               # Generated Python client → published as synapse-py
    │   ├── synapse/
    │   │   ├── client.py
    │   │   ├── models.py
    │   │   └── ...
    │   └── pyproject.toml
    └── typescript/           # Generated TypeScript client → published as synapse-ts
        ├── src/
        │   ├── client.ts
        │   ├── models.ts
        │   └── react/        # React hooks
        └── package.json
```

---

## Further reading

- [Architecture](architecture.md) — REST API endpoints the SDK wraps
- [Integrations](integrations.md) — messaging integrations that use synapse-py internally
- [Webhooks](webhooks.md) — SDK includes webhook signature verification helpers
