"""
orchestrator.py — the agent's main loop.

Two entry points:

  handle_event(event)            — a structured situation (CLI/tests/sweeps).
  handle_inbound(from_phone, text) — a raw inbound message (WhatsApp). Resolves the
                                     sender, understands the text (llm.understand),
                                     runs the right engine, and replies on the same
                                     channel. This is the "replace me texting them"
                                     path: messages flow in and out automatically.

In both cases the DETERMINISTIC engines decide and the LLM/templates only phrase.
Nothing money-/legal-touching executes without an approval.
"""

from __future__ import annotations
import json
import sys
from datetime import datetime, timezone

from config import JURISDICTION
from core import (
    triage, maintenance, arrears, disputes, renewals, end_of_tenancy, cases,
)
from core.legal_guard import (
    is_legal_question, refuse, surface, LegalGuardEscalation,
)
from llm.drafter import draft_message
from llm.understand import understand_message
from integrations import comms, contractors
from db.store import (
    get_tenancy, get_property, get_party, find_contractor, prior_fault_reports,
    ledger_for_tenancy, active_tenancies, find_party_by_phone, tenancy_for_party,
    open_case, update_case, get_case, record_decision, queue_approval,
    record_complaint, log_communication, latest_open_case_for_tenancy,
    inbound_count_for_case, cases_by_status, decision_count,
)
from approvals.telegram_bot import push_pending_approvals
from notify import notify_operator


# -------------------------------------------------------------------------
# Small helpers
# -------------------------------------------------------------------------
def _resolve_parties(tenancy_id: int) -> tuple[dict, dict, dict, dict]:
    """Return (tenancy, property, tenant, landlord)."""
    tenancy = get_tenancy(tenancy_id)
    if not tenancy:
        raise ValueError(f"tenancy {tenancy_id} not found")
    prop = get_property(tenancy["property_id"])
    tenant = get_party(tenancy["tenant_party_id"])
    landlord = get_party(prop["landlord_party_id"]) if prop else None
    return tenancy, prop, tenant, landlord


# When handling an inbound message, the sender's raw text is stashed here so the
# drafter can read THEIR mood when we reply to THEM (and only them).
_INBOUND: dict = {}


def _send(case_id: int, party: dict | None, audience_role: str, verdict: str,
          reason: str, *, context: dict | None = None, legal: dict | None = None) -> None:
    if not party:
        return
    inbound = (_INBOUND.get("message")
               if party.get("id") == _INBOUND.get("sender_id") else None)
    draft = draft_message(audience_role, verdict, reason, context=context,
                          legal=legal, inbound_message=inbound,
                          recipient_name=party.get("name"))
    comms.send(case_id, party, audience_role, draft["subject"], draft["body"])


def _finish(case_id: int, engine: str, decision: dict, action_taken: str) -> dict:
    """Record the decision, advance case state, notify, push approvals."""
    record_decision(case_id, engine, decision["verdict"], decision["reason"],
                    decision.get("metrics"))
    transition = cases.derive(engine, decision["verdict"])
    update_case(case_id, status=transition["status"], next_action=transition["next_action"])
    case = get_case(case_id)
    notify_operator(case, decision, action_taken)
    push_pending_approvals()
    return {"case_id": case_id, "engine": engine, **decision,
            "status": transition["status"], "next_action": transition["next_action"]}


def _surface_or_escalate(case_id: int, stage: str) -> dict | None:
    """Try to surface guarded legal facts; on failure, escalate and return None."""
    try:
        return surface(stage, JURISDICTION)
    except LegalGuardEscalation as exc:
        update_case(case_id, status=cases.ESCALATED, escalated_reason=str(exc))
        queue_approval("escalate_human", {"reason": str(exc)}, case_id=case_id)
        return None


