"""Calls the configured live chat model for a pursuit specialist."""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from observability.tracing import traced_span


def model_identity() -> dict[str, str]:
    from shared.config import get_settings

    settings = get_settings()
    provider = settings.llm_provider.strip().lower()
    model = (
        settings.ollama_model
        if provider == "ollama"
        else settings.azure_openai_deployment
    )
    return {"provider": provider, "model": model}


def parse_model_json(response_text: str, required_keys: set[str]) -> dict[str, Any]:
    """Parse and validate a JSON object returned by the configured model."""
    content = response_text.strip()
    if content.startswith("```"):
        content = content.removeprefix("```json").removeprefix("```").strip()
        if content.endswith("```"):
            content = content[:-3].strip()
    decoder = json.JSONDecoder()
    for start, character in enumerate(content):
        if character != "{":
            continue
        try:
            result, _ = decoder.raw_decode(content, start)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict) and required_keys.issubset(result):
            return result
    raise RuntimeError(
        "Configured model did not return a JSON object with the required fields"
    )


def parse_model_answer(response_text: str, *, max_words: int = 90) -> str:
    """Extract an answer from JSON, including a truncated JSON wrapper, or plain text."""
    content = response_text.strip()
    if content.startswith("```"):
        content = content.removeprefix("```json").removeprefix("```").strip()
        if content.endswith("```"):
            content = content[:-3].strip()

    try:
        result = parse_model_json(content, {"answer"})
    except RuntimeError:
        answer_key = re.search(r'"answer"\s*:\s*"', content)
        if answer_key is None:
            if content and not content.startswith("{"):
                result = {"answer": content}
            else:
                raise
        else:
            value_start = answer_key.end() - 1
            try:
                answer, _ = json.JSONDecoder().raw_decode(content, value_start)
            except json.JSONDecodeError:
                partial_value = content[answer_key.end():]
                closing_quote = re.search(r'(?<!\\)(?:\\\\)*"', partial_value)
                if closing_quote:
                    partial_value = partial_value[:closing_quote.start()]
                partial_value = partial_value.rstrip("\\")
                try:
                    answer = json.loads(f'"{partial_value}"')
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        "Configured model returned an unreadable answer string"
                    ) from exc
            result = {"answer": answer}

    answer_value = result.get("answer")
    if not isinstance(answer_value, str) or not answer_value.strip():
        raise RuntimeError("Configured model returned an empty answer")
    answer = answer_value.strip()
    words = answer.split()
    if len(words) > max_words:
        answer = " ".join(words[:max_words])
        boundary = max(
            answer.rfind(". "),
            answer.rfind("; "),
            answer.rfind("\n"),
        )
        if boundary >= len(answer) // 2:
            answer = answer[:boundary + 1].rstrip()
        else:
            answer = answer.rstrip(" ,;:-") + "..."
    return answer


@traced_span("rpg_foresight.llm.agent_reasoning")
async def reason_with_live_model(
    agent_name: str,
    task: str,
    evidence: dict[str, Any],
    *,
    max_tokens: int = 384,
    timeout_seconds: float = 45,
) -> str:
    """Run one real model request; failures are surfaced to the API caller."""
    from opentelemetry import trace

    from shared.llm import get_llm

    identity = model_identity()
    span = trace.get_current_span()
    span.set_attribute("llm.provider", identity["provider"])
    span.set_attribute("llm.model_name", identity["model"])
    span.set_attribute("llm.agent_name", agent_name)

    prompt = (
        f"You are the {agent_name.replace('_', ' ')} for a live tender review.\n"
        f"Task: {task}\n"
        "Use only the supplied evidence. Do not invent values, requirements, "
        "dates, citations, or outcomes. If information is missing or uncertain, "
        "say so. Do not change any calculated score, risk classification, "
        "recommendation, or next step supplied in the evidence. Follow the task's "
        "requested response format and keep the response concise.\n"
        "Evidence JSON:\n"
        f"{json.dumps(evidence, ensure_ascii=False, default=str)}"
    )
    span.set_attribute("input.value", prompt[:16_000])

    started_at = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            get_llm(max_tokens=max_tokens, streaming=False).ainvoke(prompt),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        span.set_attribute("llm.duration_ms", duration_ms)
        raise RuntimeError(
            f"{agent_name} configured-model request exceeded "
            f"{timeout_seconds:g} seconds"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"{agent_name} configured-model request failed"
        ) from exc
    span.set_attribute(
        "llm.duration_ms",
        int((time.perf_counter() - started_at) * 1000),
    )
    content = response.content
    if isinstance(content, str):
        answer = content.strip()
    elif isinstance(content, list):
        answer = "\n".join(
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ).strip()
    else:
        answer = ""
    if not answer:
        raise RuntimeError(f"{agent_name} returned an empty model response")
    span.set_attribute("output.value", answer[:8_000])
    return answer
