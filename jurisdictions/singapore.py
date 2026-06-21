"""
jurisdictions/singapore.py — Singapore residential tenancy reference pack.

FACTS ONLY, each with a source. Nothing here is legal advice, and the agent must
never present it as such. Singapore has no residential bond authority and no
RTA-style tenancy tribunal: deposits are held privately by the landlord, notices
are contractual (per the lease), and disputes go to the Small Claims Tribunals or
the civil courts.

These statements are general and may go out of date — every outward use is
wrapped by core/legal_guard with a "verify with a qualified professional"
disclaimer and the cited source attached.
"""

from __future__ import annotations
from jurisdictions.base import Jurisdiction, LegalFact, Source

# -- Sources ---------------------------------------------------------------
SCT = Source(
    "State Courts of Singapore — Small Claims Tribunals",
    "https://www.judiciary.gov.sg/civil/small-claims-tribunals",
)
DISTRESS_ACT = Source(
    "Distress Act 1934 (Singapore Statutes Online)",
    "https://sso.agc.gov.sg/Act/DA1934",
)
IRAS = Source(
    "IRAS — Stamp Duty on leases / tenancy agreements",
    "https://www.iras.gov.sg/taxes/stamp-duty/for-property/buying-or-renting-property/renting-a-property",
)
ICA = Source(
    "ICA — Immigration & Checkpoints Authority (pass validity)",
    "https://www.ica.gov.sg/",
)
HDB = Source(
    "HDB — Renting out your flat / bedrooms",
    "https://www.hdb.gov.sg/residential/renting-a-flat/renting-from-the-open-market",
)
URA = Source(
    "URA — Renting out private residential property (minimum 3-month stay)",
    "https://www.ura.gov.sg/Corporate/Property/Residential/Renting-Property",
)
CEA = Source(
    "Council for Estate Agencies (CEA)",
    "https://www.cea.gov.sg/",
)


# -- Facts by topic --------------------------------------------------------
_FACTS = {
    "deposit": (
        LegalFact(
            "A security deposit in Singapore is held by the landlord under the "
            "tenancy agreement; there is no government bond-lodgement scheme. "
            "Deductions should be itemised and supported.",
            (IRAS,),
        ),
        LegalFact(
            "A dispute over the return of a deposit can be filed with the Small "
            "Claims Tribunals where the lease does not exceed 2 years and the "
            "claim is within the monetary limit.",
            (SCT,),
        ),
    ),
    "disputes": (
        LegalFact(
            "The Small Claims Tribunals hear disputes arising from residential "
            "tenancy agreements where the lease does not exceed 2 years, for "
            "claims up to S$20,000 (or up to S$30,000 if both parties consent).",
            (SCT,),
        ),
        LegalFact(
            "Disputes outside the Small Claims Tribunals' limits are dealt with "
            "by the Magistrates' or District Courts.",
            (SCT,),
        ),
    ),
    "notices": (
        LegalFact(
            "In Singapore a notice to remedy a breach or to end a tenancy is "
            "governed by the tenancy agreement's own clauses; there is no "
            "statutory prescribed notice form for private residential tenancies.",
            (SCT,),
        ),
        LegalFact(
            "A landlord cannot lawfully evict a tenant by self-help (e.g. changing "
            "locks or removing belongings); possession is recovered through the "
            "process set out in the tenancy agreement and, if needed, the courts.",
            (SCT,),
        ),
    ),
    "arrears_recovery": (
        LegalFact(
            "Where rent is in arrears, the Distress Act provides a court process "
            "by which a landlord may apply to recover rent due.",
            (DISTRESS_ACT,),
        ),
        LegalFact(
            "A claim for unpaid rent within the monetary limit and for a lease not "
            "exceeding 2 years may be brought before the Small Claims Tribunals.",
            (SCT,),
        ),
    ),
    "onboarding": (
        LegalFact(
            "A tenancy agreement is subject to stamp duty payable to IRAS; the "
            "tenant customarily pays unless the agreement states otherwise.",
            (IRAS,),
        ),
        LegalFact(
            "A landlord must verify that a prospective foreign tenant holds a valid "
            "immigration pass; renting to an immigration offender is an offence.",
            (ICA,),
        ),
        LegalFact(
            "Subletting an HDB flat or its bedrooms requires meeting HDB's rules, "
            "including registration, the minimum occupation period and occupancy "
            "caps.",
            (HDB,),
        ),
        LegalFact(
            "Private residential properties may not be let for stays shorter than "
            "the URA minimum of 3 consecutive months.",
            (URA,),
        ),
    ),
    "agency": (
        LegalFact(
            "Estate agencies and their agents in Singapore must be licensed and "
            "registered with the Council for Estate Agencies (CEA).",
            (CEA,),
        ),
    ),
}


SINGAPORE = Jurisdiction(
    code="SG",
    name="Singapore",
    notice_is_statutory=False,
    bond_authority=None,
    facts=_FACTS,
)