# -------------------------------------------------------------------------
# Per-type handlers
# -------------------------------------------------------------------------
def _handle_maintenance(event: dict) -> dict:
    tenancy, prop, tenant, landlord = _resolve_parties(event["tenancy_id"])
    desc = event.get("description", "")
    # Clean, agent's-POV wording for anything relayed outward (landlord/contractor).
    # Falls back to the tenant's raw words on the offline keyword path. The raw `desc`
    # is kept for the case record, triage, and recurrence matching below.
    relayed = event.get("fault_summary") or desc

    case_id = open_case("maintenance", desc, property_id=prop["id"],
                        tenancy_id=tenancy["id"], opened_by_party_id=tenant["id"])

    urg = triage.classify(desc, reported_unsafe=event.get("reported_unsafe", False))
    record_decision(case_id, "triage", urg["verdict"], urg["reason"], urg["metrics"])
    update_case(case_id, urgency=urg["verdict"])

    recurrence = prior_fault_reports(tenancy["id"], event.get("fault_keyword", desc[:20]))
    decision = maintenance.gate(
        event.get("estimated_cost_sgd"), urg["verdict"],
        minor_repair_cap_sgd=tenancy.get("minor_repair_cap_sgd"),
        landlord_threshold_sgd=prop.get("repair_threshold_sgd"),
        recurrence_count=recurrence,
    )
    verdict = decision["verdict"]
    has_media = event.get("has_media")
    ctx = {"fault": relayed, "address": prop["address"]}
    if has_media:
        ctx["note"] = "Tenant attached photo(s)."

    if verdict in ("DISPATCH", "EMERGENCY_DISPATCH", "ASSESS"):
        fault_brief = relayed + (" (tenant sent photo(s))" if has_media else "")
        job = contractors.dispatch(find_contractor(event.get("trade", "general")),
                                   fault=fault_brief, address=prop["address"],
                                   urgency=urg["verdict"])
        ctx["appointment"] = f"{job['contractor']} (ref {job['reference']}), ETA {job['eta']}"
        update_case(case_id, next_action_at=job["eta"])   # so follow-up sweep can chase
        tenant_msg = {
            "EMERGENCY_DISPATCH": "Thanks for flagging this — we're treating it as "
                "urgent and have arranged for a contractor to attend right away.",
            "ASSESS": "Thanks for letting us know. We've arranged for a contractor to "
                "come and take a look and provide a quote.",
            "DISPATCH": "Thanks for reporting this. We've arranged for a contractor to "
                "take care of it.",
        }[verdict]
        landlord_msg = {
            "EMERGENCY_DISPATCH": "We treated this as an emergency and dispatched a "
                "contractor immediately, ahead of the usual approval step.",
            "ASSESS": "We've arranged a contractor to assess the issue and will confirm "
                "the cost with you before any chargeable work.",
            "DISPATCH": "This is within your pre-approved threshold, so we've arranged a "
                "contractor and it will be charged to your account.",
        }[verdict]
        _send(case_id, tenant, "tenant", verdict, tenant_msg, context=ctx)
        _send(case_id, landlord, "landlord", verdict, landlord_msg,
              context={"address": prop["address"], "fault": relayed})
        action = f"Dispatched {job['contractor']} (ref {job['reference']})."
    elif verdict == "APPROVE":
        queue_approval("approve_repair",
                       {"estimated_cost_sgd": event.get("estimated_cost_sgd"),
                        "fault": relayed, "address": prop["address"],
                        "reason": decision["reason"]}, case_id=case_id)
        _send(case_id, landlord, "landlord", verdict, decision["reason"],
              context={"address": prop["address"], "fault": relayed})
        _send(case_id, tenant, "tenant", "ACKNOWLEDGED",
              "Thanks for reporting this. We've logged it and are arranging the next step.",
              context={"fault": relayed})
        action = "Queued landlord approval for over-threshold repair."
    else:  # TENANT_RESPONSIBILITY
        _send(case_id, tenant, "tenant", verdict, decision["reason"], context=ctx)
        action = "Informed tenant of minor-repair responsibility."

    return _finish(case_id, "maintenance", decision, action)


