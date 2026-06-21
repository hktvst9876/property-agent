from core import arrears


def test_current_when_paid():
    led = [{"due_date": "2026-06-01", "amount_sgd": 3000, "paid_amount_sgd": 3000,
            "paid_date": "2026-06-01"}]
    assert arrears.assess(led, as_of="2026-06-20")["verdict"] == "CURRENT"


def test_clean_history_day_one_is_reminder():
    led = [{"due_date": "2026-06-01", "amount_sgd": 3000, "paid_amount_sgd": 0}]
    out = arrears.assess(led, as_of="2026-06-02")
    assert out["verdict"] == "REMINDER"


def test_fourteen_days_is_legal_risk():
    led = [{"due_date": "2026-06-01", "amount_sgd": 3000, "paid_amount_sgd": 0}]
    out = arrears.assess(led, as_of="2026-06-19")
    assert out["verdict"] == "LEGAL_RISK"


def test_seven_days_is_breach():
    led = [{"due_date": "2026-06-01", "amount_sgd": 3000, "paid_amount_sgd": 0}]
    out = arrears.assess(led, as_of="2026-06-09")
    assert out["verdict"] == "BREACH"


def test_repeat_offender_day_one_skips_reminder():
    led = [
        {"due_date": "2026-04-01", "amount_sgd": 3000, "paid_amount_sgd": 3000,
         "paid_date": "2026-04-10"},   # paid late
        {"due_date": "2026-05-01", "amount_sgd": 3000, "paid_amount_sgd": 3000,
         "paid_date": "2026-05-09"},   # paid late
        {"due_date": "2026-06-01", "amount_sgd": 3000, "paid_amount_sgd": 0},
    ]
    out = arrears.assess(led, as_of="2026-06-02")
    assert out["verdict"] == "CONTACT"
    assert out["metrics"]["repeat_offender"] is True
