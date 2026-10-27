"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
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
    centrifugo_ws_url: str = "ws://localhost:8001/connection/websocket"
    centrifugo_api_key: str = "dev-centrifugo-api-key"
    centrifugo_token_secret: str = "dev-centrifugo-token-secret"
    centrifugo_token_ttl_seconds: int = 3600

    # --- Auth ---
    synapse_auth_mode: Literal["jwt_hs256", "jwt_oidc", "local"] = "jwt_hs256"
    # HS256 (dev)
    synapse_jwt_secret: str = "dev-jwt-secret-change-in-production"
    synapse_jwt_audience: str = "synapse"
    # RS256 OIDC (production — external IdP such as Casdoor/Cerebro)
    synapse_jwt_jwks_url: str = ""
    synapse_jwt_issuer: str = ""
    # Local auth (SYNAPSE_AUTH_MODE=local) — built-in email/password, RS256 JWT issuance
    # Generate keys: openssl genrsa -out synapse-private.pem 2048
    #                openssl rsa -in synapse-private.pem -pubout -out synapse-public.pem
    # Then set SYNAPSE_LOCAL_JWT_PRIVATE_KEY and SYNAPSE_LOCAL_JWT_PUBLIC_KEY to the PEM contents.
    synapse_local_jwt_private_key: str = ""  # RS256 private key PEM
    synapse_local_jwt_public_key: str = ""  # RS256 public key PEM
    synapse_local_jwt_issuer: str = "http://localhost:8000"
    synapse_local_jwt_ttl_seconds: int = 3600
    synapse_local_registration_open: bool = True  # False = only admins can create users

    # --- LLM ---
    # Empty = call each provider directly (Pydantic AI). Set to route every call
    # through an OpenAI-compatible gateway such as AISIX; model names are then the
    # gateway's model aliases. Named LLM_GATEWAY_*, not AISIX_*, because AISIX warns
    # about unknown AISIX_* variables when one env file feeds both processes.
    llm_gateway_base_url: str = ""
    llm_gateway_api_key: str = ""
    # Removed. Kept only so a deployment still pointing at the retired LiteLLM
    # proxy fails at startup instead of silently calling providers directly,
    # bypassing the gateway it meant to use. See `_reject_retired_litellm`.
    litellm_api_base: str = ""

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

    # --- Multi-round deliberation (B5) ---
    deliberation_enabled: bool = True
    max_deliberation_rounds: int = 2  # critique→revise cycles before forced stop
    convergence_threshold: float = 0.72  # Jaccard similarity; stop early if reached
    critique_timeout_seconds: int = 60
    revise_timeout_seconds: int = 60

    # --- Notifications (EE Team+) ---
    # SMTP — operators supply their own server; no vendor lock-in
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = "noreply@synapse.local"
    smtp_tls: bool = True

    # ntfy — self-hostable push (UnifiedPush on Android; APNs relay on iOS)
    ntfy_url: str = ""  # e.g. https://ntfy.sh or http://ntfy.internal:2586
    ntfy_token: str = ""  # optional Bearer token for authenticated ntfy topics

    # FCM — Firebase Cloud Messaging HTTP v1 (Android + iOS via Firebase relay)
    fcm_service_account_json: str = ""  # full Google service-account JSON

    # APNs direct — native iOS device tokens (token_type='apns')
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_key: str = ""  # .p8 PEM contents
    apns_bundle_id: str = ""
    apns_use_sandbox: bool = False

    # --- EE ---
    synapse_license_key: str | None = None
    synapse_license_key_offline: str | None = None
    synapse_license_server_url: str = "https://cerebro.odeoncg.ai"

    # --- S-DSAR ---
    # HMAC-SHA256 secret used to sign fulfilment certificates. The basic
    # tier supports HMAC only; Cerebro Enterprise adds detached RS256 JWS
    # for externally-verifiable attestation. Operators MUST set a real
    # value in production — the default empty string disables the DSAR
    # endpoints (router returns 503).
    synapse_dsar_signing_secret: str = ""

    @model_validator(mode="after")
    def _reject_retired_litellm(self) -> Settings:
        if self.litellm_api_base:
            raise ValueError(
                "LITELLM_API_BASE is no longer supported: LiteLLM was replaced by "
                "AISIX. Set LLM_GATEWAY_BASE_URL (and LLM_GATEWAY_API_KEY, an AISIX "
                "caller key) instead, and use AISIX model aliases as model names."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
