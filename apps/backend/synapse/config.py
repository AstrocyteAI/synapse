"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+asyncpg://synapse:synapse@localhost:5432/synapse"

    # --- Astrocyte gateway ---
    astrocyte_gateway_url: str = "http://localhost:8080"
    astrocyte_token: str = "dev-astrocyte-api-key"

    # --- Centrifugo ---
    centrifugo_api_url: str = "http://localhost:8002"
    centrifugo_api_key: str = "dev-centrifugo-api-key"
    centrifugo_token_secret: str = "dev-centrifugo-token-secret"
    centrifugo_token_ttl_seconds: int = 3600

    # --- Auth ---
    synapse_auth_mode: Literal["jwt_hs256", "jwt_oidc"] = "jwt_hs256"
    # HS256 (dev)
    synapse_jwt_secret: str = "dev-jwt-secret-change-in-production"
    synapse_jwt_audience: str = "synapse"
    # RS256 OIDC (production)
    synapse_jwt_jwks_url: str = ""
    synapse_jwt_issuer: str = ""

    # --- LLM ---
    synapse_llm_provider: Literal["litellm"] = "litellm"
    litellm_api_base: str = ""   # empty = direct library calls; set for proxy
    litellm_api_key: str = ""

    # --- Council defaults ---
    default_members: list[dict] = [
        {"model_id": "gpt-4o", "name": "GPT-4o"},
        {"model_id": "claude-3-5-sonnet-20241022", "name": "Claude"},
        {"model_id": "gemini/gemini-1.5-pro", "name": "Gemini"},
    ]
    default_chairman: dict = {"model_id": "claude-opus-4-5", "name": "Chair"}
    stage1_timeout_seconds: int = 60
    stage2_timeout_seconds: int = 60
    stage3_timeout_seconds: int = 90
    max_precedents: int = 5

    # --- EE ---
    synapse_license_key: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
