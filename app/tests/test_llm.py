from __future__ import annotations

from types import SimpleNamespace

import pytest

import shared.llm as llm


def test_get_llm_defaults_to_local_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_chat_openai(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        llm,
        "get_settings",
        lambda: SimpleNamespace(
            llm_provider="ollama",
            ollama_base_url="http://localhost:11434/v1",
            ollama_model="qwen2.5:3b",
        ),
    )
    monkeypatch.setattr(llm, "ChatOpenAI", fake_chat_openai)

    llm.get_llm(max_tokens=256, streaming=False)

    assert captured == {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "model": "qwen2.5:3b",
        "max_tokens": 256,
        "streaming": False,
    }


def test_get_llm_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm,
        "get_settings",
        lambda: SimpleNamespace(llm_provider="unknown"),
    )

    with pytest.raises(ValueError, match="Supported providers are 'ollama'"):
        llm.get_llm()


def test_azure_provider_requires_azure_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm,
        "get_settings",
        lambda: SimpleNamespace(
            llm_provider="azure_openai",
            azure_openai_endpoint="",
            azure_openai_api_key="",
        ),
    )

    with pytest.raises(RuntimeError, match="For fully local inference"):
        llm.get_llm()
