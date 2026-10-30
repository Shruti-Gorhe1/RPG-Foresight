"""Azure Key Vault helper — resolve secrets by full URI.

Self-contained (no Settings import) to avoid a circular dependency with
shared.config, which calls get_secret_by_uri from a model validator.

A secret URI looks like:
    https://<vault-name>.vault.azure.net/secrets/<secret-name>[/<version>]
"""
from __future__ import annotations

import logging
from functools import lru_cache

log = logging.getLogger("security.vault")


@lru_cache(maxsize=64)
def get_secret_by_uri(secret_uri: str) -> str | None:
    """Fetch a secret value from Azure Key Vault given its full URI.

    Returns None (and logs a warning) if the Azure SDK is missing or the fetch
    fails — callers keep whatever default they already had.
    """
    if not secret_uri:
        return None
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError:
        log.warning("azure-keyvault-secrets not installed; cannot resolve %s", secret_uri)
        return None

    try:
        # Split "https://vault.vault.azure.net/secrets/name/version"
        parts = secret_uri.rstrip("/").split("/secrets/")
        vault_url = parts[0]
        name_and_version = parts[1].split("/")
        secret_name = name_and_version[0]
        version = name_and_version[1] if len(name_and_version) > 1 else None

        client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
        secret = client.get_secret(secret_name, version)
        return secret.value
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to resolve secret %s: %s", secret_uri, exc)
        return None
