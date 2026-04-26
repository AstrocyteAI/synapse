"""Shared Synapse backend OpenAPI contract."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load_contract() -> dict[str, Any]:
    """Return the canonical contract shared by Synapse EE and Cerebro."""
    contract = resources.files("synapse.contracts").joinpath("synapse-v1.openapi.json")
    return json.loads(contract.read_text(encoding="utf-8"))
