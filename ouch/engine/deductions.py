"""Standard vs. itemized deduction and QBI (spec §9.5, §9.6)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from ouch.model.enums import DeductionMode, FilingStatus
from ouch.model.input import TaxInput
from ouch.model.money import Money, ZERO, maxm, minm
from ouch.taxdata.schema import FederalData, PhasedDeduction, SaltCap

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


def phased_deduction(amount: Money, magi: Money, status: FilingStatus,
                     section: PhasedDeduction) -> Money:
    """A Schedule 1-A capped deduction with a stepped phase-out.

    Tips (Part II, lines 7–13), overtime (Part III, lines 15–21) and car-loan
    interest (Part IV, lines 24–30) share one shape: cap the amount, then
    subtract ``reduction_per_step`` for each ``step`` of MAGI over the
    threshold, with the step count rounded as the form directs.
    """
    capped = minm(maxm(amount, ZERO), Money(section.cap[status]))
    excess = magi - Money(section.phaseout_threshold[status])
    if capped <= ZERO or excess <= ZERO:
        return capped
    ratio = excess.amount / section.step
    steps = (ratio.to_integral_value(rounding=ROUND_FLOOR)
             if section.round_steps == "down"
             else ratio.to_integral_value(rounding=ROUND_CEILING))
    return maxm(ZERO, capped - Money(section.reduction_per_step) * steps)


@dataclass(frozen=True)
class Schedule1AItem:
    key: str              # trace id suffix: fed.deduction.<key>
    label: str
    amount: Money
    claimed: Money        # before cap and phase-out
    section: PhasedDeduction
    warnings: tuple[str, ...]


def schedule_1a_items(inp: TaxInput, magi: Money,
                      fed: FederalData) -> list[Schedule1AItem]:
    """Tips, overtime and car-loan interest (Schedule 1-A Parts II–IV).

    MAGI is AGI (ouch has no inputs for the Part I exclusions). Tips and
    overtime need a joint return if married; car-loan interest doesn't.
    Eligibility the profile can't express (occupation, the FLSA premium,
    the vehicle) is assumed and disclosed.
    """
    sched = fed.schedule_1a
    if sched is None:
        return []
    status = inp.taxpayer.filing_status
    w = inp.income.wages
    joint = status == FilingStatus.MARRIED_FILING_JOINTLY
    spouse_tips = Money(w.spouse_qualified_tips) if joint else ZERO
    spouse_ot = Money(w.spouse_qualified_overtime) if joint else ZERO
    candidates = (
        ("tips", "Qualified tips deduction", sched.tips,
         Money(w.taxpayer_qualified_tips) + spouse_tips,
         "qualified tips deduction assumes the tips were earned in an "
         "occupation on the Treasury list (IRS.gov/TippedOccupations) and that "
         "each recipient has a valid Social Security number"),
        ("overtime", "Qualified overtime deduction", sched.overtime,
         Money(w.taxpayer_qualified_overtime) + spouse_ot,
         "qualified overtime deduction assumes the amount entered is only the "
         "premium portion of FLSA overtime and that each recipient has a "
         "valid Social Security number"),
        ("car_loan_interest", "Car loan interest deduction",
         sched.car_loan_interest, Money(inp.deductions.car_loan_interest),
         "car loan interest deduction assumes the loan is for an applicable "
         "passenger vehicle bought after 2024 for personal use (see the "
         "Schedule 1-A instructions)"),
    )
    items: list[Schedule1AItem] = []
    for key, label, section, claimed, assumption in candidates:
        if section is None or claimed <= ZERO:
            continue
        if section.joint_return_required and status == FilingStatus.MARRIED_FILING_SEPARATELY:
            items.append(Schedule1AItem(key, label, ZERO, claimed, section, (
                f"{label.lower()} requires a joint return if married; none "
                f"allowed when filing separately",)))
            continue
        amount = phased_deduction(claimed, magi, status, section)
        items.append(Schedule1AItem(key, label, amount, claimed, section,
                                    (assumption,)))
    return items


@dataclass(frozen=True)
class ItemizedResult:
    total: Money
    medical: Money
    salt: Money
    salt_income_component: Money  # the state/local income tax actually deducted
    salt_capped: bool
    salt_cap: Money          # the cap in force, after any phase-down
    salt_cap_reduced: bool   # True when the high-income phase-down lowered it
    mortgage_interest: Money
    charitable: Money
    investment_interest: Money
    other: Money


def salt_cap(status: FilingStatus, magi: Money, rules: SaltCap) -> Money:
    """The SALT cap in force for this return (IRC §164(b)(6)–(7)).

    With a phase-down (2025 onward), the cap is reduced by ``rate`` × the
    excess of modified AGI over the threshold, but not below the floor —
    Schedule A instructions, State and Local Tax Deduction Worksheet lines
    5–9. Married filing separately uses the halved cap, threshold and floor.

    MAGI for this purpose is AGI increased by income excluded under
    §§911, 931 and 933 (foreign earned income, possessions, Puerto Rico).
    ouch has no inputs for those exclusions, so callers pass AGI.
    """
    cap = Money(rules.for_status(status))
    pd = rules.phasedown
    if pd is None:
        return cap
    excess = maxm(ZERO, magi - Money(pd.threshold.for_status(status)))
    return maxm(Money(pd.floor.for_status(status)), cap - excess * pd.rate)


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
    full_cap = Money(rules.salt_cap.for_status(status))
    cap = salt_cap(status, agi, rules.salt_cap)  # MAGI = AGI (no §911/931/933 inputs)
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
        salt_cap=cap, salt_cap_reduced=cap < full_cap,
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
