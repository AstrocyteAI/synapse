"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from synapse.config import get_settings
from synapse.db.session import create_engine_and_sessionmaker
from synapse.mcp.server import mcp as mcp_server
from synapse.memory.gateway_client import AstrocyteGatewayClient
from synapse.realtime.centrifugo import CentrifugoClient
from synapse.routers import centrifugo_router, councils, threads


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Shared async HTTP client — one connection pool for the process lifetime
    http_client = httpx.AsyncClient(timeout=120.0)

    # Wire dependencies onto app state so routers can access them via request.app.state
    app.state.settings = settings
    app.state.http_client = http_client
    app.state.astrocyte = AstrocyteGatewayClient(
        base_url=settings.astrocyte_gateway_url,
        api_key=settings.astrocyte_token,
        http_client=http_client,
    )
    app.state.centrifugo = CentrifugoClient(
        api_url=settings.centrifugo_api_url,
        api_key=settings.centrifugo_api_key,
        http_client=http_client,
    )
    engine, sessionmaker = create_engine_and_sessionmaker(settings.database_url)
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker

    yield

    await http_client.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Synapse",
        description="Multi-agent deliberation API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(councils.router, prefix="/v1")
    app.include_router(threads.router, prefix="/v1")
    app.include_router(centrifugo_router.router, prefix="/v1")

    # MCP server — agent-to-agent access via Streamable HTTP transport
    # Tools: start_council, join, contribute, recall_precedent, close
    app.mount("/mcp", mcp_server.streamable_http_app())

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
