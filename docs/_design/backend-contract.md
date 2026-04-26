# Shared Synapse Backend Contract

Synapse supports two backend implementations:

- Synapse EE self-hosted backend, implemented with FastAPI and Centrifugo.
- Cerebro backend, implemented with Phoenix and Phoenix Channels.

Both backends expose the same REST OpenAPI contract at `/openapi.json`. The canonical contract is committed in the backend source and exported by CI as `synapse-v1.openapi.json` so clients can generate SDKs without caring which backend serves the API.

## Realtime Descriptor

Realtime transport differs internally, so the shared REST contract includes a descriptor endpoint:

```http
GET /v1/socket/token
Authorization: Bearer <jwt>
```

Response:

```json
{
  "transport": "centrifugo",
  "url": "ws://localhost:8001/connection/websocket",
  "token": "...",
  "expires_in": 3600,
  "topics": {
    "council": "council:<council_id>",
    "thread": "thread:<thread_id>"
  }
}
```

Cerebro returns the same schema with `transport: "phoenix"` and a Phoenix `/socket/websocket` URL.

## Client Contract

Clients must normalize transport events to:

```json
{
  "topic": "council:<id>",
  "type": "stage1_complete",
  "payload": {}
}
```

This keeps application code independent of whether the backend uses Centrifugo publication frames or Phoenix channel event names.

## Compatibility Rule

Do not add Synapse EE-only or Cerebro-only REST paths to the shared client surface. If one backend needs a private operational endpoint, keep it outside the shared OpenAPI contract or mark it as implementation-specific documentation rather than part of `synapse-v1.openapi.json`.
