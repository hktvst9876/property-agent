"""
core/arrears.py — DETERMINISTIC rent-arrears escalation stage.

Reads the rent ledger and returns a proportionate stage. The point of the rules
is to avoid both over- and under-reacting:

  CURRENT     — nothing overdue.
  REMINDER    — day 1-2: gentle nudge; likely a banking delay.
  CONTACT     — day 3-6: direct contact to understand the situation.
  BREACH      — day 7-13: formal contractual notice to remedy (gated by approval).
  LEGAL_RISK  — day 14+: advise the landlord on recovery options (gated; legal
                facts only via legal_guard, with disclaimer + sources).

A tenant with a repeat-late history skips the gentle-reminder tone even on day 1.
"""

from __future__ import annotations
from datetime import date, datetime
from enum import Enum

from config import ARREARS


class ArrearsStage(str, Enum):
    CURRENT = "CURRENT"
    REMINDER = "REMINDER"
    CONTACT = "CONTACT"
    BREACH = "BREACH"
    LEGAL_RISK = "LEGAL_RISK"


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _outstanding(entry: dict) -> float:
    return (entry.get("amount_sgd") or 0) - (entry.get("paid_amount_sgd") or 0)


def assess(ledger: list[dict], as_of=None) -> dict:
    """Return {"verdict", "reason", "metrics"} from a tenancy's ledger rows."""
    today = _as_date(as_of) if as_of is not None else date.today()

    # Outstanding, past-due cycles.
    overdue = [e for e in ledger
               if _outstanding(e) > 0.005 and _as_date(e["due_date"]) <= today]
    days_overdue = max((today - _as_date(e["due_date"])).days for e in overdue) if overdue else 0
    amount_outstanding = round(sum(_outstanding(e) for e in overdue), 2)

    # Repeat-late history: any prior cycle paid after its due date, or still
    # outstanding, excluding the current oldest overdue cycle.
    prior_late = 0
    for e in ledger:
        if e.get("paid_date") and _as_date(e["paid_date"]) > _as_date(e["due_date"]):
            prior_late += 1
        elif _outstanding(e) > 0.005 and _as_date(e["due_date"]) < today:
            prior_late += 1
    # The current overdue cycle is counted above; don't let it inflate "prior".
    prior_late = max(0, prior_late - (1 if overdue else 0))
    repeat_offender = prior_late >= ARREARS.repeat_offender_cycles

    metrics = {
        "days_overdue": days_overdue,
        "amount_outstanding_sgd": amount_outstanding,
        "prior_late_cycles": prior_late,
        "repeat_offender": repeat_offender,
    }

    if not overdue or days_overdue <= 0:
        return _result(ArrearsStage.CURRENT, metrics, "Rent is up to date.")

    if days_overdue >= ARREARS.legal_risk_min_days:
        return _result(ArrearsStage.LEGAL_RISK, metrics,
            f"{days_overdue} days overdue (S${amount_outstanding:.2f}). Advise the "
            f"landlord on recovery options and the tenant of the risk; escalate the case.")

    if days_overdue >= ARREARS.breach_min_days:
        return _result(ArrearsStage.BREACH, metrics,
            f"{days_overdue} days overdue (S${amount_outstanding:.2f}). Issue a formal "
            f"notice to remedy per the tenancy agreement (subject to approval).")

    if days_overdue > ARREARS.reminder_max_days:
        return _result(ArrearsStage.CONTACT, metrics,
            f"{days_overdue} days overdue (S${amount_outstanding:.2f}). Contact the "
            f"tenant directly to understand the situation.")

    # Day 1-2.
    if repeat_offender:
        return _result(ArrearsStage.CONTACT, metrics,
            f"{days_overdue} day(s) overdue, but {prior_late} prior late cycle(s). "
            f"Skip the gentle reminder; contact the tenant directly.")
    return _result(ArrearsStage.REMINDER, metrics,
        f"{days_overdue} day(s) overdue (S${amount_outstanding:.2f}). Send a gentle "
        f"reminder; clean history, likely a banking delay.")


def _result(stage: ArrearsStage, metrics: dict, reason: str) -> dict:
    return {"verdict": stage.value, "reason": reason, "metrics": metrics}


if __name__ == "__main__":
    import json
    led = [{"due_date": "2026-06-01", "amount_sgd": 3000, "paid_amount_sgd": 0}]
    print(json.dumps(assess(led, as_of="2026-06-18"), indent=2))
