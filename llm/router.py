"""
llm/router.py — the brain switchboard (same contract as store-tester).

Every AI call goes through route()/ask_*, which:
  1. Maps a TaskType to a provider (Claude / OpenAI / ...).
  2. Enforces the golden rule: DECISION-tagged tasks ONLY go to providers with
     supports_decisions=True. Today that's Claude alone.
  3. Reads the mapping from config.PROVIDER_MAP so you can swap brains by editing
     ONE line — no code changes elsewhere.

In the property agent the engines in core/ make every *verdict*. The LLM is only
ever asked to DRAFT party-facing prose, which is treated as decision-class
because getting tone and facts right is part of the agency's duty of care.
"""

from __future__ import annotations
from enum import Enum

from llm.providers.base import AIProvider
from llm.providers.anthropic_provider import ClaudeProvider
from llm.providers.openai_provider import GPTProvider
from llm.providers.deepseek_provider import DeepSeekProvider


class TaskType(str, Enum):
    # ---- Locked to Claude (decision-class) ----
    DECISION = "decision"     # any verdict-adjacent reasoning (reserved)
    DRAFTING = "drafting"     # writing a message to a tenant/landlord/contractor
    INTAKE = "intake"         # understanding an inbound message (feeds the engines)
    # ---- Open to any provider ----
    SUMMARY = "summary"       # operator-facing recap, quality-tolerant


# Provider registry — add a new vendor here.
_REGISTRY: dict[str, AIProvider] = {
    "anthropic": ClaudeProvider(),
    "openai":    GPTProvider(),
    "deepseek":  DeepSeekProvider(),
}


# Tasks that MUST go to a provider with supports_decisions=True.
# INTAKE is decision-class: misreading a gas leak is as costly as misphrasing it,
# so the perception layer is locked to Claude just like drafting.
_DECISION_TASKS = {TaskType.DECISION, TaskType.DRAFTING, TaskType.INTAKE}


# Default mapping. Override via config.PROVIDER_MAP.
_DEFAULT_MAP: dict[TaskType, str] = {
    TaskType.DECISION: "anthropic",
    TaskType.DRAFTING: "anthropic",
    TaskType.INTAKE:   "anthropic",
    TaskType.SUMMARY:  "anthropic",
}


def _load_map() -> dict[TaskType, str]:
    """Merge config.PROVIDER_MAP (str keys) over _DEFAULT_MAP (TaskType keys)."""
    try:
        from config import PROVIDER_MAP  # type: ignore
        merged = dict(_DEFAULT_MAP)
        for k, v in PROVIDER_MAP.items():
            try:
                merged[TaskType(k)] = v
            except ValueError:
                pass  # Unknown task name in config — ignore.
        return merged
    except (ImportError, AttributeError):
        return _DEFAULT_MAP


def get_provider(task: TaskType) -> AIProvider:
    """Resolve a task type to a concrete provider, enforcing the decision lock."""
    mapping = _load_map()
    name = mapping.get(task, "anthropic")
    provider = _REGISTRY.get(name)
    if provider is None:
        raise RuntimeError(
            f"Unknown provider '{name}' for task {task.value}. "
            f"Available: {list(_REGISTRY)}"
        )
    if task in _DECISION_TASKS and not provider.supports_decisions:
        raise RuntimeError(
            f"GOLDEN RULE VIOLATION: task {task.value} routed to '{name}' which has "
            f"supports_decisions=False. Decision-class tasks must go to Claude. "
            f"Edit config.PROVIDER_MAP."
        )
    return provider


def ask_json(task: TaskType, system: str, user: str, *,
             max_tokens: int = 600, tier: str = "reasoning") -> dict:
    return get_provider(task).ask_json(system, user, max_tokens=max_tokens, tier=tier)


def ask_text(task: TaskType, system: str, user: str, *,
             max_tokens: int = 400, tier: str = "reasoning") -> str:
    return get_provider(task).ask_text(system, user, max_tokens=max_tokens, tier=tier)


def status() -> dict:
    """Diagnostic: which providers are available + the current mapping."""
    mapping = _load_map()
    return {
        "providers": {n: p.available() for n, p in _REGISTRY.items()},
        "mapping": {t.value: mapping[t] for t in TaskType},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(status(), indent=2))
