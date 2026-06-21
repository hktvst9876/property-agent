from core import triage


def test_gas_leak_is_emergency():
    assert triage.classify("I smell gas in the kitchen")["verdict"] == "EMERGENCY"


def test_no_water_is_emergency():
    assert triage.classify("There is no water at all in the unit")["verdict"] == "EMERGENCY"


def test_broken_lock_is_urgent():
    assert triage.classify("The front door lock is broken")["verdict"] == "URGENT"


def test_dripping_tap_is_routine():
    assert triage.classify("The kitchen tap drips a little")["verdict"] == "ROUTINE"


def test_reported_unsafe_overrides_to_emergency():
    out = triage.classify("Something feels off", reported_unsafe=True)
    assert out["verdict"] == "EMERGENCY"


def test_sla_attached():
    assert triage.classify("gas leak")["metrics"]["sla"] == "same hour"
