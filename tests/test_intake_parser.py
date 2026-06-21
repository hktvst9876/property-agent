from core import intake_parser
from db.store import normalize_phone


def _intents(text):
    return [i["intent"] for i in intake_parser.detect_intents(text)]


def test_maintenance_detected_with_trade():
    out = intake_parser.detect_intents("the aircon is leaking again")
    assert out[0]["intent"] == "maintenance"
    assert out[0]["hints"]["trade"] in ("plumber", "aircon")


def test_singlish_maintenance():
    assert "maintenance" in _intents("aircon spoil liao, so hot")
    assert "maintenance" in _intents("toilet choke cannot use")
    assert "maintenance" in _intents("the lights all blackout")


def test_gas_is_maintenance_not_complaint():
    assert _intents("I can smell gas in the kitchen") == ["maintenance"]


def test_rent_detected():
    assert "arrears" in _intents("sorry I haven't paid the rent yet")


def test_multiple_intents_in_one_message():
    intents = _intents("rent late sorry and the toilet is choked")
    assert "arrears" in intents and "maintenance" in intents


def test_noise_complaint_detected():
    out = intake_parser.detect_intents("my neighbour blasts loud music till 3am")
    assert out[0]["intent"] == "dispute"
    assert out[0]["hints"]["category"] == "noise"


def test_renewal_vs_move_out():
    assert _intents("can we renew the lease for another year?") == ["renewal"]
    assert _intents("we're moving out, not renewing") == ["move_out"]


def test_locksmith_trade():
    out = intake_parser.detect_intents("the front door lock is broken")
    assert out[0]["hints"]["trade"] == "locksmith"


def test_followup_classification():
    assert intake_parser.classify_followup("any update? still waiting") == "status_chase"
    assert intake_parser.classify_followup("ok thanks!") == "acknowledgement"
    assert intake_parser.classify_followup("yes that works for me") == "confirmation"
    assert intake_parser.classify_followup("the tap is leaking") is None


def test_sentiment_reads_mood():
    assert intake_parser.sentiment("this is the third time!! unacceptable") == "angry"
    assert intake_parser.sentiment("please help, there's no water and I'm scared") == "distressed"
    assert intake_parser.sentiment("hi, the tap drips a little") == "calm"


def test_phone_normalization_matches_formats():
    a = normalize_phone("+65 9222 0000")
    b = normalize_phone("6592220000")
    c = normalize_phone("92220000")
    assert a == b == c == "92220000"
