from core import end_of_tenancy


def test_fair_wear_only_is_no_claim():
    items = [
        {"item": "Living room wall", "ingoing": "clean", "outgoing": "minor scuffs",
         "cost_sgd": 0, "fair_wear_and_tear": True},
    ]
    out = end_of_tenancy.assess(items, 6000)
    assert out["verdict"] == "NO_CLAIM"
    assert out["metrics"]["refund_sgd"] == 6000


def test_damage_is_itemised_claim():
    items = [
        {"item": "Living room wall", "ingoing": "clean", "outgoing": "minor scuffs",
         "cost_sgd": 0, "fair_wear_and_tear": True},
        {"item": "Kitchen countertop", "ingoing": "intact", "outgoing": "burn mark",
         "cost_sgd": 450, "fair_wear_and_tear": False},
    ]
    out = end_of_tenancy.assess(items, 6000)
    assert out["verdict"] == "CLAIM"
    assert out["metrics"]["total_deduction_sgd"] == 450
    assert out["metrics"]["refund_sgd"] == 5550
    assert len(out["metrics"]["deductible_items"]) == 1


def test_deduction_capped_at_deposit():
    items = [
        {"item": "Flooring", "ingoing": "intact", "outgoing": "destroyed",
         "cost_sgd": 9000, "fair_wear_and_tear": False},
    ]
    out = end_of_tenancy.assess(items, 6000)
    assert out["metrics"]["total_deduction_sgd"] == 6000
    assert out["metrics"]["refund_sgd"] == 0
    assert out["metrics"]["uncapped_deduction_sgd"] == 9000


def test_unchanged_items_not_charged():
    items = [
        {"item": "Bedroom door", "ingoing": "intact", "outgoing": "intact",
         "cost_sgd": 500, "fair_wear_and_tear": False},
    ]
    out = end_of_tenancy.assess(items, 6000)
    assert out["verdict"] == "NO_CLAIM"
