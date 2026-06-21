"""
core/legal_guard.py — the single chokepoint for anything legal-adjacent.

The user's rule, enforced in code (not left to the model's discretion):

  1. The agent NEVER answers a legal question or gives legal advice. A direct
     legal question gets a referral, not an answer.
  2. Factual legal information is surfaced ONLY when a deterministic engine has
     already put a party at genuine risk (a risk *stage*).
  3. Every surfaced statement carries a "general information, not legal advice —
     verify with a qualified professional" disclaimer.
  4. Every surfaced statement carries a NON-EMPTY list of sources. If no source
     is available, nothing is surfaced — the matter is escalated to a human.

Engines call surface(stage). Intake calls is_legal_question()/refuse() on raw
inbound text. The orchestrator catches LegalGuardEscalation and escalates.
"""

from __future__ import annotations
import re

from jurisdictions.base import get_jurisdiction

DISCLAIMER = (
    "Please note: this is general information, not legal advice. It should be "
    "verified with a qualified legal professional before you act on it."
)

REFERRAL = (
    "I'm not able to give legal advice or answer legal questions. For that, "
    "please consult a qualified legal professional (for example, a lawyer or a "
    "community legal clinic). I'm glad to help with anything within the agency's "
    "remit."
)


class LegalGuardEscalation(Exception):
    """Raised when legal info is warranted but no citable source exists.
    The orchestrator turns this into a human escalation."""


# A risk stage is the ONLY key that unlocks factual legal information. Each maps
# to a topic in the active jurisdiction's data pack.
_STAGE_TOPIC = {
    "arrears_legal_risk": "arrears_recovery",
    "dispute_notice":     "disputes",
    "eot_dispute":        "disputes",
    "notice":             "notices",
    "deposit_claim":      "deposit",
    "onboarding":         "onboarding",
}

# Phrases that signal someone is asking us for a legal opinion / answer.
_LEGAL_Q = re.compile(
    r"\b(can i (legally|evict|withhold|sue|terminate)|am i (allowed|entitled|liable)|"
    r"is it legal|are they allowed|what are my (legal )?rights|do i have (the|a) right|"
    r"can the landlord (legally|evict|enter)|can my tenant|"
    r"will i (win|lose) (in|at) court|should i sue|take (them|him|her) to court|"
    r"is this (legal|illegal|lawful))\b",
    re.IGNORECASE,
)


def is_legal_question(text: str) -> bool:
    """True if inbound text reads as a request for legal advice/opinion."""
    return bool(_LEGAL_Q.search(text or ""))


def refuse() -> dict:
    """The only response to a direct legal question: a referral, never an answer."""
    return {
        "refused": True,
        "refer_to_professional": True,
        "message": REFERRAL,
    }


def surface(stage: str, jurisdiction_code: str = "SG") -> dict:
    """
    Return guarded factual legal information for a risk stage.

    Returns:
      {"facts": [str, ...], "sources": [{"citation","url"}, ...],
       "disclaimer": str, "refer_to_professional": True}

    Raises:
      ValueError            — stage isn't a recognised risk stage (caller bug:
                              never surface legal info outside a risk stage).
      LegalGuardEscalation  — the stage is valid but the jurisdiction has no
                              citable source; escalate to a human instead.
    """
    topic = _STAGE_TOPIC.get(stage)
    if topic is None:
        raise ValueError(
            f"legal_guard.surface called with non-risk stage {stage!r}. "
            f"Legal facts may only be surfaced at a genuine risk stage."
        )

    jur = get_jurisdiction(jurisdiction_code)
    legal_facts = jur.facts_for(topic)

    facts: list[str] = []
    sources: list[dict] = []
    seen: set[str] = set()
    for lf in legal_facts:
        if not lf.sources:
            continue  # a fact with no source is unusable here
        facts.append(lf.text)
        for s in lf.sources:
            if s.citation not in seen:
                seen.add(s.citation)
                sources.append({"citation": s.citation, "url": s.url})

    if not facts or not sources:
        raise LegalGuardEscalation(
            f"Risk stage {stage!r} reached but no citable source available for "
            f"topic {topic!r} in {jur.name}. Escalating rather than stating "
            f"unsourced legal information."
        )

    return {
        "facts": facts,
        "sources": sources,
        "disclaimer": DISCLAIMER,
        "refer_to_professional": True,
    }