def _handle_arrears(event: dict, *, case_id: int | None = None) -> dict:
    tenancy, prop, tenant, landlord = _resolve_parties(event["tenancy_id"])
    inbound = event.get("inbound", False)
    ledger = ledger_for_tenancy(tenancy["id"])
    decision = arrears.assess(ledger, as_of=event.get("as_of"))
    verdict = decision["verdict"]

    if case_id is None:
        case_id = open_case("arrears", decision["reason"], property_id=prop["id"],
                            tenancy_id=tenancy["id"], opened_by_party_id=tenant["id"])

    m = decision["metrics"]
    amt, days = m["amount_outstanding_sgd"], m["days_overdue"]
    ctx = {"amount_sgd": amt}
    addr = prop["address"]
    legal = None
    action = ""

    if verdict == "CURRENT":
        if inbound:
            _send(case_id, tenant, "tenant", "CURRENT",
                  "Your rent is up to date — there's nothing outstanding. Thank you!")
        action = "Rent up to date; no action."
    elif verdict == "REMINDER":
        _send(case_id, tenant, "tenant", verdict,
              f"Just a friendly reminder that your rent of S${amt:.0f} appears "
              f"outstanding ({days} day(s)). If you've already paid, please ignore "
              f"this — it may simply be a banking delay.", context=ctx)
        action = "Sent gentle reminder to tenant."
    elif verdict == "CONTACT":
        _send(case_id, tenant, "tenant", verdict,
              f"We noticed your rent of S${amt:.0f} is now {days} days overdue. Could "
              f"you let us know when we can expect payment, or if there's anything we "
              f"should be aware of?", context=ctx)
        action = "Contacted tenant directly."
    elif verdict == "BREACH":
        queue_approval("issue_notice",
                       {"kind": "notice_to_remedy", "reason": decision["reason"],
                        "amount_sgd": amt}, case_id=case_id)
        _send(case_id, tenant, "tenant", verdict,
              f"Your rent of S${amt:.0f} is now {days} days overdue. We may need to "
              f"issue a formal notice to remedy under your tenancy agreement — please "
              f"arrange payment as soon as possible, or get in touch to discuss.", context=ctx)
        _send(case_id, landlord, "landlord", verdict,
              f"Rent at {addr} is {days} days overdue (S${amt:.0f}). With your approval "
              f"we'll issue a formal notice to remedy under the tenancy agreement.", context=ctx)
        action = "Queued approval to issue a notice to remedy; landlord informed."
    elif verdict == "LEGAL_RISK":
        legal = _surface_or_escalate(case_id, "arrears_legal_risk")
        queue_approval("escalate_human", {"reason": decision["reason"], "amount_sgd": amt},
                       case_id=case_id)
        _send(case_id, tenant, "tenant", verdict,
              f"Your rent of S${amt:.0f} is now {days} days overdue. This has reached a "
              f"stage where the matter may be escalated. Please contact us urgently to "
              f"arrange payment so we can avoid further steps.", context=ctx, legal=legal)
        _send(case_id, landlord, "landlord", verdict,
              f"Rent at {addr} is {days} days overdue (S${amt:.0f}). We've flagged this "
              f"for escalation and can advise on recovery options.", context=ctx, legal=legal)
        action = "Escalated to human; tenant and landlord informed of risk (sourced)."

    return _finish(case_id, "arrears", decision, action)


def _handle_dispute(event: dict) -> dict:
    tenancy, prop, tenant, landlord = _resolve_parties(event["tenancy_id"])
    complainant_id = event.get("complainant_party_id", tenant["id"])
    subject_id = event.get("subject_party_id")
    anonymity = event.get("anonymity", True)

    case_id = open_case("dispute", event.get("description", ""), property_id=prop["id"],
                        tenancy_id=tenancy["id"], opened_by_party_id=complainant_id)
    record_complaint(case_id, complainant_id, event.get("category", "other"),
                     event.get("description", ""), subject_party_id=subject_id,
                     evidence={"has_media": True} if event.get("has_media") else None,
                     anonymity=anonymity)

    decision = disputes.assess(
        event.get("category", "other"), event.get("description", ""),
        lease_or_bylaw_breached=event.get("lease_or_bylaw_breached", False),
        anonymity=anonymity,
        safety_flag=event.get("safety_flag"),
    )
    verdict = decision["verdict"]
    subject = get_party(subject_id) if subject_id else None
    complainant = get_party(complainant_id)
    # The subject is only ever told "we received a complaint" — never who made it.
    ctx = {"next_step": "We received a complaint and are looking into it."}

    if verdict == "ESCALATE":
        queue_approval("escalate_human", {"reason": decision["reason"]}, case_id=case_id)
        _send(case_id, complainant, complainant["role"], "ACKNOWLEDGED",
              "Thank you for raising this. Given its nature we are escalating it for "
              "urgent attention and will keep you updated.")
        action = "Escalated to human (safety)."
    elif verdict == "NOTICE_WARRANTED":
        queue_approval("issue_notice",
                       {"kind": "breach_notice", "reason": decision["reason"]},
                       case_id=case_id)
        _send(case_id, subject, subject["role"] if subject else "tenant",
              verdict, decision["reason"], context=ctx)
        _send(case_id, complainant, complainant["role"], "ACKNOWLEDGED",
              "Thank you for the report. We're addressing it with the relevant party. "
              "Your identity is kept confidential.")
        action = "Queued approval to issue a notice; complainant kept anonymous."
    else:  # FACILITATE
        _send(case_id, subject, subject["role"] if subject else "tenant",
              verdict, decision["reason"], context=ctx)
        _send(case_id, complainant, complainant["role"], "ACKNOWLEDGED",
              "Thank you for letting us know. We're looking into it and your identity "
              "is kept confidential.")
        action = "Investigating and facilitating; complainant kept anonymous."

    return _finish(case_id, "dispute", decision, action)


