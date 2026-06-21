"""
core/maintenance.py — DETERMINISTIC repair authority gate.

Given an estimated cost, the urgency band, and the spend limits in force, decide
who pays and whether the agent may act alone:

  TENANT_RESPONSIBILITY — cost is within the tenant's minor-repair cap.
  DISPATCH              — within the landlord's pre-approved threshold; the agent
                          may book a contractor directly and notify the landlord.
  APPROVE              — above the threshold; queue a landlord approval first.
  EMERGENCY_DISPATCH    — emergency: act first, notify immediately, even over the
                          threshold (per the master prompt's emergency rule).

Recurrence is flagged (not a verdict change): a fault re-reported inside the
window needs root-cause attention, so an otherwise-DISPATCH job is escalated to
APPROVE so the landlord sees the pattern and signs off on a proper fix.
"""

from __future__ import annotations
from enum import Enum

from config import MAINTENANCE


class RepairVerdict(str, Enum):
    TENANT_RESPONSIBILITY = "TENANT_RESPONSIBILITY"
    DISPATCH = "DISPATCH"
    APPROVE = "APPROVE"
    EMERGENCY_DISPATCH = "EMERGENCY_DISPATCH"
    ASSESS = "ASSESS"   # cost unknown (e.g. inbound text) -> send a contractor to quote


def gate(estimated_cost_sgd: float | None, urgency: str, *,
         minor_repair_cap_sgd: float | None = None,
         landlord_threshold_sgd: float | None = None,
         recurrence_count: int = 0) -> dict:
    """Return {"verdict", "reason", "metrics"}. estimated_cost_sgd may be None when
    the cost isn't known yet (a tenant's message rarely includes one)."""
    cap = (minor_repair_cap_sgd if minor_repair_cap_sgd is not None
           else MAINTENANCE.default_minor_repair_cap_sgd)
    threshold = (landlord_threshold_sgd if landlord_threshold_sgd is not None
                 else MAINTENANCE.default_landlord_threshold_sgd)
    recurring = recurrence_count > 0

    metrics = {
        "estimated_cost_sgd": estimated_cost_sgd,
        "minor_repair_cap_sgd": cap,
        "landlord_threshold_sgd": threshold,
        "recurrence_count": recurrence_count,
        "emergency": urgency == "EMERGENCY",
    }

    # 1. Emergencies override the money gate entirely.
    if urgency == "EMERGENCY":
        return _result(RepairVerdict.EMERGENCY_DISPATCH, metrics,
            "Emergency: dispatching a contractor immediately and notifying the "
            "landlord at once, ahead of the usual approval gate.")

    # 2. Cost not yet known — send someone to assess and quote, and notify the landlord.
    if estimated_cost_sgd is None:
        return _result(RepairVerdict.ASSESS, metrics,
            "Cost not yet known. Arranging a contractor to assess and quote the "
            "repair, and notifying the landlord.")

    # 3. Within the tenant's minor-repair cap.
    if estimated_cost_sgd <= cap:
        return _result(RepairVerdict.TENANT_RESPONSIBILITY, metrics,
            f"Estimated S${estimated_cost_sgd:.0f} is within the tenant's minor-repair "
            f"cap of S${cap:.0f}; this is the tenant's responsibility under the lease.")

    # 4. A recurring fault should be looked at properly, not patched again.
    if recurring:
        return _result(RepairVerdict.APPROVE, metrics,
            f"Recurring fault (reported {recurrence_count} time(s) before). "
            f"Recommend landlord approve a root-cause repair rather than another "
            f"temporary fix. Estimated S${estimated_cost_sgd:.0f}.")

    # 5. Within the landlord's pre-approved threshold — act and notify.
    if estimated_cost_sgd <= threshold:
        return _result(RepairVerdict.DISPATCH, metrics,
            f"Estimated S${estimated_cost_sgd:.0f} is within the landlord's "
            f"pre-approved threshold of S${threshold:.0f}; dispatching a contractor "
            f"and notifying the landlord.")

    # 6. Above threshold — needs landlord sign-off.
    return _result(RepairVerdict.APPROVE, metrics,
        f"Estimated S${estimated_cost_sgd:.0f} exceeds the landlord's threshold of "
        f"S${threshold:.0f}; landlord approval required before proceeding.")


def _result(verdict: RepairVerdict, metrics: dict, reason: str) -> dict:
    return {"verdict": verdict.value, "reason": reason, "metrics": metrics}


if __name__ == "__main__":
    import json
    print(json.dumps(gate(80, "ROUTINE"), indent=2))
    print(json.dumps(gate(1200, "URGENT"), indent=2))
    print(json.dumps(gate(2000, "EMERGENCY"), indent=2))
