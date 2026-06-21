"""
End-to-end tests for the conversational behaviour: threading replies onto an open
case, escalating repeated chasing, multiple issues in one message, media, and the
proactive contractor-chasing sweep. These use the real SQLite DB; each test re-seeds
for a clean slate. No model/network needed.
"""

import os

os.environ["COMMS_DRY_RUN"] = "1"          # never attempt a real send during tests

from scripts.seed_demo import seed
from orchestrator import handle_inbound, sweep_followups
from db.store import get_case, connect

TENANT = "+6592220000"


def _fresh():
    seed()


def test_followup_threads_onto_same_case():
    _fresh()
    first = handle_inbound(TENANT, "aircon spoil liao, so hot")
    cid = first["case_id"]
    reply = handle_inbound(TENANT, "any update? still waiting")
    assert reply["case_id"] == cid            # same case, not a new one
    assert reply["engine"] == "followup"
    assert reply["verdict"] == "UPDATE"


def test_repeated_chasing_escalates():
    _fresh()
    first = handle_inbound(TENANT, "aircon spoil, so hot")
    cid = first["case_id"]
    handle_inbound(TENANT, "any update?")             # chase 1 -> UPDATE
    third = handle_inbound(TENANT, "still not fixed!!")  # chase 2 -> ESCALATE
    assert third["case_id"] == cid
    assert third["verdict"] == "ESCALATED"
    assert get_case(cid)["status"] == "escalated"


def test_multiple_issues_in_one_message():
    _fresh()
    res = handle_inbound(TENANT, "rent late sorry and the toilet is choked")
    assert "multi" in res
    engines = sorted(r["engine"] for r in res["multi"])
    assert engines == ["arrears", "maintenance"]


def test_inbound_is_logged_with_media():
    _fresh()
    res = handle_inbound(TENANT, "here is a photo of the leak", has_media=True)
    cid = res["case_id"]
    conn = connect()
    row = conn.execute(
        "SELECT media_json FROM communications WHERE case_id=? AND direction='in'", (cid,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert "has_media" in (row["media_json"] or "")


def test_sweep_followups_chases_then_escalates():
    _fresh()
    first = handle_inbound(TENANT, "aircon spoil, so hot")   # ASSESS -> awaiting_contractor + ETA
    cid = first["case_id"]
    future = "2099-01-01T00:00"
    s1 = sweep_followups(as_of=future)
    assert any(x["case_id"] == cid and x["verdict"] == "CHASE" for x in s1)
    s2 = sweep_followups(as_of=future)
    assert any(x["case_id"] == cid and x["verdict"] == "ESCALATE" for x in s2)
    assert get_case(cid)["status"] == "escalated"