def _handle_renewal(event: dict, *, case_id: int | None = None) -> dict:
    tenancy, prop, tenant, landlord = _resolve_parties(event["tenancy_id"])
    inbound = event.get("inbound", False)
    decision = renewals.assess(tenancy["end_date"], tenancy["rent_sgd"],
                               event.get("comparable_rent_sgd"), as_of=event.get("as_of"))
    verdict = decision["verdict"]

    if case_id is None:
        case_id = open_case("renewal", decision["reason"], property_id=prop["id"],
                            tenancy_id=tenancy["id"])

    rec = decision["metrics"]["recommended_rent_sgd"]
    ctx = {"next_step": f"Lease expires {tenancy['end_date']}."}
    action = ""

    if verdict == "NOT_DUE":
        if inbound:
            _send(case_id, tenant, "tenant", "NOT_DUE",
                  f"Your lease runs until {tenancy['end_date']}. We'll be in touch about "
                  f"renewal around 90 days before then — but happy to note your interest now.")
        action = "Renewal window not open yet."
    elif verdict == "RENEW_FLAT":
        _send(case_id, landlord, "landlord", verdict, decision["reason"], context=ctx)
        _send(case_id, tenant, "tenant", verdict,
              "Your lease is approaching its end date and we'd be glad to renew it at "
              "the current rent. Please let us know if you'd like to.", context=ctx)
        action = "Offered flat renewal to both parties."
    elif verdict == "RENEW_ADJUST":
        queue_approval("raise_rent",
                       {"current_rent_sgd": tenancy["rent_sgd"],
                        "recommended_rent_sgd": rec, "reason": decision["reason"]},
                       case_id=case_id)
        _send(case_id, landlord, "landlord", verdict, decision["reason"],
              context={"next_step": f"Recommended new rent ~S${rec:.0f} (your approval needed)."})
        action = "Queued landlord approval for a rent adjustment."

    return _finish(case_id, "renewal", decision, action)


def _handle_end_of_tenancy(event: dict) -> dict:
    tenancy, prop, tenant, landlord = _resolve_parties(event["tenancy_id"])
    decision = end_of_tenancy.assess(event.get("items", []),
                                     tenancy.get("security_deposit_sgd", 0.0))
    verdict = decision["verdict"]

    case_id = open_case("end_of_tenancy", decision["reason"], property_id=prop["id"],
                        tenancy_id=tenancy["id"], opened_by_party_id=tenant["id"])
    m = decision["metrics"]

    if verdict == "NO_CLAIM":
        _send(case_id, tenant, "tenant", verdict, decision["reason"],
              context={"amount_sgd": m["refund_sgd"],
                       "next_step": "Full deposit will be refunded."})
        action = "Full deposit refund proposed."
    else:  # CLAIM
        legal = _surface_or_escalate(case_id, "deposit_claim")
        queue_approval("deposit_claim",
                       {"deductions": m["deductible_items"],
                        "total_deduction_sgd": m["total_deduction_sgd"],
                        "refund_sgd": m["refund_sgd"]}, case_id=case_id)
        items_str = "; ".join(f"{d['item']} S${d['cost_sgd']:.0f}"
                              for d in m["deductible_items"])
        _send(case_id, tenant, "tenant", verdict, decision["reason"],
              context={"next_step": f"Proposed deductions: {items_str}. "
                       f"You have {m['response_window_days']} days to respond or remedy."},
              legal=legal)
        action = "Sent itemised deductions; response window open; claim queued for approval."

    return _finish(case_id, "end_of_tenancy", decision, action)


_HANDLERS = {
    "maintenance": _handle_maintenance,
    "arrears": _handle_arrears,
    "dispute": _handle_dispute,
    "renewal": _handle_renewal,
    "end_of_tenancy": _handle_end_of_tenancy,
}


