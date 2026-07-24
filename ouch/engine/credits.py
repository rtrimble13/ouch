"""Credits engine: phase-out primitives and the CTC/ODC (spec §9.8).

Nonrefundable credits are clamped to remaining liability; refundable credits
are applied after and may drive the balance negative.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Sequence

from ouch.model.enums import FilingStatus
from ouch.model.input import TaxInput
from ouch.model.money import Money, ZERO, maxm, minm
from ouch.taxdata.schema import FederalData

# ---------------------------------------------------------------------------
# Phase-out primitives (spec §9.8) — reusable by every credit.
# ---------------------------------------------------------------------------


def cliff(amount: Money, agi: Money, threshold: Money) -> Money:
    """Full amount below the threshold, zero above."""
    return amount if agi <= threshold else ZERO


def linear(amount: Money, agi: Money, start: Money, end: Money) -> Money:
    """Straight-line reduction across [start, end]."""
    if agi <= start:
        return amount
    if agi >= end:
        return ZERO
    remaining = Decimal(1) - (agi - start).ratio(end - start)
    return amount * remaining


def stepped(amount: Money, agi: Money, start: Money, per_increment: Money,
            increment: Money) -> Money:
    """e.g. $50 of credit lost per $1,000 (or fraction) of AGI over the start."""
    excess = agi - start
    if excess <= ZERO:
        return amount
    steps = math.ceil(excess.ratio(increment))
    return maxm(ZERO, amount - per_increment * steps)


def tiered(agi: Money, table: Sequence[tuple[Money | None, Decimal]]) -> Decimal:
    """Rate table by AGI band: [(up_to|None, rate), ...] ascending."""
    for up_to, rate in table:
        if up_to is None or agi <= up_to:
            return rate
    return Decimal(0)


def plateau(earned: Money, agi: Money, phase_in_rate: Decimal,
            plateau_start: Money, phaseout_start: Money,
            phaseout_rate: Decimal, max_credit: Money) -> Money:
    """EITC-style trapezoid: phase in on earned income, plateau, phase out on
    the greater of earned income and AGI."""
    grown = minm(earned * phase_in_rate, max_credit)
    basis = maxm(earned, agi)
    if basis <= phaseout_start:
        return grown
    reduction = (basis - phaseout_start) * phaseout_rate
    return maxm(ZERO, grown - reduction)


# ---------------------------------------------------------------------------
# Child Tax Credit / Other Dependent Credit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CtcResult:
    qualifying_children: int
    other_dependents: int
    gross: Money            # CTC + ODC before phase-out
    after_phaseout: Money
    nonrefundable_used: Money
    refundable: Money       # additional CTC
    warnings: tuple[str, ...] = ()


def child_tax_credit(inp: TaxInput, agi: Money, tax_liability: Money,
                     earned_income: Money, fed: FederalData) -> CtcResult:
    ctc = fed.credits.child_tax_credit
    odc = fed.credits.other_dependent_credit
    status = inp.taxpayer.filing_status

    n_children = 0
    n_other = 0
    for dep in inp.dependents:
        if dep.qualifies_ctc is not None:
            qualifies = dep.qualifies_ctc  # explicit override
        else:
            age = inp.age_at_year_end(dep.birth_date)
            qualifies = (dep.relationship == "child" and age is not None
                         and age <= ctc.qualifying_age_max
                         and dep.months_in_home > 6)
        if qualifies:
            n_children += 1
        else:
            n_other += 1

    gross_ctc = Money(ctc.amount_per_child) * n_children
    gross_odc = Money(odc.amount) * n_other
    gross = gross_ctc + gross_odc

    # Phase-out applies to the combined CTC+ODC: $50 per $1,000 of excess AGI.
    after = stepped(gross, agi, Money(ctc.phaseout_start[status]),
                    Money(ctc.phaseout_rate_per_1000), Money(1000))

    nonrefundable = minm(after, tax_liability)
    residue = after - nonrefundable

    # Additional CTC (refundable portion): limited to the per-child cap, the
    # unused credit, and 15% of earned income over the floor. Approximate.
    refundable = ZERO
    if residue > ZERO and n_children > 0:
        earned_excess = maxm(ZERO, earned_income - Money(ctc.refundable_earned_income_floor))
        refundable = minm(
            residue,
            Money(ctc.refundable_cap) * n_children,
            earned_excess * ctc.refundable_earned_income_pct,
        )

    warnings = ()
    if residue - refundable > ZERO:
        warnings = (f"${(residue - refundable).round_dollar().amount:,.0f} of "
                    "child/dependent credit lost to the liability limit",)

    return CtcResult(
        qualifying_children=n_children, other_dependents=n_other,
        gross=gross, after_phaseout=after,
        nonrefundable_used=nonrefundable, refundable=refundable,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Earned Income Tax Credit (EITC) — the plateau trapezoid
# ---------------------------------------------------------------------------


def _eitc_qualifying_children(inp: TaxInput) -> int:
    """EITC child test (approximate): under 19, or a student under 24, or
    disabled, living with the taxpayer more than half the year."""
    count = 0
    for dep in inp.dependents:
        if dep.relationship != "child" or dep.months_in_home <= 6:
            continue
        age = inp.age_at_year_end(dep.birth_date)
        if dep.disabled or (age is not None
                            and (age < 19 or (dep.student and age < 24))):
            count += 1
    return count


def earned_income_credit(inp: TaxInput, agi: Money, earned_income: Money,
                         investment_income: Money,
                         fed: FederalData) -> tuple[Money, tuple[str, ...]]:
    """Refundable. Returns (credit, warnings). Fidelity: approximate —
    residency/SSN/age-25-65 tests for childless claimants are not modeled."""
    eitc = fed.credits.eitc
    if eitc is None:
        return ZERO, ()
    status = inp.taxpayer.filing_status
    if status == FilingStatus.MARRIED_FILING_SEPARATELY:
        return ZERO, ("EITC: married filing separately is generally "
                      "ineligible (special rules not modeled)",)
    if investment_income > Money(eitc.investment_income_limit):
        return ZERO, (f"EITC: investment income exceeds the "
                      f"${eitc.investment_income_limit:,.0f} limit",)
    if earned_income <= ZERO:
        return ZERO, ()

    n = min(_eitc_qualifying_children(inp),
            max(t.children for t in eitc.by_children))
    tier = next(t for t in eitc.by_children if t.children == n)

    phaseout_start = Money(
        tier.phaseout_start_mfj
        if status in (FilingStatus.MARRIED_FILING_JOINTLY,
                      FilingStatus.QUALIFYING_SURVIVING_SPOUSE)
        else tier.phaseout_start_other)

    credit = plateau(
        earned=earned_income, agi=agi,
        phase_in_rate=tier.phase_in_rate,
        plateau_start=Money(tier.earned_income_amount),
        phaseout_start=phaseout_start,
        phaseout_rate=tier.phaseout_rate,
        max_credit=Money(tier.max_credit))
    return credit, ()


# ---------------------------------------------------------------------------
# Child and Dependent Care Credit
# ---------------------------------------------------------------------------


def dependent_care_credit(inp: TaxInput, agi: Money, earned_income: Money,
                          fed: FederalData) -> Money:
    """Nonrefundable. Rate slides from max_rate to min_rate as AGI rises."""
    care = fed.credits.child_dependent_care
    expenses = Money(inp.expenses.dependent_care)
    if care is None or expenses <= ZERO:
        return ZERO
    qualifying = 0
    for dep in inp.dependents:
        age = inp.age_at_year_end(dep.birth_date)
        if dep.disabled or (age is not None and age <= care.qualifying_age_max):
            qualifying += 1
    if qualifying == 0:
        return ZERO
    cap = Money(care.max_expenses_one if qualifying == 1
                else care.max_expenses_two_plus)
    base = minm(expenses, cap, maxm(earned_income, ZERO))
    excess = maxm(ZERO, agi - Money(care.agi_threshold))
    steps = math.ceil(excess.ratio(Money(care.step))) if excess > ZERO else 0
    rate = max(care.max_rate - care.step_rate * steps, care.min_rate)
    return base * rate


# ---------------------------------------------------------------------------
# Education credits (AOTC + LLC)
# ---------------------------------------------------------------------------


def _education_phaseout_fraction(agi: Money, status: FilingStatus,
                                 phaseout) -> Decimal:
    mfj = status in (FilingStatus.MARRIED_FILING_JOINTLY,
                     FilingStatus.QUALIFYING_SURVIVING_SPOUSE)
    start = Money(phaseout.mfj_start if mfj else phaseout.other_start)
    end = Money(phaseout.mfj_end if mfj else phaseout.other_end)
    if agi <= start:
        return Decimal(1)
    if agi >= end:
        return Decimal(0)
    return Decimal(1) - (agi - start).ratio(end - start)


def aotc_credit(inp: TaxInput, agi: Money,
                fed: FederalData) -> tuple[Money, Money]:
    """American Opportunity credit: returns (nonrefundable, refundable).
    MFS ineligible."""
    edu = fed.credits.education
    expenses = Money(inp.expenses.education_aotc)
    if edu is None or expenses <= ZERO:
        return ZERO, ZERO
    if inp.taxpayer.filing_status == FilingStatus.MARRIED_FILING_SEPARATELY:
        return ZERO, ZERO
    a = edu.aotc
    first = minm(expenses, Money(a.first_dollar))
    second = minm(maxm(ZERO, expenses - Money(a.first_dollar)),
                  Money(a.second_cap)) * a.second_rate
    total = (first + second) * _education_phaseout_fraction(
        agi, inp.taxpayer.filing_status, a.phaseout)
    refundable = total * a.refundable_pct
    return total - refundable, refundable


def llc_credit(inp: TaxInput, agi: Money, fed: FederalData) -> Money:
    """Lifetime Learning credit: nonrefundable. MFS ineligible."""
    edu = fed.credits.education
    expenses = Money(inp.expenses.education_llc)
    if edu is None or expenses <= ZERO:
        return ZERO
    if inp.taxpayer.filing_status == FilingStatus.MARRIED_FILING_SEPARATELY:
        return ZERO
    llc = edu.llc
    return (minm(expenses, Money(llc.max_expenses)) * llc.rate
            * _education_phaseout_fraction(
                agi, inp.taxpayer.filing_status, llc.phaseout))


# ---------------------------------------------------------------------------
# Saver's credit
# ---------------------------------------------------------------------------


def savers_credit(inp: TaxInput, agi: Money, fed: FederalData) -> Money:
    """Retirement savings contributions credit: nonrefundable, tiered by AGI.
    Fidelity: approximate — full-time-student and dependent exclusions and
    recent-distribution offsets are not modeled."""
    sc = fed.credits.savers_credit
    if sc is None:
        return ZERO
    contributions = minm(
        Money(sc.contribution_cap),
        Money(inp.adjustments.traditional_ira)
        + Money(inp.adjustments.sep_solo401k))
    if contributions <= ZERO:
        return ZERO
    status = inp.taxpayer.filing_status
    for tier in sc.tiers:  # ascending AGI ceilings, descending rates
        if status in (FilingStatus.MARRIED_FILING_JOINTLY,
                      FilingStatus.QUALIFYING_SURVIVING_SPOUSE):
            ceiling = tier.mfj_up_to
        elif status == FilingStatus.HEAD_OF_HOUSEHOLD:
            ceiling = tier.hoh_up_to
        else:
            ceiling = tier.other_up_to
        if agi <= Money(ceiling):
            return contributions * tier.rate
    return ZERO


# ---------------------------------------------------------------------------
# Orchestrator: the ordered credit cascade (spec §9.8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreditItem:
    id: str
    label: str
    amount: Money           # amount actually used
    refundable: bool
    lost_to_liability: Money = ZERO


@dataclass(frozen=True)
class CreditsResult:
    nonrefundable_used: Money
    refundable: Money
    items: tuple[CreditItem, ...]
    warnings: tuple[str, ...]


def compute_credits(inp: TaxInput, agi: Money, tax_liability: Money,
                    earned_income: Money, investment_income: Money,
                    fed: FederalData) -> CreditsResult:
    """Nonrefundable credits applied in order and clamped to remaining
    liability (residue reported); refundable credits applied after and may
    drive the balance negative."""
    items: list[CreditItem] = []
    warnings: list[str] = []
    remaining = tax_liability

    def apply_nonrefundable(id: str, label: str, amount: Money) -> None:
        nonlocal remaining
        if amount <= ZERO:
            return
        used = minm(amount, remaining)
        remaining -= used
        lost = amount - used
        if used > ZERO:  # zero-amount lines would clutter the trace
            items.append(CreditItem(id=id, label=label, amount=used,
                                    refundable=False, lost_to_liability=lost))
        if lost > ZERO:
            warnings.append(
                f"${lost.round_dollar().amount:,.0f} of {label} lost to the "
                "liability limit")

    # Nonrefundable cascade (statutory ordering, simplified)
    apply_nonrefundable("fed.credits.care", "child and dependent care credit",
                        dependent_care_credit(inp, agi, earned_income, fed))
    aotc_nonref, aotc_ref = aotc_credit(inp, agi, fed)
    apply_nonrefundable("fed.credits.aotc", "American Opportunity credit "
                        "(nonrefundable 60%)", aotc_nonref)
    apply_nonrefundable("fed.credits.llc", "Lifetime Learning credit",
                        llc_credit(inp, agi, fed))
    apply_nonrefundable("fed.credits.saver", "saver's credit",
                        savers_credit(inp, agi, fed))

    # CTC/ODC last so its refundable portion (ACTC) computes on the residue.
    ctc = child_tax_credit(inp, agi, remaining, earned_income, fed)
    if ctc.nonrefundable_used > ZERO:
        remaining -= ctc.nonrefundable_used
        items.append(CreditItem(
            id="fed.credits.ctc", label="child tax credit / ODC",
            amount=ctc.nonrefundable_used, refundable=False,
            lost_to_liability=(ctc.after_phaseout - ctc.nonrefundable_used
                               - ctc.refundable)))
    warnings.extend(ctc.warnings)

    # Refundable credits
    refundable = ZERO
    if aotc_ref > ZERO:
        items.append(CreditItem(id="fed.credits.aotc_refundable",
                                label="American Opportunity credit "
                                "(refundable 40%)",
                                amount=aotc_ref, refundable=True))
        refundable += aotc_ref
    if ctc.refundable > ZERO:
        items.append(CreditItem(id="fed.credits.actc",
                                label="additional child tax credit",
                                amount=ctc.refundable, refundable=True))
        refundable += ctc.refundable
    eitc_amount, eitc_warnings = earned_income_credit(
        inp, agi, earned_income, investment_income, fed)
    warnings.extend(eitc_warnings)
    if eitc_amount > ZERO:
        items.append(CreditItem(id="fed.credits.eitc",
                                label="earned income credit",
                                amount=eitc_amount, refundable=True))
        refundable += eitc_amount

    return CreditsResult(
        nonrefundable_used=tax_liability - remaining,
        refundable=refundable,
        items=tuple(items), warnings=tuple(warnings))
