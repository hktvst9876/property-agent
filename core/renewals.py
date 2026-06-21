"""
core/renewals.py — DETERMINISTIC lease-renewal trigger and rent recommendation.

Fires proactively as expiry approaches and compares the current rent to a market
comparable:

  NOT_DUE       — more than the lead window away; nothing to do yet.
  RENEW_FLAT    — within the window; comparable is within the tolerance band, so
                  recommend renewing at the current rent.
  RENEW_ADJUST  — within the window; comparable is outside the band, so recommend
                  a rent adjustment toward the comparable (a raise is gated by approval).

Whether either party actually wants to renew is decided by their responses, not
by this math — the orchestrator handles a NON_RENEWAL path from those answers.
"""

from __future__ import annotations
from datetime import date, datetime
from enum import Enum

from config import RENEWAL


class RenewalVerdict(str, Enum):
    NOT_DUE = "NOT_DUE"
    RENEW_FLAT = "RENEW_FLAT"
    RENEW_ADJUST = "RENEW_ADJUST"


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def assess(end_date, current_rent_sgd: float, comparable_rent_sgd: float | None = None,
           as_of=None) -> dict:
    """Return {"verdict", "reason", "metrics"}."""
    today = _as_date(as_of) if as_of is not None else date.today()
    days_to_expiry = (_as_date(end_date) - today).days

    comparable = comparable_rent_sgd if comparable_rent_sgd else current_rent_sgd
    pct_diff = (comparable - current_rent_sgd) / current_rent_sgd if current_rent_sgd else 0.0

    metrics = {
        "days_to_expiry": days_to_expiry,
        "current_rent_sgd": current_rent_sgd,
        "comparable_rent_sgd": comparable,
        "pct_diff": round(pct_diff, 4),
        "recommended_rent_sgd": current_rent_sgd,
    }

    if days_to_expiry > RENEWAL.lead_days:
        return _result(RenewalVerdict.NOT_DUE, metrics,
            f"Lease expires in {days_to_expiry} days; renewal process opens at "
            f"{RENEWAL.lead_days} days out.")

    if abs(pct_diff) <= RENEWAL.rent_adjust_band_pct:
        return _result(RenewalVerdict.RENEW_FLAT, metrics,
            f"Expires in {days_to_expiry} days. Market comparable (S${comparable:.0f}) "
            f"is within {RENEWAL.rent_adjust_band_pct*100:.0f}% of current rent; "
            f"recommend renewing at the current rent.")

    metrics["recommended_rent_sgd"] = round(comparable, 2)
    direction = "increase" if pct_diff > 0 else "reduction"
    return _result(RenewalVerdict.RENEW_ADJUST, metrics,
        f"Expires in {days_to_expiry} days. Comparable (S${comparable:.0f}) implies a "
        f"{abs(pct_diff)*100:.1f}% {direction} from S${current_rent_sgd:.0f}; recommend "
        f"renewing at ~S${comparable:.0f} (a raise needs landlord approval).")


def _result(verdict: RenewalVerdict, metrics: dict, reason: str) -> dict:
    return {"verdict": verdict.value, "reason": reason, "metrics": metrics}


if __name__ == "__main__":
    import json
    print(json.dumps(assess("2026-08-31", 3000, 3400, as_of="2026-06-20"), indent=2))
