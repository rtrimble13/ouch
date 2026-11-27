"""Pydantic models for every tax data file (spec §6).

A malformed file is a hard error, never a warning (P5).
All numeric figures parse to Decimal — no floats survive validation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import (BaseModel, ConfigDict, Field, field_validator,
                      model_validator)

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


class SaltAmount(_Model):
    """A SALT figure with its married-filing-separately counterpart."""
    amount: Decimal = Field(ge=0)
    mfs_amount: Decimal = Field(ge=0)

    def for_status(self, status: FilingStatus) -> Decimal:
        return (self.mfs_amount if status == FilingStatus.MARRIED_FILING_SEPARATELY
                else self.amount)


class SaltPhasedown(_Model):
    """High-income reduction of the SALT cap (IRC §164(b)(7), from 2025).

    The cap is reduced by ``rate`` × (MAGI − ``threshold``), but never below
    ``floor``.
    """
    threshold: SaltAmount
    rate: Decimal = Field(gt=0, le=1)
    floor: SaltAmount


class SaltCap(SaltAmount):
    phasedown: Optional[SaltPhasedown] = None

    @model_validator(mode="after")
    def _floor_within_cap(self) -> "SaltCap":
        pd = self.phasedown
        if pd is not None and (pd.floor.amount > self.amount
                               or pd.floor.mfs_amount > self.mfs_amount):
            raise ValueError("salt_cap.phasedown.floor exceeds the cap it "
                             "reduces")
        return self


class CharitableLimits(_Model):
    cash: Decimal
    noncash: Decimal
    appreciated: Decimal


class NonItemizerCharitable(_Model):
    """Form 1040 line 12f (2026 onward): cash gifts deductible without
    itemizing, up to ``amount`` (``mfj_amount`` on a joint return)."""
    amount: Decimal = Field(gt=0)
    mfj_amount: Decimal = Field(gt=0)


class ItemizedLimitation(_Model):
    """§68 as amended by OBBBA (2026 onward): itemized deductions are
    reduced by ``rate`` × the lesser of the itemized total and the income
    above ``threshold[status]`` (the start of the 37% bracket), measured as
    AGI less Schedule 1-A and QBI deductions (draft 2026 Schedule A line 18)."""
    rate: Decimal = Field(gt=0, le=1)
    threshold: StatusAmount

    @field_validator("threshold")
    @classmethod
    def _all_statuses(cls, v: StatusAmount) -> StatusAmount:
        missing = [s.value for s in FilingStatus if s not in v]
        if missing:
            raise ValueError(f"limitation.threshold missing {', '.join(missing)}")
        return v


class Itemized(_Model):
    salt_cap: SaltCap
    medical_agi_floor: Decimal
    mortgage_acquisition_limit: Decimal
    mortgage_grandfathered_limit: Decimal
    charitable_agi_limits: CharitableLimits
    # 2026 onward; each absent means the rule isn't in force that year.
    charitable_floor_agi_pct: Optional[Decimal] = Field(default=None, gt=0, le=1)
    nonitemizer_charitable: Optional[NonItemizerCharitable] = None
    limitation: Optional[ItemizedLimitation] = None


class WageUbiaAlt(_Model):
    wage_pct: Decimal
    ubia_pct: Decimal


class QbiMinimum(_Model):
    """§199A(i) (OBBBA §70105, 2026 onward): the deduction is at least
    ``amount`` when active QBI is at least ``active_qbi_threshold``
    (draft 2026 Form 8995 lines 16–17)."""
    amount: Decimal = Field(gt=0)
    active_qbi_threshold: Decimal = Field(gt=0)


class Qbi(_Model):
    rate: Decimal
    threshold: StatusAmount
    phase_in_range: StatusAmount
    wage_limit_pct: Decimal
    wage_ubia_alt: WageUbiaAlt
    sstb_disallowed_above_phasein: bool = True
    minimum_deduction: Optional[QbiMinimum] = None


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
    # §55(b)(1): married filing separately reaches 28% at half the amount.
    # Absent, MFS uses `brackets` (files written before this field existed).
    brackets_mfs: Optional[list[Bracket]] = None

    @field_validator("brackets", "brackets_mfs")
    @classmethod
    def _ordered(cls, v: Optional[list[Bracket]], info) -> Optional[list[Bracket]]:
        if v is not None:
            _validate_brackets(v, f"amt.{info.field_name}")
        return v

    def brackets_for(self, status: FilingStatus) -> list[Bracket]:
        if status == FilingStatus.MARRIED_FILING_SEPARATELY and self.brackets_mfs:
            return self.brackets_mfs
        return self.brackets


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


class EitcTier(_Model):
    children: int
    phase_in_rate: Decimal
    earned_income_amount: Decimal     # plateau start (earned income at max)
    max_credit: Decimal
    phaseout_start_mfj: Decimal
    phaseout_start_other: Decimal
    phaseout_rate: Decimal


class Eitc(_Model):
    investment_income_limit: Decimal
    by_children: list[EitcTier]


class CareHighIncomePhasedown(_Model):
    """The second step-down of the care credit rate (OBBBA §70405, 2026):
    from the first tier's floor, ``step_rate`` for each ``step`` (or part)
    of AGI over the threshold, down to ``min_rate``. Joint returns have
    their own threshold and step; every other status uses the ``other``
    figures."""
    agi_threshold_mfj: Decimal
    agi_threshold_other: Decimal
    step_mfj: Decimal = Field(gt=0)
    step_other: Decimal = Field(gt=0)
    step_rate: Decimal = Field(gt=0, le=1)
    min_rate: Decimal = Field(ge=0, le=1)


class ChildDependentCare(_Model):
    max_expenses_one: Decimal
    max_expenses_two_plus: Decimal
    max_rate: Decimal                 # 35% (50% from 2026)
    min_rate: Decimal                 # floor of the first step-down
    agi_threshold: Decimal            # rate steps down above this
    step: Decimal                     # per this much AGI (or part)
    step_rate: Decimal                # by this much
    qualifying_age_max: int = 12
    # 2026 onward: a second step-down to a lower floor at higher AGI.
    high_income_phasedown: Optional[CareHighIncomePhasedown] = None

    @model_validator(mode="after")
    def _floors_ordered(self) -> "ChildDependentCare":
        hp = self.high_income_phasedown
        if hp is not None and hp.min_rate > self.min_rate:
            raise ValueError("child_dependent_care.high_income_phasedown.min_rate "
                             "must not exceed the first tier's min_rate")
        return self


class EducationPhaseout(_Model):
    mfj_start: Decimal
    mfj_end: Decimal
    other_start: Decimal
    other_end: Decimal


class Aotc(_Model):
    first_dollar: Decimal             # 100% of the first ...
    second_rate: Decimal              # then this rate on the next ...
    second_cap: Decimal
    refundable_pct: Decimal
    phaseout: EducationPhaseout


class Llc(_Model):
    rate: Decimal
    max_expenses: Decimal
    phaseout: EducationPhaseout


class Education(_Model):
    aotc: Aotc
    llc: Llc


class SaversTier(_Model):
    mfj_up_to: Decimal
    hoh_up_to: Decimal
    other_up_to: Decimal
    rate: Decimal


class SaversCredit(_Model):
    contribution_cap: Decimal
    tiers: list[SaversTier]           # descending rates, ascending AGI


class Credits(_Model):
    child_tax_credit: ChildTaxCredit
    other_dependent_credit: OtherDependentCredit
    eitc: Optional[Eitc] = None
    child_dependent_care: Optional[ChildDependentCare] = None
    education: Optional[Education] = None
    savers_credit: Optional[SaversCredit] = None


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


class SeniorDeduction(_Model):
    """Enhanced deduction for seniors (Schedule 1-A Part V; 2025–2028).

    Each qualifying individual gets ``amount`` less ``phaseout_rate`` ×
    (MAGI − ``phaseout_threshold[status]``), floored at zero. Married
    filers must file jointly to claim it.
    """
    amount: Decimal = Field(gt=0)            # per qualifying individual
    min_age: int = Field(default=65, gt=0)
    phaseout_threshold: StatusAmount
    phaseout_rate: Decimal = Field(gt=0, le=1)

    @field_validator("phaseout_threshold")
    @classmethod
    def _all_statuses(cls, v: StatusAmount) -> StatusAmount:
        missing = [s.value for s in FilingStatus if s not in v]
        if missing:
            raise ValueError(f"phaseout_threshold missing {', '.join(missing)}")
        return v


class PhasedDeduction(_Model):
    """A capped Schedule 1-A deduction with a stepped MAGI phase-out
    (tips, Part II; overtime, Part III; car-loan interest, Part IV).

    deduction = min(amount, cap[status]) − reduction_per_step × steps, where
    steps = (MAGI − threshold) / step, rounded as the form says: down for
    tips and overtime (lines 11, 19), up for car-loan interest (line 28).
    """
    cap: StatusAmount
    phaseout_threshold: StatusAmount
    reduction_per_step: Decimal = Field(gt=0)
    step: Decimal = Field(default=Decimal(1000), gt=0)
    round_steps: Literal["down", "up"]
    joint_return_required: bool     # "If married, you must file jointly"

    @field_validator("cap", "phaseout_threshold")
    @classmethod
    def _all_statuses(cls, v: StatusAmount, info) -> StatusAmount:
        missing = [s.value for s in FilingStatus if s not in v]
        if missing:
            raise ValueError(f"{info.field_name} missing {', '.join(missing)}")
        return v


class Schedule1A(_Model):
    """Additional deductions claimed on Schedule 1-A (Form 1040 line 13b).

    A section's presence means the provision is in force for the file's
    year; absence means it is not (no year checks in the engine).
    """
    senior: Optional[SeniorDeduction] = None
    tips: Optional[PhasedDeduction] = None
    overtime: Optional[PhasedDeduction] = None
    car_loan_interest: Optional[PhasedDeduction] = None


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
    schedule_1a: Optional[Schedule1A] = None

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
