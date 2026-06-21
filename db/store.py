"""
db/store.py — SQLite helpers. Thin wrappers; raw SQL kept readable.
Mirrors the conventions in store-tester/db/store.py.
"""

from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "property_agent.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = connect()
    with conn:
        conn.executescript(SCHEMA_PATH.read_text())
    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


# -------------------------------------------------------------------------
# Parties / properties / tenancies
# -------------------------------------------------------------------------
def add_party(role: str, name: str, email: str | None = None,
              phone: str | None = None, trade: str | None = None,
              notes: str | None = None) -> int:
    conn = connect()
    with conn:
        cur = conn.execute(
            "INSERT INTO parties (role, name, email, phone, trade, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (role, name, email, phone, trade, notes),
        )
    conn.close()
    return cur.lastrowid


def add_property(address: str, landlord_party_id: int, type: str = "condo",
                 repair_threshold_sgd: float | None = None,
                 jurisdiction: str = "SG", notes: str | None = None) -> int:
    conn = connect()
    with conn:
        cur = conn.execute(
            "INSERT INTO properties "
            "(address, type, landlord_party_id, repair_threshold_sgd, jurisdiction, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (address, type, landlord_party_id, repair_threshold_sgd, jurisdiction, notes),
        )
    conn.close()
    return cur.lastrowid


def add_tenancy(property_id: int, tenant_party_id: int, rent_sgd: float,
                start_date: str, end_date: str, security_deposit_sgd: float = 0.0,
                lease_notice_days: int = 30, minor_repair_cap_sgd: float | None = None,
                ingoing_report: dict | None = None) -> int:
    conn = connect()
    with conn:
        cur = conn.execute(
            """INSERT INTO tenancies
               (property_id, tenant_party_id, rent_sgd, start_date, end_date,
                security_deposit_sgd, lease_notice_days, minor_repair_cap_sgd,
                ingoing_report_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (property_id, tenant_party_id, rent_sgd, start_date, end_date,
             security_deposit_sgd, lease_notice_days, minor_repair_cap_sgd,
             json.dumps(ingoing_report) if ingoing_report else None),
        )
    conn.close()
    return cur.lastrowid


def add_ledger_entry(tenancy_id: int, due_date: str, amount_sgd: float,
                     paid_date: str | None = None, paid_amount_sgd: float = 0.0,
                     status: str = "due") -> int:
    conn = connect()
    with conn:
        cur = conn.execute(
            """INSERT OR REPLACE INTO rent_ledger
               (tenancy_id, due_date, amount_sgd, paid_date, paid_amount_sgd, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tenancy_id, due_date, amount_sgd, paid_date, paid_amount_sgd, status),
        )
    conn.close()
    return cur.lastrowid


# -------------------------------------------------------------------------
# Cases / communications / decisions / approvals / complaints
# -------------------------------------------------------------------------
def open_case(type: str, summary: str, property_id: int | None = None,
              tenancy_id: int | None = None, opened_by_party_id: int | None = None,
              urgency: str | None = None) -> int:
    conn = connect()
    with conn:
        cur = conn.execute(
            """INSERT INTO cases
               (type, property_id, tenancy_id, opened_by_party_id, urgency, summary)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (type, property_id, tenancy_id, opened_by_party_id, urgency, summary),
        )
    conn.close()
    return cur.lastrowid


def update_case(case_id: int, *, status: str | None = None, urgency: str | None = None,
                next_action: str | None = None, next_action_at: str | None = None,
                escalated_reason: str | None = None) -> None:
    fields, vals = [], []
    if status is not None:
        fields.append("status=?"); vals.append(status)
    if urgency is not None:
        fields.append("urgency=?"); vals.append(urgency)
    if next_action is not None:
        fields.append("next_action=?"); vals.append(next_action)
    if next_action_at is not None:
        fields.append("next_action_at=?"); vals.append(next_action_at)
    if escalated_reason is not None:
        fields.append("escalated_reason=?"); vals.append(escalated_reason)
    fields.append("updated_at=?"); vals.append(_now())
    vals.append(case_id)
    conn = connect()
    with conn:
        conn.execute(f"UPDATE cases SET {', '.join(fields)} WHERE id=?", vals)
    conn.close()


def log_communication(case_id: int, direction: str, body: str, *,
                      channel: str = "email", from_party_id: int | None = None,
                      to_party_id: int | None = None, audience_role: str | None = None,
                      subject: str | None = None, media: dict | None = None) -> int:
    conn = connect()
    with conn:
        cur = conn.execute(
            """INSERT INTO communications
               (case_id, direction, channel, from_party_id, to_party_id,
                audience_role, subject, body, media_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (case_id, direction, channel, from_party_id, to_party_id,
             audience_role, subject, body, json.dumps(media) if media else None),
        )
    conn.close()
    return cur.lastrowid


def record_decision(case_id: int, engine: str, verdict: str, reason: str,
                    metrics: dict | None = None) -> int:
    conn = connect()
    with conn:
        cur = conn.execute(
            """INSERT INTO decisions (case_id, engine, verdict, reason, metrics_json)
               VALUES (?, ?, ?, ?, ?)""",
            (case_id, engine, verdict, reason, json.dumps(metrics or {}, default=str)),
        )
    conn.close()
    return cur.lastrowid


def queue_approval(action: str, payload: dict, case_id: int | None = None) -> int:
    conn = connect()
    with conn:
        cur = conn.execute(
            "INSERT INTO approvals (case_id, action, payload_json) VALUES (?, ?, ?)",
            (case_id, action, json.dumps(payload, default=str)),
        )
    conn.close()
    return cur.lastrowid


def pending_approvals() -> list[sqlite3.Row]:
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM approvals WHERE status='pending' ORDER BY created_at"
    ).fetchall()
    conn.close()
    return rows


