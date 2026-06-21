"""
core/cases.py — case status transitions, derived from engine verdicts.

Keeps the "what happens to the case next" logic in one place so the orchestrator
stays a thin wiring layer. Given the engine that ran and its verdict, derive the
case status and the next action to record.
"""

from __future__ import annotations

# Case statuses (must match db/schema.sql).
OPEN = "open"
AWAITING_PARTY = "awaiting_party"
AWAITING_APPROVAL = "awaiting_approval"
AWAITING_CONTRACTOR = "awaiting_contractor"
RESOLVED = "resolved"
ESCALATED = "escalated"


# (engine, verdict) -> (status, next_action). Anything money-/legal-touching
# lands on AWAITING_APPROVAL; the approval gate must clear before execution.
_TRANSITIONS = {
    ("maintenance", "TENANT_RESPONSIBILITY"): (RESOLVED, "Informed tenant it is their responsibility under the lease."),
    ("maintenance", "DISPATCH"):              (AWAITING_CONTRACTOR, "Contractor dispatched; awaiting completion."),
    ("maintenance", "EMERGENCY_DISPATCH"):    (AWAITING_CONTRACTOR, "Emergency contractor dispatched; landlord notified."),
    ("maintenance", "ASSESS"):                (AWAITING_CONTRACTOR, "Contractor dispatched to assess and quote; landlord notified."),
    ("maintenance", "APPROVE"):               (AWAITING_APPROVAL, "Awaiting landlord approval for the repair."),

    ("arrears", "CURRENT"):                    (RESOLVED, "Rent up to date; no action."),
    ("arrears", "REMINDER"):                   (AWAITING_PARTY, "Gentle reminder sent; awaiting payment."),
    ("arrears", "CONTACT"):                    (AWAITING_PARTY, "Tenant contacted; awaiting response."),
    ("arrears", "BREACH"):                     (AWAITING_APPROVAL, "Awaiting approval to issue a notice to remedy."),
    ("arrears", "LEGAL_RISK"):                 (ESCALATED, "Escalated to a human; advise landlord on recovery options."),

    ("dispute", "FACILITATE"):                 (AWAITING_PARTY, "Investigating; facilitating a resolution."),
    ("dispute", "NOTICE_WARRANTED"):           (AWAITING_APPROVAL, "Awaiting approval to issue a notice."),
    ("dispute", "ESCALATE"):                   (ESCALATED, "Escalated to a human (safety concern)."),

    ("renewal", "NOT_DUE"):                    (OPEN, "Renewal window not yet open."),
    ("renewal", "RENEW_FLAT"):                 (AWAITING_PARTY, "Renewal offered at current rent; awaiting both parties."),
    ("renewal", "RENEW_ADJUST"):               (AWAITING_APPROVAL, "Rent adjustment needs landlord approval."),

    ("end_of_tenancy", "NO_CLAIM"):            (AWAITING_PARTY, "Full deposit refund proposed; awaiting move-out completion."),
    ("end_of_tenancy", "CLAIM"):               (AWAITING_PARTY, "Itemised deductions sent; tenant response window open."),

    ("general", "RECEIVED"):                   (OPEN, "Message received and acknowledged; flagged for a human to follow up."),
    ("general", "REFERRAL"):                   (RESOLVED, "Legal question referred to a qualified professional."),
}


def derive(engine: str, verdict: str) -> dict:
    """Return {"status", "next_action"} for an engine verdict (sensible default)."""
    status, action = _TRANSITIONS.get((engine, verdict), (OPEN, "Review manually."))
    return {"status": status, "next_action": action}
