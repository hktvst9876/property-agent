"""
config.py — agency policy expressed as numbers and switches.

Thresholds here are the *decision boundaries* the deterministic engines in core/
use. Editing a number here changes agent behaviour without touching logic — the
same discipline as store-tester/config.py.

Region: Singapore. Currency: SGD.
"""

from __future__ import annotations
import os
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Jurisdiction. Selects the active legal/data pack in jurisdictions/.
# --------------------------------------------------------------------------
JURISDICTION = "SG"

# --------------------------------------------------------------------------
# Safety. DRY-RUN means party-facing comms are logged, never actually sent.
# Read at call time so tests/CLI can override via env without reimporting.
# --------------------------------------------------------------------------
def comms_dry_run() -> bool:
    return os.environ.get("COMMS_DRY_RUN", "1") != "0"


# --------------------------------------------------------------------------
# Maintenance / repair authority.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MaintenanceThresholds:
    # Below this, the repair is the tenant's responsibility per a typical
    # SG "minor repair" lease clause (a per-item cap). Default fallback when a
    # tenancy doesn't specify its own minor_repair_cap_sgd.
    default_minor_repair_cap_sgd: float = 150.0
    # Below the landlord's per-property repair_threshold_sgd the agent may
    # dispatch a contractor directly (and notify). Above it, landlord must
    # approve first — unless it's an emergency. Default fallback per property.
    default_landlord_threshold_sgd: float = 300.0
    # A fault re-reported within this window counts as "recurring" and is
    # flagged for root-cause attention rather than another patch job.
    recurrence_window_days: int = 90


# --------------------------------------------------------------------------
# Rent arrears escalation. Days overdue -> stage.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ArrearsThresholds:
    reminder_max_days: int = 2      # day 1-2: gentle reminder (likely a bank delay)
    contact_max_days: int = 5       # day 3-5: direct contact to understand the situation
    breach_min_days: int = 7        # day 7+: formal contractual breach / notice to remedy
    legal_risk_min_days: int = 14   # beyond: advise landlord on recovery options (gated)
    # A tenant with this many prior overdue cycles is "repeat" — skips the
    # gentle-reminder tone even on a fresh first day late.
    repeat_offender_cycles: int = 2


# --------------------------------------------------------------------------
# Lease renewals.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class RenewalThresholds:
    lead_days: int = 90             # begin renewal process this far before expiry
    # If market comparable differs from current rent by more than this band,
    # recommend an adjustment rather than a flat renewal.
    rent_adjust_band_pct: float = 0.05


# --------------------------------------------------------------------------
# End of tenancy.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class EndOfTenancyThresholds:
    # Tenant gets this many days to respond/remedy before any deposit claim.
    tenant_response_window_days: int = 7


MAINTENANCE = MaintenanceThresholds()
ARREARS = ArrearsThresholds()
RENEWAL = RenewalThresholds()
END_OF_TENANCY = EndOfTenancyThresholds()

# --------------------------------------------------------------------------
# Models + brain switchboard (identical contract to store-tester).
# DECISION-class tasks are LOCKED to Claude; the router refuses anything else.
# Here, the only LLM task is DRAFTING party-facing messages, which is treated
# as decision-class because tone/accuracy is part of the agency's duty of care.
# --------------------------------------------------------------------------
CLAUDE_REASONING_MODEL = "claude-sonnet-4-6"
CLAUDE_CHEAP_MODEL = "claude-haiku-4-5-20251001"

# By default the agent writes messages with built-in, mood-aware templates — no
# model, no API. The mapping below only matters if you opt into an LLM by setting a
# provider's API key (e.g. ANTHROPIC_API_KEY); until then the drafter uses templates.
# Decisions are always made by the deterministic engines, never a model.
PROVIDER_MAP = {
    "decision":   "anthropic",   # reserved (unused) — kept locked to Claude
    "drafting":   "anthropic",   # only used if a key is set; else templates
    "summary":    "anthropic",
}