# -------------------------------------------------------------------------
# Public entry: structured events
# -------------------------------------------------------------------------
def handle_event(event: dict) -> dict:
    """Run one structured situation end-to-end."""
    etype = event.get("type")

    if etype == "legal_question" or is_legal_question(event.get("description", "")):
        ref = refuse()
        print("  [LEGAL] direct legal question -> referral, not answered.")
        return {"type": "legal_question", **ref}

    handler = _HANDLERS.get(etype)
    if not handler:
        raise ValueError(f"unknown event type {etype!r}. "
                         f"Expected one of {sorted(_HANDLERS)} or 'legal_question'.")
    return handler(event)


# -------------------------------------------------------------------------
# Public entry: raw inbound messages (the WhatsApp path)
# -------------------------------------------------------------------------
def _log_inbound(case_id: int, party: dict, text: str, media: dict | None) -> None:
    log_communication(case_id, "in", text, channel="whatsapp",
                      from_party_id=party["id"], audience_role=party["role"], media=media)


def _event_from_intent(it: dict, tenancy: dict, party: dict, text: str,
                       has_media: bool) -> dict:
    intent, hints = it["intent"], it.get("hints", {})
    # The AI intake writes a clean, agent's-POV one-liner per issue; we relay THAT to
    # the landlord/contractor rather than the tenant's raw words. None on the keyword
    # fallback, in which case the handlers use the raw text.
    summary = it.get("summary")
    event = {"tenancy_id": tenancy["id"], "inbound": True, "has_media": has_media}
    if intent == "maintenance":
        event.update(type="maintenance", description=text,
                     trade=hints.get("trade", "general"), fault_summary=summary)
    elif intent == "arrears":
        event.update(type="arrears")
    elif intent == "dispute":
        event.update(type="dispute", description=text,
                     category=hints.get("category", "other"),
                     complainant_party_id=party["id"], anonymity=True,
                     fault_summary=summary, safety_flag=hints.get("safety_flag"))
    elif intent == "renewal":
        event.update(type="renewal")
    return event


def handle_inbound(from_phone: str, text: str, has_media: bool = False) -> dict:
    """Understand and act on one raw inbound message, replying on the same channel.

    Threads onto an existing open case when it's a follow-up, handles more than one
    issue in a single message, logs the inbound for history, and notes any photo."""
    comms.set_default_channel("whatsapp")
    party = find_party_by_phone(from_phone)
    if not party:
        print(f"  [INBOUND] unknown sender {from_phone}; ignoring for safety.")
        return {"status": "ignored_unknown_sender", "from": from_phone}

    media = {"has_media": True} if has_media else None
    print(f"  [INBOUND] {party['name']} ({party['role']}): {text!r}"
          + (" [+photo]" if has_media else ""))
    _INBOUND.update(sender_id=party["id"], message=text)
    try:
        tenancy = tenancy_for_party(party["id"])

        # Legal questions are never answered — referral only.
        if is_legal_question(text):
            case_id = open_case("general", text, opened_by_party_id=party["id"],
                                tenancy_id=tenancy["id"] if tenancy else None)
            _log_inbound(case_id, party, text, media)
            ref = refuse()
            _send(case_id, party, party["role"], "REFERRAL", ref["message"])
            return _finish(case_id, "general",
                           {"verdict": "REFERRAL", "reason": "Legal question received.",
                            "metrics": {}}, "Referred to a professional.")

        parsed = understand_message(text)
        engine_intents = [i for i in parsed["intents"] if i["intent"] in _HANDLERS]
        open_case_row = latest_open_case_for_tenancy(tenancy["id"]) if tenancy else None

        # 1. A reply on an existing matter takes precedence — a chase like "still not
        #    fixed" mentions "fix" but is a follow-up, not a brand-new job.
        if open_case_row and parsed["follow_up"]:
            _log_inbound(open_case_row["id"], party, text, media)
            return handle_followup(open_case_row, party, text, parsed["follow_up"])

        # 2. New actionable issue(s) — a single message can carry several.
        if engine_intents and tenancy:
            results, logged = [], False
            for it in engine_intents:
                res = handle_event(_event_from_intent(it, tenancy, party, text, has_media))
                if not logged and res.get("case_id"):
                    _log_inbound(res["case_id"], party, text, media)
                    logged = True
                results.append(res)
            return results[0] if len(results) == 1 else {"multi": results}

        # 3. A bare reply on an open case (no new issue, no follow-up keyword).
        if open_case_row and not parsed["intents"]:
            _log_inbound(open_case_row["id"], party, text, media)
            return handle_followup(open_case_row, party, text, "status_chase")

        # 4. Move-out notice, or nothing actionable — acknowledge + flag a human.
        move_out = any(i["intent"] == "move_out" for i in parsed["intents"])
        case_id = open_case("general", text, tenancy_id=tenancy["id"] if tenancy else None,
                            opened_by_party_id=party["id"])
        _log_inbound(case_id, party, text, media)
        note = ("Thanks — we've noted you intend to move out and a team member will "
                "follow up with the next steps." if move_out
                else "Thanks for your message — we've received it and a team member will "
                     "follow up shortly.")
        _send(case_id, party, party["role"], "RECEIVED", note)
        return _finish(case_id, "general",
                       {"verdict": "RECEIVED",
                        "reason": "move-out notice" if move_out else "general message",
                        "metrics": {"intents": parsed["intents"]}},
                       "Acknowledged; flagged for human follow-up.")
    finally:
        _INBOUND.clear()


