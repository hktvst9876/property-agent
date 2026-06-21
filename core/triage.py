"""
core/triage.py — DETERMINISTIC urgency classification.

Rules decide the urgency band; the LLM never does. Bands and their service-level
targets come straight from the agency's master prompt.

  EMERGENCY — act this hour:  no water / no hot water, flood, gas leak,
              electrical hazard, break-in / security compromise, anything the
              tenant reports as unsafe.
  URGENT    — act same day:   broken lock or door, an appliance failure that
              hits daily life, a formal legal notice received, a party in distress.
  ROUTINE   — 2-5 business days: everything else.
"""

from __future__ import annotations
from enum import Enum


class Urgency(str, Enum):
    EMERGENCY = "EMERGENCY"
    URGENT = "URGENT"
    ROUTINE = "ROUTINE"


SLA = {
    Urgency.EMERGENCY: "same hour",
    Urgency.URGENT: "same day",
    Urgency.ROUTINE: "2-5 business days",
}

_EMERGENCY_SIGNS = (
    "no water", "no hot water", "without water", "burst pipe", "flood", "flooding",
    "gas leak", "smell gas", "smell of gas", "gas smell", "electrical hazard",
    "exposed wire", "sparking", "sparks", "burning smell", "fire",
    "break-in", "break in", "broken into", "intruder", "burglary", "not secure",
    "unsafe", "carbon monoxide",
)

_URGENT_SIGNS = (
    "broken lock", "can't lock", "cannot lock", "won't lock", "door won't close",
    "broken door", "locked out", "no electricity", "power out", "no power",
    "fridge not working", "refrigerator not working", "freezer not working",
    "no aircon", "air-con not working", "aircon not working", "oven not working",
    "stove not working", "washing machine not working", "no cooking",
    "legal notice", "letter of demand", "court", "distress", "very distressed",
    "blocked toilet", "toilet not working", "no working toilet",
)


def classify(description: str, *, reported_unsafe: bool = False) -> dict:
    """Return {"verdict", "reason", "metrics": {"sla", "matched"}}."""
    text = (description or "").lower()

    if reported_unsafe:
        return _result(Urgency.EMERGENCY,
                       "Tenant reports an unsafe situation — treated as an emergency.",
                       "tenant-reported unsafe")

    for sign in _EMERGENCY_SIGNS:
        if sign in text:
            return _result(Urgency.EMERGENCY,
                           f"Matched emergency indicator '{sign}'. Safety/habitability at risk.",
                           sign)

    for sign in _URGENT_SIGNS:
        if sign in text:
            return _result(Urgency.URGENT,
                           f"Matched urgent indicator '{sign}'. Affects safety, security, or daily life.",
                           sign)

    # A lock or door reported as faulty in any phrasing is a security/access
    # issue — urgent regardless of word order ("broken lock" / "lock is broken").
    _FAULT_WORDS = ("broken", "jam", "won't", "wont", "can't", "cant",
                    "not working", "stuck", "faulty", "stopped working")
    if any(w in text for w in ("lock", "door", "gate")) and any(f in text for f in _FAULT_WORDS):
        return _result(Urgency.URGENT,
                       "A lock/door/gate is reported faulty — a security and access issue.",
                       "lock/door fault")

    return _result(Urgency.ROUTINE,
                   "No emergency or urgent indicators detected.", None)


def _result(urgency: Urgency, reason: str, matched: str | None) -> dict:
    return {
        "verdict": urgency.value,
        "reason": reason,
        "metrics": {"sla": SLA[urgency], "matched": matched},
    }


if __name__ == "__main__":
    import json
    for d in ["I smell gas in the kitchen", "The front door lock is broken",
              "The kitchen tap drips a little"]:
        print(d, "->", json.dumps(classify(d)))
