"""
core/intake_parser.py — DETERMINISTIC inbound message understanding.

Turns a free-text message into structured signals the orchestrator can act on:
  - intents:   zero or more actionable issues (a single message can hold several,
               e.g. "rent late and the toilet is choked" -> arrears + maintenance)
  - follow_up: whether it's a reply on an existing matter (chasing, ack, confirming)
  - sentiment: a coarse emotional read so even template replies can open with empathy

Keyword-based, no LLM (the deliberate trade of the no-model design). It leans
toward catching how people in Singapore actually text — Singlish and synonyms
included ("aircon spoil liao", "toilet choke", "cannot on") — and is conservative:
anything it can't place becomes a general acknowledgement, never a wrong action.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Intent vocabulary
# ---------------------------------------------------------------------------
# Order within a category doesn't matter; categories are checked independently so
# multiple intents can fire from one message.
_MAINTENANCE = (
    "leak", "leaking", "broken", "spoil", "spoilt", "not working", "no working",
    "doesn't work", "won't work", "stopped working", "cannot use", "cannot on",
    "can't on", "died", "dead", "no water", "no hot water", "no power",
    "no electricity", "blackout", "aircon", "air con", "air-con", "tap",
    "toilet", "pipe", "sink", "drain", "choke", "choked", "clog", "blocked",
    "fridge", "refrigerator", "oven", "stove", "heater", "light", "bulb", "fan",
    "wire", "socket", "switch", "lock", "door", "window", "gas", "fix", "repair",
    "faulty", "flood", "burst", "electrical", "plumbing", "mould", "mold",
    "pest", "cockroach", "ceiling", "wall crack", "wet",
)
_RENT = ("rent", "payment", "pay the", "paid the", "haven't paid", "havent paid",
         "transfer for", "giro", "paynow", "outstanding", "owe")
_DISPUTE = ("noise", "loud", "neighbour", "neighbor", "complain", "complaint",
            "harass", "threat", "smoking", "smell of smoke", "party next",
            "disturb", "nuisance", "banging", "shouting", "music")
_RENEWAL = ("renew", "extend the lease", "extend lease", "extend my lease",
            "lease ending", "lease expir", "stay longer", "another year", "renewal")
_MOVE_OUT = ("moving out", "move out", "vacate", "not renew", "won't renew",
             "wont renew", "ending the lease", "terminate the lease", "give notice",
             "hand back", "handing back")

# Maintenance trade routing, so the right contractor is dispatched.
_TRADE = {
    "plumber": ("water", "tap", "toilet", "pipe", "sink", "drain", "leak", "flood",
                "burst", "hot water", "plumbing", "blocked", "choke", "clog", "wet"),
    "electrician": ("power", "electric", "electrical", "light", "bulb", "wire",
                    "socket", "switch", "fan", "blackout"),
    "locksmith": ("lock", "door", "gate", "key"),
    "aircon": ("aircon", "air con", "air-con"),
}
_CATEGORY = {
    "noise": ("noise", "loud", "banging", "shouting", "party next", "disturb", "music"),
    "behaviour": ("harass", "threat", "smoking", "smell of smoke"),
}

# ---------------------------------------------------------------------------
# Follow-up vocabulary (a reply on an existing matter, not a new issue)
# ---------------------------------------------------------------------------
# Kept specific on purpose: bare "still" / "can" / "yes" appear in normal reports
# ("water still running", "cannot use", "yesterday") and would misfire.
_STATUS_CHASE = ("any update", "update?", "still waiting", "still not", "not fixed",
                 "not yet fixed", "where is", "where are", "when will", "how long",
                 "hello?", "anyone", "chasing", "follow up", "followup", "still broken",
                 "still no", "any news", "what's happening", "whats happening")
_ACK = ("ok thanks", "okay thanks", "thank you", "thanks", "noted", "received",
        "got it", "great thanks", "appreciate it", "cheers")
_CONFIRM = ("confirm", "that works", "works for me", "i'll be home", "i will be home",
            "sounds good", "ok that", "okay that", "yes please", "yes that")

# ---------------------------------------------------------------------------
# Sentiment vocabulary
# ---------------------------------------------------------------------------
_DISTRESS = ("scared", "afraid", "frightened", "worried", "anxious", "desperate",
             "please help", "help me", "emergency", "urgent", "asap", "can't cope",
             "cannot cope", "stressed", "no water", "no power", "flooding")
_ANGRY = ("unacceptable", "ridiculous", "furious", "angry", "fed up", "sick of",
          "disgrace", "terrible", "appalling", "useless", "!!", "again", "still",
          "third time", "second time", "how many times", "keep happening", "joke")


def _has_any(text: str, words) -> str | None:
    for w in words:
        if w in text:
            return w
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def detect_intents(text: str) -> list[dict]:
    """Return every actionable intent in the message (possibly several).
    Each item: {"intent", "matched", "hints"}."""
    t = (text or "").lower()
    intents: list[dict] = []

    m = _has_any(t, _MAINTENANCE)
    if m:
        intents.append({"intent": "maintenance", "matched": m,
                        "hints": {"trade": _trade_for(t)}})

    m = _has_any(t, _RENT)
    if m:
        intents.append({"intent": "arrears", "matched": m, "hints": {}})

    # move_out and renewal overlap ("not renew" contains "renew") — move_out wins.
    mo = _has_any(t, _MOVE_OUT)
    if mo:
        intents.append({"intent": "move_out", "matched": mo, "hints": {}})
    else:
        rn = _has_any(t, _RENEWAL)
        if rn:
            intents.append({"intent": "renewal", "matched": rn, "hints": {}})

    m = _has_any(t, _DISPUTE)
    if m:
        intents.append({"intent": "dispute", "matched": m,
                        "hints": {"category": _category_for(t)}})

    return intents


def classify_followup(text: str) -> str | None:
    """Is this a reply on an existing matter? -> status_chase | acknowledgement |
    confirmation | None."""
    t = (text or "").lower()
    if _has_any(t, _STATUS_CHASE):
        return "status_chase"
    if _has_any(t, _ACK):
        return "acknowledgement"
    if _has_any(t, _CONFIRM):
        return "confirmation"
    return None


def sentiment(text: str) -> str:
    """'distressed' | 'angry' | 'calm' from a message. Deterministic."""
    t = (text or "").lower()
    if _has_any(t, _DISTRESS):
        return "distressed"
    if _has_any(t, _ANGRY):
        return "angry"
    return "calm"


def parse(text: str) -> dict:
    """Full read of an inbound message."""
    return {
        "intents": detect_intents(text),
        "follow_up": classify_followup(text),
        "sentiment": sentiment(text),
    }


def _trade_for(text: str) -> str:
    for trade, words in _TRADE.items():
        if any(w in text for w in words):
            return trade
    return "general"


def _category_for(text: str) -> str:
    for cat, words in _CATEGORY.items():
        if any(w in text for w in words):
            return cat
    return "other"


if __name__ == "__main__":
    import json
    for s in ["aircon spoil liao, so hot", "rent late sorry and the toilet is choked",
              "any update? still waiting", "ok thanks", "we're moving out next month"]:
        print(s, "->", json.dumps(parse(s)))
