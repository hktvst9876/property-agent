"""
jurisdictions/base.py — jurisdiction-neutral types.

A Jurisdiction is a pack of FACTS, each carrying its sources. The engines and
the legal guard read from this; they never hard-code law. Drop in a second pack
(e.g. AU/NZ) and select it via config.JURISDICTION — no engine changes needed.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    citation: str          # human-readable, e.g. "State Courts — Small Claims Tribunals"
    url: str               # where to verify it


@dataclass(frozen=True)
class LegalFact:
    text: str              # a plain factual statement (never advice)
    sources: tuple[Source, ...]   # must be non-empty — legal_guard enforces this


@dataclass(frozen=True)
class Jurisdiction:
    code: str              # "SG"
    name: str              # "Singapore"
    # Whether formal notices follow a statutory prescribed form (AU/NZ) or are
    # purely contractual (SG). Drives how core/legal_guard validates a notice.
    notice_is_statutory: bool
    # Name of the government bond/deposit-lodgement authority, or None when the
    # deposit is held privately by the landlord (SG).
    bond_authority: str | None
    # Topic -> facts. Topics used by the engines:
    #   deposit | disputes | notices | arrears_recovery | onboarding | agency
    facts: dict[str, tuple[LegalFact, ...]] = field(default_factory=dict)

    def facts_for(self, topic: str) -> tuple[LegalFact, ...]:
        return self.facts.get(topic, ())


def get_jurisdiction(code: str) -> Jurisdiction:
    """Resolve a jurisdiction code to its data pack."""
    code = (code or "").upper()
    if code == "SG":
        from jurisdictions.singapore import SINGAPORE
        return SINGAPORE
    raise ValueError(
        f"No jurisdiction data pack for {code!r}. "
        f"Add one under jurisdictions/ before issuing any notice."
    )
