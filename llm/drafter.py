"""
llm/drafter.py — turn a deterministic verdict into a party-facing message.

The engines in core/ decide WHAT happens. The drafter decides HOW it's worded for
the audience. It reads the person's actual message to gauge their mood and respond
accordingly (warm, de-escalating, specific). The decision and any legal facts are
FIXED inputs it may phrase but never change.

Default path is built-in, mood-aware templates — no model, no API. If an LLM
provider is configured (an API key is set), it's used instead, and the templates
remain the fallback so the agent never breaks.
"""

from __future__ import annotations
import json

from llm.router import ask_json, get_provider, TaskType
from llm.prompts import DRAFT_MESSAGE, PROPERTY_AGENT_SYSTEM, AUDIENCE_TONE


def _model_available() -> bool:
    try:
        return get_provider(TaskType.DRAFTING).available()
    except Exception:
        return False


def draft_message(audience_role: str, verdict: str, reason: str, *,
                  context: dict | None = None,
                  legal: dict | None = None,
                  inbound_message: str | None = None,
                  recipient_name: str | None = None) -> dict:
    """
    Returns {"subject", "body"}.

    audience_role:    tenant | landlord | contractor | body_corporate | council | other
    verdict/reason:   the deterministic decision being communicated (reason = what to say)
    context:          facts safe to share (e.g. {"fault": "...", "appointment": "..."})
    legal:            optional core.legal_guard.surface() output (disclaimer + sources)
    inbound_message:  the recipient's own latest message, so the model can read mood.
                      None when we're reaching out proactively (e.g. a sweep).
    recipient_name:   the recipient's actual name, so the greeting is personal and the
                      model never writes a bracketed placeholder like "[Landlord]".
    """
    audience_role = audience_role if audience_role in AUDIENCE_TONE else "other"

    if not _model_available():
        return _fallback(audience_role, verdict, reason, context, legal,
                         inbound_message, recipient_name)

    payload = {
        "recipient": audience_role,
        "recipient_name": recipient_name,
        "tone": AUDIENCE_TONE[audience_role],
        "verdict": verdict,
        "what_to_communicate": reason,
        "context": context or {},
        "original_message_from_recipient": inbound_message,
    }
    if legal:
        payload["legal_facts"] = legal.get("facts", [])
        payload["disclaimer"] = legal.get("disclaimer", "")
        payload["sources"] = legal.get("sources", [])

    result = ask_json(
        TaskType.DRAFTING,
        system=PROPERTY_AGENT_SYSTEM + "\n\n" + DRAFT_MESSAGE,
        user=json.dumps(payload, indent=2, default=str),
        max_tokens=700,
    )
    if "_error" in result or "body" not in result:
        return _fallback(audience_role, verdict, reason, context, legal,
                         inbound_message, recipient_name)
    return result


# --------------------------------------------------------------------------
# Built-in message composer. Deterministic, no model required. Reads the sender's
# mood (from their message) so even template replies open with appropriate empathy.
# --------------------------------------------------------------------------
# Empathetic openers, used for the person who wrote in (tenants/contractors), so an
# angry or worried message is acknowledged before the substance.
_OPENERS = {
    "angry": "I'm really sorry for the trouble — I completely understand the "
             "frustration, and I'll make sure this is taken care of. ",
    "distressed": "Thanks for reaching out, and I'm sorry you're dealing with this. "
                  "Let's get it sorted as quickly as we can. ",
    "calm": "",
}


def _fallback(audience_role: str, verdict: str, reason: str,
              context: dict | None, legal: dict | None,
              inbound_message: str | None = None,
              recipient_name: str | None = None) -> dict:
    from core.intake_parser import sentiment

    if recipient_name:
        greeting = f"Hello {recipient_name},"
    else:
        greeting = {
            "tenant": "Hello,",
            "landlord": "Dear Landlord,",
            "contractor": "Hello,",
            "body_corporate": "To whom it may concern,",
            "council": "To whom it may concern,",
            "other": "Hello,",
        }.get(audience_role, "Hello,")

    # Only mirror mood when writing back to the person who messaged us.
    opener = ""
    if inbound_message and audience_role in ("tenant", "contractor", "other"):
        opener = _OPENERS.get(sentiment(inbound_message), "")

    lines = [greeting, "", (opener + reason.strip()).strip()]

    ctx = context or {}
    detail_keys = [k for k in ("address", "fault", "access", "due_date", "amount_sgd",
                               "appointment", "next_step", "note") if k in ctx]
    if detail_keys:
        lines.append("")
        for k in detail_keys:
            lines.append(f"- {k.replace('_', ' ').title()}: {ctx[k]}")

    if legal:
        lines.append("")
        for fact in legal.get("facts", []):
            lines.append(f"- {fact}")
        srcs = ", ".join(s.get("citation", "") for s in legal.get("sources", []))
        if srcs:
            lines.append(f"  (Source: {srcs})")
        lines.append("")
        lines.append(legal.get("disclaimer", ""))

    lines += ["", "The Property Management Team"]

    subject = {
        "tenant": "An update on your request",
        "landlord": f"Action required: {verdict}",
        "contractor": "Job request",
        "body_corporate": "Notice from the managing agent",
        "council": "Notice from the managing agent",
        "other": "A message from your property manager",
    }.get(audience_role, "A message from your property manager")

    return {"subject": subject, "body": "\n".join(lines)}
