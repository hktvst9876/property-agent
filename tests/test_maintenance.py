from core import maintenance


def test_under_cap_is_tenant_responsibility():
    out = maintenance.gate(80, "ROUTINE", minor_repair_cap_sgd=150,
                           landlord_threshold_sgd=300)
    assert out["verdict"] == "TENANT_RESPONSIBILITY"


def test_within_threshold_dispatches():
    out = maintenance.gate(250, "ROUTINE", minor_repair_cap_sgd=150,
                           landlord_threshold_sgd=300)
    assert out["verdict"] == "DISPATCH"


def test_over_threshold_needs_approval():
    out = maintenance.gate(1200, "URGENT", minor_repair_cap_sgd=150,
                           landlord_threshold_sgd=300)
    assert out["verdict"] == "APPROVE"


def test_emergency_dispatches_even_over_threshold():
    out = maintenance.gate(2000, "EMERGENCY", minor_repair_cap_sgd=150,
                           landlord_threshold_sgd=300)
    assert out["verdict"] == "EMERGENCY_DISPATCH"


def test_recurring_fault_escalates_to_approval():
    out = maintenance.gate(250, "ROUTINE", minor_repair_cap_sgd=150,
                           landlord_threshold_sgd=300, recurrence_count=2)
    assert out["verdict"] == "APPROVE"
    assert "recurring" in out["reason"].lower()
