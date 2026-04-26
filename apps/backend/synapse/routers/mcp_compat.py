"""JSON tool dispatch endpoint for the shared Synapse backend contract."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["mcp"])

_SUPPORTED_TOOLS = {
    "synapse.council.list",
    "synapse.council.create",
    "synapse.council.start",
    "synapse.council.join",
    "synapse.council.contribute",
    "synapse.council.close",
    "synapse.memory.recall",
    "synapse.memory.recall_precedent",
}


class MCPDispatchRequest(BaseModel):
    tool: str
    arguments: dict = {}


@router.post("/mcp")
async def dispatch_mcp_tool(
    body: MCPDispatchRequest,
    x_api_key: str | None = Header(default=None),
) -> dict:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="x-api-key required")
    if body.tool not in _SUPPORTED_TOOLS:
        raise HTTPException(status_code=422, detail="unknown tool")

    return {"result": {"tool": body.tool, "arguments": body.arguments, "accepted": True}}
