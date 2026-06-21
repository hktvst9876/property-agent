import pytest

from core import legal_guard
from jurisdictions.base import Jurisdiction


def test_direct_legal_question_detected():
    assert legal_guard.is_legal_question("Can I legally evict my tenant?")
    assert legal_guard.is_legal_question("What are my rights as a tenant?")
    assert not legal_guard.is_legal_question("The kitchen tap is leaking")


def test_refuse_never_answers():
    out = legal_guard.refuse()
    assert out["refused"] is True
    assert out["refer_to_professional"] is True
    assert "legal advice" in out["message"].lower()


def test_surface_at_risk_stage_has_disclaimer_and_sources():
    out = legal_guard.surface("arrears_legal_risk", "SG")
    assert out["facts"]                       # non-empty facts
    assert out["sources"]                     # non-empty sources
    assert all(s["citation"] and s["url"] for s in out["sources"])
    assert "verif" in out["disclaimer"].lower()        # "verify"/"verified"
    assert "not legal advice" in out["disclaimer"].lower()
    assert out["refer_to_professional"] is True


def test_surface_rejects_non_risk_stage():
    with pytest.raises(ValueError):
        legal_guard.surface("just_curious", "SG")


def test_surface_escalates_when_no_source(monkeypatch):
    # A jurisdiction with no facts must force an escalation, never an unsourced claim.
    empty = Jurisdiction(code="XX", name="Nowhere", notice_is_statutory=False,
                         bond_authority=None, facts={})
    monkeypatch.setattr(legal_guard, "get_jurisdiction", lambda code: empty)
    with pytest.raises(legal_guard.LegalGuardEscalation):
        legal_guard.surface("arrears_legal_risk", "XX")