def handle_followup(case: dict, party: dict, text: str, kind: str) -> dict:
    """Continue an existing conversation rather than opening a new case. Records the
    follow-up, replies appropriately, and escalates if the tenant keeps chasing."""
    case_id = case["id"]

    if kind == "acknowledgement":
        decision = {"verdict": "NOTED", "reason": "Tenant acknowledged.", "metrics": {}}
        record_decision(case_id, "followup", "NOTED", decision["reason"], {})
        notify_operator(get_case(case_id), decision, "Logged acknowledgement (no reply).")
        return {"case_id": case_id, "engine": "followup", **decision, "status": case["status"]}

    if kind == "confirmation":
        _send(case_id, party, party["role"], "CONFIRMED",
              "Great, thank you for confirming — that's noted.")
        decision = {"verdict": "CONFIRMED", "reason": "Tenant confirmed.", "metrics": {}}
        record_decision(case_id, "followup", "CONFIRMED", decision["reason"], {})
        notify_operator(get_case(case_id), decision, "Logged confirmation.")
        push_pending_approvals()
        return {"case_id": case_id, "engine": "followup", **decision, "status": case["status"]}

    # status_chase (or a bare reply treated as a check-in).
    # The originating message counts as inbound #1, so chases = inbound - 1.
    chases = max(0, inbound_count_for_case(case_id) - 1)
    open_states = ("awaiting_contractor", "awaiting_party", "awaiting_approval")
    if chases >= 2 and case["status"] in open_states:
        update_case(case_id, status=cases.ESCALATED,
                    escalated_reason=f"Tenant chased {chases} times without resolution.")
        queue_approval("escalate_human",
                       {"reason": f"Repeated chasing on case {case_id} ({chases} chases)."},
                       case_id=case_id)
        _send(case_id, party, party["role"], "ESCALATED",
              f"This has been escalated after {chases} follow-ups without resolution. "
              "A human agent will be handling this personally and will be in touch very shortly.",
              context={"chase_count": chases, "status": "escalated",
                       "eta": case.get("next_action_at")})
        decision = {"verdict": "ESCALATED", "reason": f"Escalated after {chases} chases.",
                    "metrics": {"chases": chases}}
        record_decision(case_id, "followup", "ESCALATED", decision["reason"], decision["metrics"])
        notify_operator(get_case(case_id), decision, "Escalated after repeated chasing.")
        push_pending_approvals()
        return {"case_id": case_id, "engine": "followup", **decision, "status": cases.ESCALATED}

    eta = case.get("next_action_at")
    status_line = case.get("next_action") or "We're on it."
    reason = f"Status update: {status_line}" + (f" ETA: {eta}." if eta else "")
    _send(case_id, party, party["role"], "UPDATE", reason,
          context={"chase_count": chases, "status": case["status"],
                   "eta": eta, "next_step": status_line})
    decision = {"verdict": "UPDATE", "reason": "Sent status update to tenant.",
                "metrics": {"chases": chases}}
    record_decision(case_id, "followup", "UPDATE", decision["reason"], decision["metrics"])
    notify_operator(get_case(case_id), decision, "Sent status update.")
    push_pending_approvals()
    return {"case_id": case_id, "engine": "followup", **decision, "status": case["status"]}


