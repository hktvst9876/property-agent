"""
core/end_of_tenancy.py — DETERMINISTIC move-out assessment.

Compares the ingoing and outgoing condition of each item, separates fair wear and
tear (landlord's cost, never deductible) from tenant-caused damage, and itemises a
deduction from the security deposit. Singapore deposits are held privately by the
landlord, so this is a deduction-from-deposit, not a bond-authority claim.

  NO_CLAIM  — nothing deductible; refund the full deposit.
  CLAIM     — itemised deductions proposed (gated by approval). The tenant always
              gets a response/remedy window BEFORE any claim is finalised, and any
              dispute is a legal-risk stage routed through legal_guard.

Each item: {"item", "ingoing", "outgoing", "cost_sgd", "fair_wear_and_tear": bool}.
An item only counts if its outgoing condition differs from ingoing.
"""

from __future__ import annotations
from enum import Enum

from config import END_OF_TENANCY


class EotVerdict(str, Enum):
    NO_CLAIM = "NO_CLAIM"
    CLAIM = "CLAIM"


def assess(items: list[dict], deposit_sgd: float) -> dict:
    """Return {"verdict", "reason", "metrics"} with an itemised deduction."""
    deductible: list[dict] = []
    fair_wear: list[dict] = []

    for it in items:
        changed = str(it.get("ingoing")) != str(it.get("outgoing"))
        if not changed:
            continue
        if it.get("fair_wear_and_tear"):
            fair_wear.append({"item": it.get("item"), "note": it.get("outgoing")})
        else:
            deductible.append({
                "item": it.get("item"),
                "cost_sgd": round(float(it.get("cost_sgd") or 0), 2),
                "ingoing": it.get("ingoing"),
                "outgoing": it.get("outgoing"),
            })

    raw_total = round(sum(d["cost_sgd"] for d in deductible), 2)
    # Never deduct more than the deposit held.
    total_deduction = min(raw_total, deposit_sgd)
    refund = round(deposit_sgd - total_deduction, 2)

    metrics = {
        "deposit_sgd": deposit_sgd,
        "total_deduction_sgd": total_deduction,
        "uncapped_deduction_sgd": raw_total,
        "refund_sgd": refund,
        "deductible_items": deductible,
        "fair_wear_items": fair_wear,
        "response_window_days": END_OF_TENANCY.tenant_response_window_days,
    }

    if total_deduction <= 0:
        return _result(EotVerdict.NO_CLAIM, metrics,
            f"No tenant-caused damage beyond fair wear and tear. Refund the full "
            f"deposit of S${deposit_sgd:.2f}.")

    capped = " (capped at the deposit held)" if raw_total > deposit_sgd else ""
    return _result(EotVerdict.CLAIM, metrics,
        f"Proposed deductions of S${total_deduction:.2f}{capped} across "
        f"{len(deductible)} item(s); proposed refund S${refund:.2f}. The tenant has "
        f"{END_OF_TENANCY.tenant_response_window_days} days to respond or remedy "
        f"before any claim is finalised.")


def _result(verdict: EotVerdict, metrics: dict, reason: str) -> dict:
    return {"verdict": verdict.value, "reason": reason, "metrics": metrics}


if __name__ == "__main__":
    import json
    items = [
        {"item": "Living room wall", "ingoing": "clean", "outgoing": "minor scuffs",
         "cost_sgd": 0, "fair_wear_and_tear": True},
        {"item": "Kitchen countertop", "ingoing": "intact", "outgoing": "burn mark",
         "cost_sgd": 450, "fair_wear_and_tear": False},
    ]
    print(json.dumps(assess(items, 6000), indent=2))
