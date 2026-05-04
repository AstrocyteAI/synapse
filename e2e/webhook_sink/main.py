"""Minimal webhook recorder for E2E tests.

Records every inbound POST so tests can assert on delivery, headers,
and HMAC signatures without depending on an external service.

Endpoints:
    POST /<any path>        — record the request, return 200
    GET  /health            — liveness check
    GET  /recorded          — return all recorded requests
    DELETE /recorded        — clear the recording (called between tests)
"""

from __future__ import annotations

import threading
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
_lock = threading.Lock()
_received: list[dict] = []


@app.post("/{path:path}")
async def receive(request: Request, path: str) -> JSONResponse:
    body = await request.body()
    with _lock:
        _received.append(
            {
                "path": f"/{path}",
                "headers": dict(request.headers),
                "body": body.decode(errors="replace"),
            }
        )
    return JSONResponse({"ok": True}, status_code=200)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/recorded")
def recorded() -> list[dict]:
    with _lock:
        return list(_received)


@app.delete("/recorded")
def clear() -> dict:
    with _lock:
        _received.clear()
    return {"ok": True}