# -------------------------------------------------------------------------
# Proactive sweeps + the live inbound listener
# -------------------------------------------------------------------------
def sweep_arrears(as_of: str | None = None) -> list[dict]:
    results = []
    for t in active_tenancies():
        outcome = _handle_arrears({"tenancy_id": t["id"], "as_of": as_of})
        if outcome["verdict"] != "CURRENT":
            results.append(outcome)
    return results


def sweep_renewals(as_of: str | None = None) -> list[dict]:
    results = []
    for t in active_tenancies():
        outcome = _handle_renewal({"tenancy_id": t["id"], "as_of": as_of})
        if outcome["verdict"] != "NOT_DUE":
            results.append(outcome)
    return results


def sweep_followups(as_of: str | None = None) -> list[dict]:
    """Follow through on stalled work: any repair whose contractor ETA has passed gets
    chased (and the tenant updated); chase it again and it's escalated to a human.
    This is the deterministic stand-in for an agent that 'follows through until resolved'."""
    now = as_of or datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    results = []
    for case in cases_by_status(cases.AWAITING_CONTRACTOR):
        eta = case.get("next_action_at")
        if not eta or eta >= now:
            continue   # not overdue yet
        case_id = case["id"]
        tenancy = get_tenancy(case["tenancy_id"]) if case["tenancy_id"] else None
        prop = get_property(case["property_id"]) if case["property_id"] else None
        tenant = get_party(tenancy["tenant_party_id"]) if tenancy else None

        if decision_count(case_id, "followup_sweep") >= 1:
            # Already chased once and still not done — escalate to a human.
            update_case(case_id, status=cases.ESCALATED,
                        escalated_reason=f"Contractor overdue past ETA {eta}; no completion.")
            queue_approval("escalate_human",
                           {"reason": f"Contractor overdue on case {case_id} (ETA {eta})."},
                           case_id=case_id)
            _send(case_id, tenant, "tenant", "ESCALATED",
                  "Apologies for the delay — the contractor is running over, so I've "
                  "escalated this to get it sorted as a priority.")
            decision = {"verdict": "ESCALATE",
                        "reason": f"Contractor overdue (ETA {eta}); escalated.", "metrics": {}}
            record_decision(case_id, "followup_sweep", "ESCALATE", decision["reason"], {})
            notify_operator(get_case(case_id), decision, "Escalated overdue contractor.")
            push_pending_approvals()
        else:
            # First time overdue — chase the contractor and give the tenant a new ETA.
            job = contractors.dispatch(find_contractor("general"),
                                       fault=case.get("summary") or "repair",
                                       address=prop["address"] if prop else "",
                                       urgency=case.get("urgency") or "URGENT")
            update_case(case_id, next_action_at=job["eta"])
            _send(case_id, tenant, "tenant", "UPDATE",
                  f"Quick update — I'm chasing the contractor on this. Revised ETA is "
                  f"{job['eta']}. Sorry for the wait and thanks for your patience.")
            decision = {"verdict": "CHASE",
                        "reason": f"Contractor chased; new ETA {job['eta']}.", "metrics": {}}
            record_decision(case_id, "followup_sweep", "CHASE", decision["reason"], {})
            notify_operator(get_case(case_id), decision, "Chased overdue contractor.")
            push_pending_approvals()
        results.append({"case_id": case_id, **decision})
    return results


def listen(poll_seconds: int = 8) -> None:
    """Live loop: poll WhatsApp for new messages and handle each one. Blocks.
    Uses the mock client unless WHATSAPP_MODE=live (then it drives a real browser)."""
    import time
    from integrations.whatsapp import get_client
    client = get_client()
    print(f"Listening for WhatsApp messages (poll every {poll_seconds}s). Ctrl+C to stop.")
    while True:
        try:
            for msg in client.fetch_unread():
                try:
                    handle_inbound(msg["from_phone"], msg["text"],
                                   has_media=msg.get("has_media", False))
                except Exception as exc:
                    print(f"  [INBOUND] error handling message: {exc}")
            time.sleep(poll_seconds)
        except KeyboardInterrupt:
            print("\nStopped.")
            return


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(handle_event(json.loads(sys.argv[1])), indent=2, default=str))
    else:
        print("Pass an event JSON string, or use main.py.")
