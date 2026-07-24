"""Pydantic models for every tax data file (spec §6).

A malformed file is a hard error, never a warning (P5).
All numeric figures parse to Decimal — no floats survive validation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ouch.model.enums import FilingStatus, StateRegime, StartingPoint

SUPPORTED_SCHEMA_VERSIONS = range(1, 4)  # inclusive of 3


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Bracket(_Model):
    up_to: Optional[Decimal] = None  # None = top bracket
    rate: Decimal = Field(ge=0, le=1)


StatusBrackets = dict[FilingStatus, list[Bracket]]
StatusAmount = dict[FilingStatus, Decimal]


def _validate_brackets(brackets: list[Bracket], where: str) -> None:
    prev = Decimal("-1")
    for i, b in enumerate(brackets):
        last = i == len(brackets) - 1
        if b.up_to is None and not last:
            raise ValueError(f"{where}: only the last bracket may omit up_to")
        if b.up_to is not None:
            if b.up_to <= prev:
                raise ValueError(f"{where}: bracket ceilings must be increasing")
            prev = b.up_to


class Meta(_Model):
    jurisdiction: str
    year: int
    schema_version: int = 3
    verified: bool = False
    parent: Optional[str] = None
    source: list[str] = []
    notes: str = ""
    effective: Optional[str] = None

    @field_validator("schema_version")
    @classmethod
    def _supported(cls, v: int) -> int:
        if v not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"data schema_version {v} is not supported by this ouch "
                f"(supports {min(SUPPORTED_SCHEMA_VERSIONS)}–{max(SUPPORTED_SCHEMA_VERSIONS)}); "
                f"upgrade ouch"
            )
        return v


class AdditionalDeduction(_Model):
    single: Decimal
    married: Decimal


class StandardDeduction(_Model):
    single: Decimal
    married_filing_jointly: Decimal
    married_filing_separately: Decimal
    head_of_household: Decimal
    qualifying_surviving_spouse: Decimal
    additional_age65: AdditionalDeduction
    additional_blind: AdditionalDeduction
    dependent_floor: Decimal = Decimal(0)
    dependent_earned_addon: Decimal = Decimal(0)

    def base(self, status: FilingStatus) -> Decimal:
        return getattr(self, status.value)


class SaltCap(_Model):
    amount: Decimal
    mfs_amount: Decimal
    phasedown: Optional[dict] = None


class CharitableLimits(_Model):
    cash: Decimal
    noncash: Decimal
    appreciated: Decimal


class Itemized(_Model):
    salt_cap: SaltCap
    medical_agi_floor: Decimal
    mortgage_acquisition_limit: Decimal
    mortgage_grandfathered_limit: Decimal
    charitable_agi_limits: CharitableLimits


class WageUbiaAlt(_Model):
    wage_pct: Decimal
    ubia_pct: Decimal


class Qbi(_Model):
    rate: Decimal
    threshold: StatusAmount
    phase_in_range: StatusAmount
    wage_limit_pct: Decimal
    wage_ubia_alt: WageUbiaAlt
    sstb_disallowed_above_phasein: bool = True


class SocialSecurityPayroll(_Model):
    rate_employee: Decimal
    rate_self_employed: Decimal
    wage_base: Decimal


class MedicarePayroll(_Model):
    rate_employee: Decimal
    rate_self_employed: Decimal


class AdditionalMedicare(_Model):
    rate: Decimal
    threshold: StatusAmount


class Payroll(_Model):
    social_security: SocialSecurityPayroll
    medicare: MedicarePayroll
    additional_medicare: AdditionalMedicare
    se_income_factor: Decimal
    se_deduction_pct: Decimal


class Niit(_Model):
    rate: Decimal
    threshold: StatusAmount


class Amt(_Model):
    exemption: StatusAmount
    phaseout_threshold: StatusAmount
    phaseout_rate: Decimal
    brackets: list[Bracket]


class CapitalLoss(_Model):
    annual_ordinary_offset: Decimal
    mfs_offset: Decimal


class ChildTaxCredit(_Model):
    amount_per_child: Decimal
    refundable_cap: Decimal
    phaseout_start: StatusAmount
    phaseout_rate_per_1000: Decimal
    qualifying_age_max: int
    refundable_earned_income_floor: Decimal = Decimal(2500)
    refundable_earned_income_pct: Decimal = Decimal("0.15")


class OtherDependentCredit(_Model):
    amount: Decimal


class Credits(_Model):
    child_tax_credit: ChildTaxCredit
    other_dependent_credit: OtherDependentCredit


class SafeHarbor(_Model):
    current_year_pct: Decimal
    prior_year_pct: Decimal
    prior_year_pct_high_income: Decimal
    high_income_agi_threshold: Decimal
    high_income_agi_threshold_mfs: Decimal


class EstimatedPaymentsData(_Model):
    safe_harbor: SafeHarbor
    due_dates: list[str]
    underpayment_rate_by_quarter: list[Decimal]


class SocialSecurityTaxability(_Model):
    base_amount: StatusAmount
    adjusted_base: StatusAmount
    max_inclusion: Decimal


class SpecialRateGroups(_Model):
    unrecaptured_1250: Decimal
    collectibles: Decimal


class FederalData(_Model):
    meta: Meta
    ordinary_brackets: StatusBrackets
    preferential_brackets: StatusBrackets
    special_rate_groups: SpecialRateGroups
    standard_deduction: StandardDeduction
    itemized: Itemized
    qbi: Qbi
    payroll: Payroll
    niit: Niit
    amt: Amt
    capital_loss: CapitalLoss
    credits: Credits
    estimated_payments: EstimatedPaymentsData
    social_security_taxability: SocialSecurityTaxability

    @field_validator("ordinary_brackets", "preferential_brackets")
    @classmethod
    def _complete_and_ordered(cls, v: StatusBrackets, info) -> StatusBrackets:
        for status in FilingStatus:
            if status not in v:
                raise ValueError(f"{info.field_name}: missing filing status '{status}'")
            _validate_brackets(v[status], f"{info.field_name}.{status}")
        return v


class Modification(_Model):
    id: str
    label: str
    source_field: Optional[str] = None
    cap: Optional[Decimal] = None
    min_age: Optional[Decimal] = None


class Modifications(_Model):
    additions: list[Modification] = []
    subtractions: list[Modification] = []


class StateItemized(_Model):
    allowed: bool = False
    decouple_from_federal: bool = True
    salt_deductible: bool = False


class StateCredit(_Model):
    id: str
    type: str = "nonrefundable"
    amount: Optional[Decimal] = None
    pct_of_federal: Optional[Decimal] = None
    table: Optional[list] = None


class PersonalExemption(_Model):
    per_dependent: Decimal = Decimal(0)
    per_filer: Decimal = Decimal(0)


class StateData(_Model):
    meta: Meta
    regime: StateRegime
    starting_point: StartingPoint = StartingPoint.FEDERAL_AGI
    rate: Optional[Decimal] = None                    # flat regime
    brackets: Optional[StatusBrackets] = None         # progressive regime
    modifications: Modifications = Modifications()
    standard_deduction: Optional[StatusAmount] = None
    personal_exemption: PersonalExemption = PersonalExemption()
    itemized: StateItemized = StateItemized()
    credits: list[StateCredit] = []
    capital_gains_treatment: str = "ordinary"         # ordinary | preferential | exempt_pct
    supplemental_withholding_rate: Optional[Decimal] = None
    reciprocity_states: list[str] = []
    credit_for_taxes_paid_other_states: bool = False

    @field_validator("brackets")
    @classmethod
    def _ordered(cls, v: Optional[StatusBrackets]) -> Optional[StatusBrackets]:
        if v is not None:
            for status, brackets in v.items():
                _validate_brackets(brackets, f"brackets.{status}")
        return v

    def validate_regime(self) -> None:
        if self.regime == StateRegime.FLAT and self.rate is None:
            raise ValueError("regime 'flat' requires a `rate` key")
        if self.regime == StateRegime.PROGRESSIVE and not self.brackets:
            raise ValueError("regime 'progressive' requires `brackets`")


class LocalData(_Model):
    meta: Meta
    regime: StateRegime
    applies_to: str = "residents"                     # residents | workers | both
    starting_point: StartingPoint = StartingPoint.STATE_TAXABLE
    rate: Optional[Decimal] = None
    brackets: Optional[StatusBrackets] = None
    credits: list[StateCredit] = []

    def validate_regime(self) -> None:
        if self.regime == StateRegime.FLAT and self.rate is None:
            raise ValueError("regime 'flat' requires a `rate` key")
        if self.regime == StateRegime.PROGRESSIVE and not self.brackets:
            raise ValueError("regime 'progressive' requires `brackets`")
