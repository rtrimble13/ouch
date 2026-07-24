"""Key enums (spec §7.2)."""

from __future__ import annotations

from enum import StrEnum


class FilingStatus(StrEnum):
    SINGLE = "single"
    MARRIED_FILING_JOINTLY = "married_filing_jointly"
    MARRIED_FILING_SEPARATELY = "married_filing_separately"
    HEAD_OF_HOUSEHOLD = "head_of_household"
    QUALIFYING_SURVIVING_SPOUSE = "qualifying_surviving_spouse"


class RateGroup(StrEnum):
    ORDINARY = "ordinary"
    PREFERENTIAL = "preferential"        # 0/15/20
    UNRECAPTURED_1250 = "unrecap_1250"   # 25%
    COLLECTIBLES = "collectibles"        # 28%


class Fidelity(StrEnum):
    EXACT = "exact"
    APPROXIMATE = "approximate"
    HEURISTIC = "heuristic"

    @property
    def rank(self) -> int:
        return {"exact": 0, "approximate": 1, "heuristic": 2}[self.value]

    @staticmethod
    def worst(*levels: "Fidelity") -> "Fidelity":
        return max(levels, key=lambda f: f.rank)


class DeductionMode(StrEnum):
    AUTO = "auto"
    STANDARD = "standard"
    ITEMIZED = "itemized"


class StateRegime(StrEnum):
    NONE = "none"
    FLAT = "flat"
    PROGRESSIVE = "progressive"


class StartingPoint(StrEnum):
    FEDERAL_AGI = "federal_agi"
    FEDERAL_TAXABLE = "federal_taxable"
    FEDERAL_WAGES = "federal_wages"
    INDEPENDENT = "independent"
    STATE_TAXABLE = "state_taxable"
