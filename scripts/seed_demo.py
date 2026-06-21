"""
scripts/seed_demo.py — a demo dataset for end-to-end runs.

Creates a landlord, a tenant, a plumber, an HDB property, an active tenancy, and a
rent ledger with the current month overdue. Prints the IDs and ready-to-paste
intake commands. Re-running starts from a clean database.
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.store import (
    DB_PATH, init_db, add_party, add_property, add_tenancy, add_ledger_entry,
)


def seed() -> dict:
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()

    landlord = add_party("landlord", "Mr Tan Wei Ming", email="tan@example.com",
                         phone="+6591110000")
    tenant = add_party("tenant", "Aisha Rahman", email="aisha@example.com",
                       phone="+6592220000")
    add_party("contractor", "RapidFix Plumbing", email="jobs@rapidfix.example",
              phone="+6593330000", trade="plumber")

    prop = add_property("Blk 123 Tampines St 11 #08-456, Singapore 521123",
                        landlord_party_id=landlord, type="hdb",
                        repair_threshold_sgd=300.0)

    tenancy = add_tenancy(
        property_id=prop, tenant_party_id=tenant, rent_sgd=3000.0,
        start_date="2025-09-01", end_date="2026-08-31",
        security_deposit_sgd=6000.0, lease_notice_days=30,
        minor_repair_cap_sgd=150.0,
        ingoing_report={"Kitchen countertop": "intact", "Living room wall": "clean",
                        "Bedroom door": "intact"},
    )

    # Ledger: prior months paid on time, current month overdue.
    add_ledger_entry(tenancy, "2026-04-01", 3000.0, paid_date="2026-04-01",
                     paid_amount_sgd=3000.0, status="paid")
    add_ledger_entry(tenancy, "2026-05-01", 3000.0, paid_date="2026-05-02",
                     paid_amount_sgd=3000.0, status="paid")
    add_ledger_entry(tenancy, "2026-06-01", 3000.0, status="overdue")

    print(f"Seeded demo data at {DB_PATH}")
    print(f"  landlord_party_id = {landlord}")
    print(f"  tenant_party_id   = {tenant}")
    print(f"  property_id       = {prop}")
    print(f"  tenancy_id        = {tenancy}")
    print()
    print("Try these:")
    print(f'  python main.py intake \'{{"type":"maintenance","tenancy_id":{tenancy},'
          f'"description":"I smell gas in the kitchen","estimated_cost_sgd":250,"trade":"plumber"}}\'')
    print(f'  python main.py intake \'{{"type":"maintenance","tenancy_id":{tenancy},'
          f'"description":"Leaking tap","estimated_cost_sgd":1200}}\'')
    print(f"  python main.py sweep arrears")
    print(f"  python main.py sweep renewals")
    return {"landlord": landlord, "tenant": tenant, "property": prop, "tenancy": tenancy}


if __name__ == "__main__":
    seed()
