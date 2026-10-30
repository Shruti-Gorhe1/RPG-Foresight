"""YAML-based prompt manager — externalises system prompts from agent code."""
from __future__ import annotations

import pathlib
from functools import lru_cache
from typing import Any

import yaml

_DEFAULT_PROMPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "config" / "prompts"


class PromptManager:
    """Load and cache prompts from YAML files under config/prompts/."""

    def __init__(self, prompts_dir: pathlib.Path | str | None = None) -> None:
        self._dir = pathlib.Path(prompts_dir) if prompts_dir else _DEFAULT_PROMPTS_DIR
        self._cache: dict[str, dict[str, Any]] = {}

    def _load(self, agent_name: str) -> dict[str, Any]:
        if agent_name not in self._cache:
            path = self._dir / f"{agent_name}.yaml"
            if path.exists():
                with path.open("r", encoding="utf-8") as fh:
                    self._cache[agent_name] = yaml.safe_load(fh) or {}
            else:
                self._cache[agent_name] = {}
        return self._cache[agent_name]

    def get_system_prompt(self, agent_name: str) -> str:
        return self._load(agent_name).get("system", "")

    def get_prompt(self, agent_name: str, prompt_type: str = "system") -> str:
        return self._load(agent_name).get(prompt_type, "")

    def format_prompt(self, agent_name: str, prompt_type: str = "system", **kwargs: Any) -> str:
        template = self.get_prompt(agent_name, prompt_type)
        try:
            return template.format(**kwargs)
        except KeyError:
            return template

    def reload_prompts(self) -> None:
        self._cache.clear()


@lru_cache(maxsize=1)
def _manager() -> PromptManager:
    return PromptManager()


def get_system_prompt(agent_name: str) -> str:
    return _manager().get_system_prompt(agent_name)


def get_prompt(agent_name: str, prompt_type: str = "system") -> str:
    return _manager().get_prompt(agent_name, prompt_type)


def format_prompt(agent_name: str, prompt_type: str = "system", **kwargs: Any) -> str:
    return _manager().format_prompt(agent_name, prompt_type, **kwargs)
