"""
integrations/contractors.py — contractor dispatch (mockable).

In v1 this simulates booking a contractor and returns a job reference + ETA so the
orchestrator can coordinate access and follow up. Swap _book() for a real
scheduling/marketplace integration later.
"""

from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone


_ETA_BY_URGENCY = {
    "EMERGENCY": timedelta(hours=2),
    "URGENT": timedelta(hours=24),
    "ROUTINE": timedelta(days=3),
}


def dispatch(contractor: dict | None, *, fault: str, address: str,
             urgency: str) -> dict:
    """
    Book a contractor for a fault. Returns
    {"reference", "contractor", "trade", "eta", "fault", "address"}.
    """
    eta = (datetime.now(timezone.utc).replace(tzinfo=None)
           + _ETA_BY_URGENCY.get(urgency, timedelta(days=3)))
    job = {
        "reference": _book(contractor, fault, address),
        "contractor": (contractor or {}).get("name", "On-call contractor"),
        "trade": (contractor or {}).get("trade", "general"),
        "eta": eta.isoformat(timespec="minutes"),
        "fault": fault,
        "address": address,
    }
    print(f"  [CONTRACTOR] dispatched {job['contractor']} ({job['trade']}) "
          f"ref {job['reference']}, ETA {job['eta']}")
    return job


def _book(contractor: dict | None, fault: str, address: str) -> str:
    """Mock booking. Returns a job reference. Replace with a real integration."""
    return "JOB-" + uuid.uuid4().hex[:8].upper()
