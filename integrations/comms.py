"""
integrations/comms.py — party-facing outbound, channel-agnostic.

A message is addressed to ONE party and only that party's own contact details are
ever used. Cross-party contact details are never embedded — the drafter is told
not to include them, and nothing here adds them.

Delivery is gated two ways for safety:
  - COMMS_DRY_RUN (default on) → the message is logged + printed, never delivered.
  - the channel decides HOW it is delivered when dry-run is off.

The active channel is a process-level default (set by the inbound listener to
"whatsapp"); the CLI `intake` path leaves it at the env default.
"""

from __future__ import annotations
import os

from config import comms_dry_run
from db.store import log_communication

_DEFAULT_CHANNEL = os.environ.get("AGENT_CHANNEL", "whatsapp")


def set_default_channel(channel: str) -> None:
    global _DEFAULT_CHANNEL
    _DEFAULT_CHANNEL = channel


def send(case_id: int, to_party: dict, audience_role: str, subject: str,
         body: str, *, channel: str | None = None,
         from_party_id: int | None = None) -> dict:
    """
    Deliver (or, in dry-run, simulate) an outbound message and log it.
    Returns {"sent": bool, "dry_run": bool, "channel": str, "to": str}.
    """
    channel = channel or _DEFAULT_CHANNEL
    dry = comms_dry_run()
    to_name = to_party.get("name", f"party#{to_party.get('id')}")
    destination = to_party.get("phone") if channel in ("whatsapp", "sms") \
        else to_party.get("email")

    if not dry:
        _deliver(channel, destination, subject, body)

    log_communication(
        case_id=case_id, direction="out", channel=channel,
        from_party_id=from_party_id, to_party_id=to_party.get("id"),
        audience_role=audience_role, subject=subject, body=body,
    )

    tag = "[DRY-RUN] would send" if dry else "[SENT]"
    print(f"  {tag} → {to_name} ({audience_role}) via {channel}: {subject}")
    return {"sent": not dry, "dry_run": dry, "channel": channel, "to": to_name}


def _deliver(channel: str, destination: str | None, subject: str, body: str) -> None:
    """Real delivery. Reached only when COMMS_DRY_RUN=0."""
    if not destination:
        raise ValueError(f"no {channel} destination for this party")
    if channel == "whatsapp":
        from integrations.whatsapp import get_client
        # WhatsApp has no subject line; send the body (templates are self-contained).
        get_client().send(destination, body)
        return
    raise NotImplementedError(
        f"Live delivery for channel {channel!r} not wired. Use 'whatsapp', or keep "
        f"COMMS_DRY_RUN=1."
    )
