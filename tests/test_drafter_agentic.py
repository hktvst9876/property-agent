"""
Proves the optional-LLM wiring without a live model: a stub provider stands in for
whatever the drafting task maps to, and captures exactly what the drafter hands the
model. Verifies the tenant's real message (mood) and legal facts flow through, that
model output is used when available, and that mood-aware templates take over when
no model is up.
"""

import json

from llm import router, drafter
from llm.router import TaskType, _load_map

_DRAFT_PROVIDER = _load_map()[TaskType.DRAFTING]   # whatever 'drafting' maps to


class _StubProvider:
    supports_decisions = True

    def __init__(self):
        self.last_user = None

    def available(self) -> bool:
        return True

    def ask_json(self, system, user, **kw) -> dict:
        self.last_user = user
        return {"subject": "stub", "body": "a warm, mood-aware reply"}

    def ask_text(self, system, user, **kw) -> str:
        return "stub"


def test_inbound_mood_reaches_the_model(monkeypatch):
    stub = _StubProvider()
    monkeypatch.setitem(router._REGISTRY, _DRAFT_PROVIDER, stub)

    out = drafter.draft_message(
        "tenant", "LEGAL_RISK", "rent is 19 days overdue",
        inbound_message="I AM FURIOUS, this is completely unacceptable!!",
    )
    assert out["body"] == "a warm, mood-aware reply"      # model output is used
    payload = json.loads(stub.last_user)
    assert "FURIOUS" in payload["original_message_from_recipient"]   # mood handed over
    assert payload["what_to_communicate"] == "rent is 19 days overdue"


def test_legal_facts_and_disclaimer_passed(monkeypatch):
    stub = _StubProvider()
    monkeypatch.setitem(router._REGISTRY, _DRAFT_PROVIDER, stub)

    legal = {"facts": ["a fact"], "disclaimer": "verify with a professional",
             "sources": [{"citation": "SCT", "url": "http://x"}]}
    drafter.draft_message("tenant", "LEGAL_RISK", "overdue", legal=legal)
    payload = json.loads(stub.last_user)
    assert payload["legal_facts"] == ["a fact"]
    assert payload["disclaimer"] == "verify with a professional"


def test_template_is_mood_aware_when_no_model(monkeypatch):
    class _Down(_StubProvider):
        def available(self) -> bool:
            return False
    monkeypatch.setitem(router._REGISTRY, _DRAFT_PROVIDER, _Down())

    angry = drafter.draft_message(
        "tenant", "ASSESS", "We've arranged a contractor to take a look.",
        inbound_message="this is the third time!! unacceptable",
    )
    calm = drafter.draft_message(
        "tenant", "ASSESS", "We've arranged a contractor to take a look.",
        inbound_message="hi, the tap is dripping a little",
    )
    assert "The Property Management Team" in angry["body"]        # template path
    assert "frustration" in angry["body"].lower()                 # empathy opener added
    assert "frustration" not in calm["body"].lower()              # calm gets no opener
