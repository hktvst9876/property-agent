"""
llm/understand.py — the "smart senses" layer.

Turns a free-text inbound message into the SAME structured signals the orchestrator
already consumes from core/intake_parser.py — but with genuine comprehension instead
of keyword matching. It reads past Singlish, typos, and mixed topics; orders issues
most-urgent-first; writes a clean agent's-POV summary of each issue (so what reaches
the landlord/contractor is the manager's wording, not the tenant's raw text); and
judges genuine dispute safety risk rather than tripping on a keyword.

Mirrors llm/drafter.py exactly: if a model is configured it's used, otherwise — or on
any error/malformed output — it falls back to the deterministic keyword parser, so the
system runs identically with no API key. The model NEVER decides a verdict; every
decision still belongs to the engines in core/.
"""

from __future__ import annotations
import json

from llm.router import ask_json, get_provider, TaskType
from llm.prompts import INTAKE_MESSAGE, PROPERTY_AGENT_SYSTEM
from core import intake_parser

# Allowed enum values — anything outside these is dropped so a stray model token can
# never produce an event type/trade/category the engines don't understand.
_INTENTS = {"maintenance", "arrears", "dispute", "renewal", "move_out"}
_TRADES = {"plumber", "electrician", "locksmith", "aircon", "general"}
_CATEGORIES = {"noise", "behaviour", "other"}
_FOLLOWUPS = {"status_chase", "acknowledgement", "confirmation"}
_SENTIMENTS = {"distressed", "angry", "calm"}


def _model_available() -> bool:
    try:
        return get_provider(TaskType.INTAKE).available()
    except Exception:
        return False


def understand_message(text: str) -> dict:
    """Read an inbound message. Returns the parser's shape
    ({"intents", "follow_up", "sentiment"}) where each intent additionally carries
    "summary" (agent's-POV) and "urgency_hint", and dispute intents carry
    hints["safety_flag"]/["safety_reason"]. Falls back to the keyword parser."""
    if not _model_available():
        return intake_parser.parse(text)

    result = ask_json(
        TaskType.INTAKE,
        system=PROPERTY_AGENT_SYSTEM + "\n\n" + INTAKE_MESSAGE,
        user=text or "",
        max_tokens=700,
    )
    if "_error" in result:
        return intake_parser.parse(text)

    normalised = _normalise(result)
    if normalised is None:
        return intake_parser.parse(text)
    return normalised


def _normalise(raw: dict) -> dict | None:
    """Coerce the model's JSON into the orchestrator's expected shape. Returns None if
    the payload is unusable (triggers the keyword fallback)."""
    if not isinstance(raw, dict):
        return None

    raw_intents = raw.get("intents", [])
    if not isinstance(raw_intents, list):
        return None

    intents: list[dict] = []
    for it in raw_intents:
        if not isinstance(it, dict):
            continue
        name = it.get("intent")
        if name not in _INTENTS:
            continue  # drop anything the engines can't route

        hints: dict = {}
        if name == "maintenance":
            trade = it.get("trade")
            hints["trade"] = trade if trade in _TRADES else "general"
        if name == "dispute":
            cat = it.get("category")
            hints["category"] = cat if cat in _CATEGORIES else "other"
            # Only carry an explicit boolean; otherwise leave absent so the engine's
            # keyword fallback runs instead of a guessed False.
            if isinstance(it.get("safety_flag"), bool):
                hints["safety_flag"] = it["safety_flag"]
                hints["safety_reason"] = str(it.get("safety_reason") or "")

        summary = it.get("summary")
        intents.append({
            "intent": name,
            "hints": hints,
            "summary": str(summary).strip() if summary else None,
            "urgency_hint": it.get("urgency_hint", "routine"),
        })

    follow_up = raw.get("follow_up")
    follow_up = follow_up if follow_up in _FOLLOWUPS else None

    sentiment = raw.get("sentiment")
    sentiment = sentiment if sentiment in _SENTIMENTS else "calm"

    return {"intents": intents, "follow_up": follow_up, "sentiment": sentiment}