def resolve_approval(approval_id: int, status: str, resolved_by: str) -> None:
    if status not in ("approved", "rejected"):
        raise ValueError(f"invalid status {status!r}")
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE approvals SET status=?, resolved_at=?, resolved_by=? WHERE id=?",
            (status, _now(), resolved_by, approval_id),
        )
    conn.close()


def record_complaint(case_id: int, complainant_party_id: int, category: str,
                     details: str, subject_party_id: int | None = None,
                     evidence: dict | None = None, anonymity: bool = True) -> int:
    conn = connect()
    with conn:
        cur = conn.execute(
            """INSERT INTO complaints
               (case_id, complainant_party_id, subject_party_id, category,
                details, evidence_json, anonymity)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (case_id, complainant_party_id, subject_party_id, category, details,
             json.dumps(evidence) if evidence else None, 1 if anonymity else 0),
        )
    conn.close()
    return cur.lastrowid


# -------------------------------------------------------------------------
# Getters
# -------------------------------------------------------------------------
def get_party(party_id: int) -> dict | None:
    return _get_one("SELECT * FROM parties WHERE id=?", (party_id,))


def get_property(property_id: int) -> dict | None:
    return _get_one("SELECT * FROM properties WHERE id=?", (property_id,))


def get_tenancy(tenancy_id: int) -> dict | None:
    return _get_one("SELECT * FROM tenancies WHERE id=?", (tenancy_id,))


def get_case(case_id: int) -> dict | None:
    return _get_one("SELECT * FROM cases WHERE id=?", (case_id,))


def active_tenancies() -> list[dict]:
    conn = connect()
    rows = conn.execute("SELECT * FROM tenancies WHERE status='active'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def latest_open_case_for_tenancy(tenancy_id: int) -> dict | None:
    """Most recent case on this tenancy that isn't resolved — for threading a reply
    onto an ongoing conversation instead of opening a new case each time."""
    conn = connect()
    row = conn.execute(
        "SELECT * FROM cases WHERE tenancy_id=? AND status != 'resolved' "
        "ORDER BY updated_at DESC, id DESC LIMIT 1",
        (tenancy_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def inbound_count_for_case(case_id: int) -> int:
    """How many inbound messages this case has received (to detect repeat chasing)."""
    conn = connect()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM communications WHERE case_id=? AND direction='in'",
        (case_id,),
    ).fetchone()
    conn.close()
    return row["n"]


def cases_by_status(status: str) -> list[dict]:
    conn = connect()
    rows = conn.execute("SELECT * FROM cases WHERE status=?", (status,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def decision_count(case_id: int, engine: str) -> int:
    conn = connect()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM decisions WHERE case_id=? AND engine=?",
        (case_id, engine),
    ).fetchone()
    conn.close()
    return row["n"]


def ledger_for_tenancy(tenancy_id: int) -> list[dict]:
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM rent_ledger WHERE tenancy_id=? ORDER BY due_date",
        (tenancy_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def normalize_phone(phone: str) -> str:
    """Reduce a phone string to comparable digits. SG numbers are matched on their
    last 8 digits so '+65 9222 0000', '6592220000', and '92220000' all match."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    return digits[-8:] if len(digits) >= 8 else digits


def find_party_by_phone(phone: str) -> dict | None:
    """Resolve an inbound sender's phone to a known party (any role)."""
    target = normalize_phone(phone)
    if not target:
        return None
    conn = connect()
    rows = conn.execute("SELECT * FROM parties WHERE phone IS NOT NULL").fetchall()
    conn.close()
    for r in rows:
        if normalize_phone(r["phone"]) == target:
            return dict(r)
    return None


def tenancy_for_party(party_id: int) -> dict | None:
    """Active tenancy where this party is the tenant (the common inbound case)."""
    conn = connect()
    row = conn.execute(
        "SELECT * FROM tenancies WHERE tenant_party_id=? AND status='active' "
        "ORDER BY id DESC LIMIT 1",
        (party_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def find_contractor(trade: str) -> dict | None:
    """First contractor party matching a trade (or any contractor as fallback)."""
    conn = connect()
    row = conn.execute(
        "SELECT * FROM parties WHERE role='contractor' AND trade=? LIMIT 1", (trade,)
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM parties WHERE role='contractor' LIMIT 1"
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def prior_fault_reports(tenancy_id: int, keyword: str) -> int:
    """How many maintenance decisions for this tenancy mention the fault keyword.
    Used to flag recurring faults."""
    conn = connect()
    rows = conn.execute(
        """SELECT d.reason FROM decisions d
           JOIN cases c ON c.id = d.case_id
           WHERE c.tenancy_id=? AND d.engine='maintenance'""",
        (tenancy_id,),
    ).fetchall()
    conn.close()
    kw = keyword.lower()
    return sum(1 for r in rows if kw in (r["reason"] or "").lower())


def _get_one(sql: str, params: tuple) -> dict | None:
    conn = connect()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return dict(row) if row else None


if __name__ == "__main__":
    init_db()
    print(f"Initialised DB at {DB_PATH}")
