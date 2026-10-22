"""
core/disputes.py — DETERMINISTIC complaint handling.

Complaints (noise, damage, behaviour, inter-tenant) are recorded and assessed:

  ESCALATE          — a safety risk or threat is present; a human must step in.
  NOTICE_WARRANTED  — a lease clause, by-law, or statute is clearly breached; a
                      formal notice is warranted (gated by approval).
  FACILITATE        — no clear breach; broker a resolution that respects both sides.

Anonymity is non-negotiable and lives in the data layer: when a complaint is
filed with anonymity, the complainant's identity is never surfaced to the subject
party. The engine always reports anonymity_protected so downstream drafting knows
to say only "we received a complaint".
"""

from __future__ import annotations
from enum import Enum


class DisputeVerdict(str, Enum):
    ESCALATE = "ESCALATE"
    NOTICE_WARRANTED = "NOTICE_WARRANTED"
    FACILITATE = "FACILITATE"


_SAFETY_SIGNS = (
    "threat", "threaten", "violence", "violent", "weapon", "assault", "hit me",
    "harass", "harassment", "stalk", "scared", "afraid", "fear for", "abusive",
    "fire hazard", "smoke everywhere", "intimidate",
)


def assess(category: str, details: str, *,
           lease_or_bylaw_breached: bool = False,
           anonymity: bool = True,
           safety_flag: bool | None = None) -> dict:
    """Return {"verdict", "reason", "metrics"}.

    safety_flag: an upstream judgement of whether a genuine safety risk is present.
      - True/False  -> use it (e.g. from the AI intake layer, which judges meaning
                        rather than keywords: "afraid I can't make it" is NOT a risk).
      - None        -> fall back to the deterministic keyword scan below (offline path).
    The engine still deterministically maps a safety risk to ESCALATE; the flag only
    supplies the *perception*, never the verdict."""
    text = (details or "").lower()
    metrics = {
        "category": category,
        "anonymity_protected": bool(anonymity),
        "breach_flagged": bool(lease_or_bylaw_breached),
    }

    if safety_flag is True:
        metrics["safety_source"] = "judged"
        return _result(DisputeVerdict.ESCALATE, metrics,
            "A genuine safety risk was identified. Escalating to a human immediately; "
            "this is beyond routine complaint handling.")

    if safety_flag is None:
        for sign in _SAFETY_SIGNS:
            if sign in text:
                metrics["safety_source"] = "keyword"
                return _result(DisputeVerdict.ESCALATE, metrics,
                    f"Safety indicator '{sign}' present. Escalating to a human immediately; "
                    f"this is beyond routine complaint handling.")

    if lease_or_bylaw_breached:
        return _result(DisputeVerdict.NOTICE_WARRANTED, metrics,
            "A lease clause or by-law appears to be breached. A formal notice is "
            "warranted (subject to approval). The complainant's identity is withheld.")

    return _result(DisputeVerdict.FACILITATE, metrics,
        "No clear breach established. Investigate and facilitate a resolution that "
        "respects both parties. The complainant's identity is withheld.")


def _result(verdict: DisputeVerdict, metrics: dict, reason: str) -> dict:
    return {"verdict": verdict.value, "reason": reason, "metrics": metrics}


if __name__ == "__main__":
    import json
    print(json.dumps(assess("noise", "Loud music after midnight every night"), indent=2))
    print(json.dumps(assess("behaviour", "He threatened me in the lift"), indent=2))
