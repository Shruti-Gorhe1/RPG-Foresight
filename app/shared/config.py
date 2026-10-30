"""Central configuration — reads from .env via pydantic-settings.

Secrets that live in Azure Key Vault are declared as ``*_kv_uri`` fields.
The ``_resolve_kv_secrets`` validator fetches the real values at startup so the
rest of the app reads plain fields (e.g. ``settings.azure_openai_api_key``) with
no knowledge of Key Vault.

This is the accelerator baseline — add app-specific settings in the
"App-specific settings" block at the bottom; keep the platform blocks intact.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parents[1]
_REPOSITORY_DIR = _BASE_DIR.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_REPOSITORY_DIR / ".env"), str(_BASE_DIR / ".env")),
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────────────────────
    app_env: str = "development"
    app_secret_key: str = "change-me"
    log_level: str = "INFO"
    # Comma-separated allowed origins for non-development environments, e.g.
    # "https://__APP_NAME__-fe.bravesky-d9f9eeb7.eastus2.azurecontainerapps.io"
    cors_allowed_origins: str = ""

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/rpg_foresight"

    # ── Local LLM / optional Azure OpenAI ─────────────────────────────────────
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:3b"
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-4.1-mini"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_api_version: str = "2025-01-01-preview"

    # ── Azure Key Vault ────────────────────────────────────────────────────────
    azure_keyvault_url: str = "https://zaf-kv-01.vault.azure.net/"

    # KV URI overrides — when set, the corresponding plain field is populated at
    # startup by _resolve_kv_secrets below.
    azure_openai_endpoint_kv_uri: str = ""
    azure_openai_api_key_kv_uri: str = ""
    azure_openai_deployment_kv_uri: str = ""
    database_url_kv_uri: str = ""

    # KV URI overrides — Zoho / Teams secrets sourced from Key Vault
    zoho_client_id_kv_uri: str = ""
    zoho_client_secret_kv_uri: str = ""
    zoho_refresh_token_kv_uri: str = ""
    teams_webhook_url_kv_uri: str = ""

    # --- SMTP Email ---
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = ''
    smtp_from: str = ''
    smtp_use_tls: bool = True
    smtp_timeout_seconds: int = 30
    smtp_password_kv_uri: str = ''

    # --- Transactional email provider ---
    email_provider: str = "smtp"
    resend_api_key: str = ""
    resend_api_key_kv_uri: str = ""
    resend_from: str = ""


    # ── Azure / EntraID ────────────────────────────────────────────────────────
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    entra_authority: str = "https://login.microsoftonline.com/"
    entra_audience: str = ""

    # ── Vector DB (optional) ───────────────────────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # ── Temporal ───────────────────────────────────────────────────────────────
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "__NAMESPACE__"
    temporal_task_queue_agents: str = "__TASK_QUEUE__"

    # ── Arize Phoenix Observability ────────────────────────────────────────────
    phoenix_host: str = "localhost"
    phoenix_port: int = 6006
    # e.g. https://zaf-phoenix.bravesky-d9f9eeb7.eastus2.azurecontainerapps.io/v1/traces
    phoenix_collector_endpoint: str = ""
    phoenix_project_name: str = "__APP_NAME__"
    arize_space_id: str = ""
    arize_phoenix_api_key: str = ""          # resolved from KV
    arize_phoenix_api_key_kv_uri: str = ""

    # ── Prompts ────────────────────────────────────────────────────────────────
    prompts_dir: str = "config/prompts"

    # ── Zoho CRM ───────────────────────────────────────────────────────────────
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""
    zoho_redirect_uri: str = "http://localhost:8010/api/v1/connectors/zoho/callback"
    zoho_module: str = "Tenders"
    zoho_api_domain: str = "www.zohoapis.com"
    zoho_accounts_domain: str = "accounts.zoho.com"
    zoho_tenant_id: str = "KEC-001"
    zoho_sender_entity_id: str = "KEC-ENTITY"
    zoho_connector_enabled: bool = False

    # ── Microsoft Teams ────────────────────────────────────────────────────────
    teams_webhook_url: str = ""

    # ────────────────────────────────────────────────────────────────────────────
    # App-specific settings — add your own fields below (external APIs, feature
    # flags, thresholds, etc). Declare a matching ``*_kv_uri`` and add it to the
    # kv_map in _resolve_kv_secrets for any secret sourced from Key Vault.
    # ────────────────────────────────────────────────────────────────────────────

    # ── Security validators ────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _enforce_secret_key(self) -> "Settings":
        """Refuse to start in production with the default secret key."""
        if self.app_env == "production" and self.app_secret_key == "change-me":
            raise ValueError(
                "app_secret_key must not be 'change-me' in production. "
                "Set APP_SECRET_KEY via Azure Key Vault or an environment variable."
            )
        return self

    @model_validator(mode="after")
    def _resolve_kv_secrets(self) -> "Settings":
        """Replace any field whose corresponding ``*_kv_uri`` is set with the
        secret value fetched from Azure Key Vault. Silent no-op when the Azure
        SDK is not installed (local dev)."""
        try:
            from security.vault import get_secret_by_uri
        except ImportError:
            return self

        kv_map: list[tuple[str, str]] = [
            ("azure_openai_endpoint_kv_uri", "azure_openai_endpoint"),
            ("azure_openai_api_key_kv_uri", "azure_openai_api_key"),
            ("azure_openai_deployment_kv_uri", "azure_openai_deployment"),
            ("database_url_kv_uri", "database_url"),
            ("arize_phoenix_api_key_kv_uri", "arize_phoenix_api_key"),
            ("zoho_client_id_kv_uri", "zoho_client_id"),
            ("zoho_client_secret_kv_uri", "zoho_client_secret"),
            ("zoho_refresh_token_kv_uri", "zoho_refresh_token"),
            ("teams_webhook_url_kv_uri", "teams_webhook_url"),
            ("smtp_password_kv_uri", "smtp_password"),
            ("resend_api_key_kv_uri", "resend_api_key"),
        ]
        for uri_field, target_field in kv_map:
            uri: str = getattr(self, uri_field, "")
            if uri:
                value = get_secret_by_uri(uri)
                if value:
                    object.__setattr__(self, target_field, value)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
