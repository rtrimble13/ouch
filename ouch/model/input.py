"""TaxInput and sub-models (spec §7.3).

Frozen pydantic models mirroring the profile schema (§5.3), post-validation
and post-merge. Immutable — the scenario engine and solver produce new
instances via `model_copy(update=...)`, never mutation.

All money amounts are Decimal here; the engine wraps them in Money.
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ouch.model.enums import DeductionMode, FilingStatus


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


NonNeg = Field(default=Decimal(0), ge=0)
AnyAmt = Field(default=Decimal(0))


class Person(_Frozen):
    name: str = ""
    birth_date: Optional[date] = None
    blind: bool = False


class Taxpayer(Person):
    filing_status: FilingStatus = FilingStatus.SINGLE
    state: str = ""
    locality: str = ""
    residency_months: int = Field(default=12, ge=0, le=12)
    former_state: str = ""  # part-year: state lived in for 12 − residency_months


class Dependent(_Frozen):
    name: str = ""
    birth_date: Optional[date] = None
    relationship: str = "child"
    months_in_home: int = Field(default=12, ge=0, le=12)
    student: bool = False
    disabled: bool = False
    qualifies_ctc: Optional[bool] = None  # engine re-derives; this is an override


class WagesIncome(_Frozen):
    taxpayer_w2: Decimal = NonNeg
    spouse_w2: Decimal = NonNeg
    taxpayer_ss_wages: Decimal = NonNeg  # box 3, for SS wage-base coordination
    spouse_ss_wages: Decimal = NonNeg
    # box 5, uncapped — the Additional Medicare (Form 8959) base. Defaults to
    # box 1 per person when absent; box 5 usually exceeds box 1 by elective
    # 401(k)/403(b) deferrals.
    taxpayer_medicare_wages: Decimal = NonNeg
    spouse_medicare_wages: Decimal = NonNeg


class InvestmentIncome(_Frozen):
    interest: Decimal = NonNeg
    tax_exempt_interest: Decimal = NonNeg
    in_state_muni_interest: Decimal = NonNeg
    treasury_interest: Decimal = NonNeg
    qualified_dividends: Decimal = NonNeg
    ordinary_dividends: Decimal = NonNeg  # inclusive of qualified
    short_term_gains: Decimal = AnyAmt
    long_term_gains: Decimal = AnyAmt
    capital_loss_carryforward: Decimal = NonNeg  # positive = loss carried in
    section_1250_gain: Decimal = NonNeg  # 25% rate group
    collectibles_gain: Decimal = NonNeg  # 28% rate group

    @model_validator(mode="after")
    def _qualified_subset(self) -> "InvestmentIncome":
        if self.qualified_dividends > self.ordinary_dividends:
            raise ValueError(
                "qualified dividends cannot exceed ordinary dividends "
                "(box 1b of Form 1099-DIV is a subset of box 1a)"
            )
        return self


class BusinessIncome(_Frozen):
    # Whose Schedule C / SE: the Social Security wage base is per person
    # (IRC §1402(b)), so SE tax is coordinated against the owner's own W-2.
    owner: Literal["taxpayer", "spouse"] = "taxpayer"
    schedule_c_net: Decimal = AnyAmt
    se_health_premiums: Decimal = NonNeg
    qbi_eligible_income: Decimal = AnyAmt
    qbi_w2_wages_paid: Decimal = NonNeg
    qbi_ubia: Decimal = NonNeg
    sstb: bool = False


class RetirementIncome(_Frozen):
    pension: Decimal = NonNeg
    ira_distributions: Decimal = NonNeg
    taxable_social_security: Decimal = NonNeg  # engine computes if gross provided
    social_security_gross: Decimal = NonNeg
    roth_conversion: Decimal = NonNeg


class OtherIncome(_Frozen):
    rental_net: Decimal = AnyAmt
    k1_ordinary: Decimal = AnyAmt
    unemployment: Decimal = NonNeg
    other_income: Decimal = AnyAmt


class Income(_Frozen):
    wages: WagesIncome = WagesIncome()
    investment: InvestmentIncome = InvestmentIncome()
    business: BusinessIncome = BusinessIncome()
    retirement: RetirementIncome = RetirementIncome()
    other: OtherIncome = OtherIncome()


class Adjustments(_Frozen):
    traditional_ira: Decimal = NonNeg
    hsa: Decimal = NonNeg
    student_loan_interest: Decimal = NonNeg
    educator_expenses: Decimal = NonNeg
    sep_solo401k: Decimal = NonNeg
    alimony_paid: Decimal = NonNeg  # pre-2019 decrees only
    early_withdrawal_penalty: Decimal = NonNeg


class ItemizedDeductions(_Frozen):
    mortgage_interest: Decimal = NonNeg
    mortgage_balance: Decimal = NonNeg  # for the acquisition-debt limit
    mortgage_grandfathered: bool = False
    state_local_income_tax: Decimal = NonNeg  # engine computes if zero
    real_estate_tax: Decimal = NonNeg
    personal_property_tax: Decimal = NonNeg
    charitable_cash: Decimal = NonNeg
    charitable_noncash: Decimal = NonNeg
    medical_expenses: Decimal = NonNeg
    investment_interest: Decimal = NonNeg
    other: Decimal = NonNeg


class Deductions(_Frozen):
    mode: DeductionMode = DeductionMode.AUTO
    itemized: ItemizedDeductions = ItemizedDeductions()


class Expenses(_Frozen):
    """Credit-qualifying expenses (spec §9.8 credit suite)."""
    dependent_care: Decimal = NonNeg          # qualifying care expenses paid
    education_aotc: Decimal = NonNeg          # AOTC-qualified expenses
    education_llc: Decimal = NonNeg           # LLC-qualified expenses


class Carryovers(_Frozen):
    amt_credit: Decimal = NonNeg              # Form 8801 minimum tax credit


class Withholding(_Frozen):
    federal_ytd: Decimal = NonNeg
    state_ytd: Decimal = NonNeg
    local_ytd: Decimal = NonNeg
    federal_per_period: Decimal = NonNeg
    state_per_period: Decimal = NonNeg
    local_per_period: Decimal = NonNeg
    pay_periods_per_year: int = Field(default=24, ge=1, le=53)
    periods_remaining: int = Field(default=0, ge=0, le=53)


class EstimatedPayments(_Frozen):
    q1_federal: Decimal = NonNeg
    q2_federal: Decimal = NonNeg
    q3_federal: Decimal = NonNeg
    q4_federal: Decimal = NonNeg
    state_total: Decimal = NonNeg
    local_total: Decimal = NonNeg


class PriorYear(_Frozen):
    agi: Decimal = NonNeg
    total_tax: Decimal = NonNeg  # for safe-harbor test


class Payments(_Frozen):
    withholding: Withholding = Withholding()
    estimated: EstimatedPayments = EstimatedPayments()
    prior_year: PriorYear = PriorYear()
    # Annualized income installment method (§10.4): fraction of the year's
    # income earned by each estimated-payment period. Must sum to ~1.
    annualized_income_fractions: Optional[tuple[Decimal, Decimal, Decimal, Decimal]] = None

    @model_validator(mode="after")
    def _fractions_sum(self) -> "Payments":
        if self.annualized_income_fractions is not None:
            total = sum(self.annualized_income_fractions)
            if not (Decimal("0.99") <= total <= Decimal("1.01")):
                raise ValueError(
                    "annualized_income_fractions must sum to 1.0 "
                    f"(got {total})")
        return self


class TaxInput(_Frozen):
    tax_year: int = Field(ge=2000, le=2100)
    taxpayer: Taxpayer = Taxpayer()
    spouse: Optional[Person] = None
    dependents: tuple[Dependent, ...] = ()
    income: Income = Income()
    adjustments: Adjustments = Adjustments()
    deductions: Deductions = Deductions()
    expenses: Expenses = Expenses()
    carryovers: Carryovers = Carryovers()
    payments: Payments = Payments()

    @model_validator(mode="after")
    def _consistency(self) -> "TaxInput":
        joint = self.taxpayer.filing_status in (
            FilingStatus.MARRIED_FILING_JOINTLY,
            FilingStatus.MARRIED_FILING_SEPARATELY,
        )
        if not joint and self.spouse is not None and (
            self.income.wages.spouse_w2 > 0 or self.spouse.name
        ):
            raise ValueError(
                f"spouse data present but filing_status is "
                f"'{self.taxpayer.filing_status}' — use married_filing_jointly "
                f"or married_filing_separately, or remove the [spouse] section"
            )
        if self.income.wages.spouse_w2 > 0 and self.taxpayer.filing_status not in (
            FilingStatus.MARRIED_FILING_JOINTLY,
        ):
            raise ValueError(
                "spouse W-2 wages present but filing status is not "
                "married_filing_jointly"
            )
        if (self.income.business.owner == "spouse"
                and self.taxpayer.filing_status
                != FilingStatus.MARRIED_FILING_JOINTLY):
            raise ValueError(
                "income.business.owner is 'spouse' but filing status is not "
                "married_filing_jointly — a separate or unmarried return "
                "carries only its own filer's business"
            )
        inv = self.income.investment
        if inv.in_state_muni_interest > inv.tax_exempt_interest:
            raise ValueError(
                "in-state municipal interest cannot exceed total tax-exempt interest"
            )
        return self

    def fingerprint(self) -> str:
        """sha256 of the canonicalized input (spec §7.5)."""
        canon = self.model_dump_json()
        return "sha256:" + hashlib.sha256(canon.encode()).hexdigest()

    def age_at_year_end(self, birth_date: Optional[date]) -> Optional[int]:
        if birth_date is None:
            return None
        end = date(self.tax_year, 12, 31)
        years = end.year - birth_date.year
        if (end.month, end.day) < (birth_date.month, birth_date.day):
            years -= 1
        return years
