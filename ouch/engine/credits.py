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
