# Synapse E2E — Path A (OSS self-hosted)

Black-box end-to-end tests that bring up the full OSS stack with Docker Compose
and exercise it through public REST/SSE APIs. Single-tenant, HS256 auth.

## Layout

```
e2e/
  shared/                 # Backend-agnostic suite (parametrized on BACKEND_URL)
  path_a/                 # Path-A specific journeys (Synapse-only features)
  webhook_sink/           # Tiny FastAPI recorder used by webhook tests
  conftest.py             # Auth strategy + httpx clients + markers
  docker-compose.path-a.yml
  requirements.txt
  pytest.ini
```

The `shared/` suite is the **API contract**: any backend that claims to speak
the Synapse REST contract must pass it. Cerebro pulls this same suite into its
private e2e harness to prove drop-in compatibility (Paths B and C).

## Running locally

```bash
# From repo root
docker compose -f e2e/docker-compose.path-a.yml up --wait

pip install -r e2e/requirements.txt
pytest e2e/

docker compose -f e2e/docker-compose.path-a.yml down -v
```

## CI

`.github/workflows/e2e-path-a.yml` runs this suite on every PR and on
`repository_dispatch` from the astrocyte release workflow.
