"""Standard vs. itemized deduction and QBI (spec §9.5, §9.6)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ouch.model.enums import DeductionMode, FilingStatus
from ouch.model.input import TaxInput
from ouch.model.money import Money, ZERO, maxm, minm
from ouch.taxdata.schema import FederalData

_MARRIED = {
    FilingStatus.MARRIED_FILING_JOINTLY,
    FilingStatus.MARRIED_FILING_SEPARATELY,
    FilingStatus.QUALIFYING_SURVIVING_SPOUSE,
}


def standard_deduction(inp: TaxInput, fed: FederalData) -> Money:
    sd = fed.standard_deduction
    status = inp.taxpayer.filing_status
    total = Money(sd.base(status))
    married = status in _MARRIED
    add_65 = Money(sd.additional_age65.married if married else sd.additional_age65.single)
    add_blind = Money(sd.additional_blind.married if married else sd.additional_blind.single)

    people = [inp.taxpayer]
    if inp.spouse is not None and status in _MARRIED:
        people.append(inp.spouse)
    for person in people:
        # "Born before January 2, 1961" for 2025: you reach 65 the day
        # before your 65th birthday, so a January 1 birthday counts.
        if inp.reaches_age_by_year_end(person.birth_date, 65):
            total += add_65
        if person.blind:
            total += add_blind
    return total


@dataclass(frozen=True)
class SeniorResult:
    deduction: Money
    per_person: Money        # each qualifying individual's amount after phase-out
    qualifying: int          # people who meet the age test and may claim
    warnings: tuple[str, ...] = ()


def senior_deduction(inp: TaxInput, magi: Money, fed: FederalData) -> SeniorResult:
    """Enhanced deduction for seniors — Schedule 1-A (2025) Part V.

    Lines 31–35: $6,000 less 6% of MAGI over $75,000 ($150,000 MFJ), not
    below zero. Lines 36a–37: that amount once for the taxpayer and once
    for a joint-return spouse, each if born before January 2 of the year
    they turn 65. Married filers must file jointly to claim it.

    MAGI (Part I) is AGI plus excluded Puerto Rico income and the Form
    2555 / 4563 exclusions; ouch has no inputs for those, so callers pass
    AGI. The valid-SSN requirement has no profile input and is assumed met.
    """
    section = fed.schedule_1a.senior if fed.schedule_1a else None
    if section is None:
        return SeniorResult(ZERO, ZERO, 0)
    status = inp.taxpayer.filing_status
    people = [inp.taxpayer]
    if status == FilingStatus.MARRIED_FILING_JOINTLY and inp.spouse is not None:
        people.append(inp.spouse)
    seniors = sum(1 for p in people
                  if inp.reaches_age_by_year_end(p.birth_date, section.min_age))
    if seniors == 0:
        return SeniorResult(ZERO, ZERO, 0)
    if status == FilingStatus.MARRIED_FILING_SEPARATELY:
        return SeniorResult(ZERO, ZERO, 0, (
            "the enhanced deduction for seniors requires a joint return if "
            "married; none allowed when filing separately",))
    excess = maxm(ZERO, magi - Money(section.phaseout_threshold[status]))
    per_person = maxm(ZERO, Money(section.amount) - excess * section.phaseout_rate)
    warnings = ("enhanced deduction for seniors assumes each qualifying "
                "person has a valid Social Security number",)
    return SeniorResult(per_person * seniors, per_person, seniors, warnings)


@dataclass(frozen=True)
class ItemizedResult:
    total: Money
    medical: Money
    salt: Money
    salt_income_component: Money  # the state/local income tax actually deducted
    salt_capped: bool
    mortgage_interest: Money
    charitable: Money
    investment_interest: Money
    other: Money


def itemized_deduction(inp: TaxInput, agi: Money, salt_income_estimate: Money,
                       ordinary_investment_income: Money,
                       fed: FederalData) -> ItemizedResult:
    it = inp.deductions.itemized
    rules = fed.itemized
    status = inp.taxpayer.filing_status

    medical = maxm(ZERO, Money(it.medical_expenses) - agi * rules.medical_agi_floor)

    # SALT: user-supplied income tax figure wins; otherwise the engine's
    # computed state+local liability estimate (resolved by the §9.9 loop).
    salt_income = (Money(it.state_local_income_tax)
                   if it.state_local_income_tax > 0 else salt_income_estimate)
    salt_income = maxm(salt_income, ZERO)
    salt_total = salt_income + Money(it.real_estate_tax) + Money(it.personal_property_tax)
    cap = Money(rules.salt_cap.mfs_amount
                if status == FilingStatus.MARRIED_FILING_SEPARATELY
                else rules.salt_cap.amount)
    salt = minm(salt_total, cap)
    salt_capped = salt_total > cap
    # Portion of the deduction attributable to income tax (for state addbacks):
    salt_income_deducted = minm(salt_income, salt)

    # Mortgage interest limited by acquisition debt.
    limit = Money(rules.mortgage_grandfathered_limit if it.mortgage_grandfathered
                  else rules.mortgage_acquisition_limit)
    balance = Money(it.mortgage_balance)
    if balance > ZERO and balance > limit:
        factor = limit.ratio(balance)
        mortgage = Money(it.mortgage_interest) * factor
    else:
        mortgage = Money(it.mortgage_interest)

    charitable = (minm(Money(it.charitable_cash), agi * rules.charitable_agi_limits.cash)
                  + minm(Money(it.charitable_noncash), agi * rules.charitable_agi_limits.noncash))

    inv_interest = minm(Money(it.investment_interest),
                        maxm(ordinary_investment_income, ZERO))

    total = medical + salt + mortgage + charitable + inv_interest + Money(it.other)
    return ItemizedResult(
        total=total, medical=medical, salt=salt,
        salt_income_component=salt_income_deducted, salt_capped=salt_capped,
        mortgage_interest=mortgage, charitable=charitable,
        investment_interest=inv_interest, other=Money(it.other),
    )


@dataclass(frozen=True)
class QbiResult:
    deduction: Money
    qualified_business_income: Money
    warnings: tuple[str, ...] = ()


def qbi_deduction(inp: TaxInput, taxable_before_qbi: Money,
                  net_capital_gain: Money, se_deduction: Money,
                  se_health: Money, fed: FederalData) -> QbiResult:
    """§199A (fidelity: approximate — aggregation and REIT/PTP are v2)."""
    q = fed.qbi
    status = inp.taxpayer.filing_status
    biz = inp.income.business

    qbi = Money(biz.qbi_eligible_income)
    if qbi <= ZERO:
        return QbiResult(ZERO, ZERO)
    # QBI is reduced by the deductions attributable to the business:
    # ½ SE tax, SE health insurance, and self-employed retirement.
    qbi = maxm(ZERO, qbi - se_deduction - se_health - Money(inp.adjustments.sep_solo401k))
    if qbi <= ZERO:
        return QbiResult(ZERO, ZERO)

    tentative = qbi * q.rate
    overall_limit = maxm(ZERO, taxable_before_qbi - net_capital_gain) * q.rate

    threshold = Money(q.threshold[status])
    phase_range = Money(q.phase_in_range[status])
    ti = taxable_before_qbi
    wages = Money(biz.qbi_w2_wages_paid)
    ubia = Money(biz.qbi_ubia)

    def wage_cap(w: Money, u: Money) -> Money:
        return maxm(w * q.wage_limit_pct,
                    w * q.wage_ubia_alt.wage_pct + u * q.wage_ubia_alt.ubia_pct)

    if ti <= threshold:
        deduction = minm(tentative, overall_limit)
    elif ti >= threshold + phase_range:
        if biz.sstb and q.sstb_disallowed_above_phasein:
            deduction = ZERO
        else:
            deduction = minm(tentative, wage_cap(wages, ubia), overall_limit)
    else:
        pct = (ti - threshold).ratio(phase_range)
        if biz.sstb:
            keep = Decimal(1) - pct
            qbi_s, wages_s, ubia_s = qbi * keep, wages * keep, ubia * keep
        else:
            qbi_s, wages_s, ubia_s = qbi, wages, ubia
        tent_s = qbi_s * q.rate
        cap_s = wage_cap(wages_s, ubia_s)
        if tent_s > cap_s:
            # Apply the wage limitation only to the phased-in fraction.
            amount = tent_s - (tent_s - cap_s) * pct
        else:
            amount = tent_s
        deduction = minm(amount, overall_limit)

    return QbiResult(deduction=deduction, qualified_business_income=qbi)
