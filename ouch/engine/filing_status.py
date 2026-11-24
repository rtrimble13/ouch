"""Filing-status alternatives for `estimate --compare-filing-status`.

Pure: decides which statuses can be honestly computed from one profile.
Eligibility is planning-grade — tested only against what the profile
records (dependents' months in the home), never the household-cost,
dependency or marital-status facts behind it, which the user confirms.
"""

from __future__ import annotations

from dataclasses import dataclass

from ouch.model.enums import FilingStatus
from ouch.model.input import TaxInput

MARRIED = (FilingStatus.MARRIED_FILING_JOINTLY,
           FilingStatus.MARRIED_FILING_SEPARATELY)

# Order statuses are displayed in.
_ORDER = (FilingStatus.SINGLE, FilingStatus.HEAD_OF_HOUSEHOLD,
          FilingStatus.QUALIFYING_SURVIVING_SPOUSE)


@dataclass(frozen=True)
class StatusOptions:
    statuses: tuple[FilingStatus, ...]                   # computed, in order
    omitted: tuple[tuple[FilingStatus, str], ...]        # (status, reason)


def has_hoh_qualifying_person(inp: TaxInput) -> bool:
    """A dependent who lived in the home more than half the year, or a
    parent (who need not live with the taxpayer) — IRC §2(b)."""
    return any(d.months_in_home > 6 or d.relationship.lower() == "parent"
               for d in inp.dependents)


def status_alternatives(inp: TaxInput) -> StatusOptions:
    """Statuses to compare for an unmarried profile. Married profiles are
    the caller's to refuse: a joint profile cannot be split into two
    separate returns, because income, deductions and payments are not
    attributed per spouse."""
    current = inp.taxpayer.filing_status
    if current in MARRIED:
        raise ValueError("married profiles have no computable alternatives")
    chosen = {FilingStatus.SINGLE, current}
    omitted: list[tuple[FilingStatus, str]] = []
    if has_hoh_qualifying_person(inp):
        chosen.add(FilingStatus.HEAD_OF_HOUSEHOLD)
    elif current != FilingStatus.HEAD_OF_HOUSEHOLD:
        omitted.append((FilingStatus.HEAD_OF_HOUSEHOLD,
                        "needs a qualifying person — no dependent in the "
                        "profile lived in your home more than half the year"))
    if current != FilingStatus.QUALIFYING_SURVIVING_SPOUSE:
        omitted.append((FilingStatus.QUALIFYING_SURVIVING_SPOUSE,
                        "requires a spouse who died in one of the two prior "
                        "years and a dependent child — set filing_status "
                        "explicitly if that applies"))
    return StatusOptions(
        statuses=tuple(s for s in _ORDER if s in chosen),
        omitted=tuple(omitted))


def with_status(inp: TaxInput, status: FilingStatus) -> TaxInput:
    """A re-validated copy of `inp` filed under `status`."""
    raw = inp.model_dump()
    raw["taxpayer"]["filing_status"] = status
    return TaxInput.model_validate(raw)
