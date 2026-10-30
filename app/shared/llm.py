"""Shared chat-model factory for local Ollama and optional Azure OpenAI."""
from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_openai import AzureChatOpenAI

from shared.config import get_settings


def get_llm(max_tokens: int = 512, streaming: bool = True) -> BaseChatModel:
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()

    if provider == "ollama":
        return ChatOpenAI(
            base_url=settings.ollama_base_url,
            api_key="ollama",
            model=settings.ollama_model,
            max_tokens=max_tokens,
            streaming=streaming,
        )

    if provider != "azure_openai":
        raise ValueError(
            f"Unsupported LLM_PROVIDER {settings.llm_provider!r}. "
            "Supported providers are 'ollama' and 'azure_openai'."
        )

    if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        raise RuntimeError(
            "LLM_PROVIDER=azure_openai requires AZURE_OPENAI_ENDPOINT and "
            "AZURE_OPENAI_API_KEY. For fully local inference, use "
            "LLM_PROVIDER=ollama."
        )

    # Strip deployment path if the user provided the full URL, e.g.
    # https://host.azure.com/openai/deployments/... -> https://host.azure.com
    endpoint = settings.azure_openai_endpoint
    if "/openai" in endpoint:
        endpoint = endpoint.split("/openai")[0]
    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        azure_deployment=settings.azure_openai_deployment,
        openai_api_key=settings.azure_openai_api_key,
        openai_api_version=settings.azure_openai_api_version,
        max_tokens=max_tokens,
        # streaming=True lets OpenAIInstrumentor record a "First Token Stream
        # Event" span event, which Phoenix uses to compute TTFT.
        streaming=streaming,
    )
