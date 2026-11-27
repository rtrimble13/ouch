"""Federal income tax: ordinary + preferential stacking (spec §9.4) and AMT.

Preferential income is NOT taxed at a flat rate; it sits on top of ordinary
income, and ordinary income is taxed as if the preferential income did not
exist.
"""

from __future__ import annotations

from dataclasses import dataclass

from ouch.engine.brackets import apply_brackets
from ouch.model.enums import DeductionMode, FilingStatus
from ouch.model.money import Money, ZERO, maxm, minm
from ouch.taxdata.schema import Amt, Bracket, SpecialRateGroups


@dataclass(frozen=True)
class FederalTax:
    ordinary: Money
    preferential: Money
    special: Money  # 25% / 28% groups

    @property
    def total(self) -> Money:
        return self.ordinary + self.preferential + self.special


def federal_income_tax(taxable_income: Money, pref_income: Money,
                       brackets: list[Bracket], pref_brackets: list[Bracket],
                       unrecap_1250: Money = ZERO, collectibles: Money = ZERO,
                       special_rates: SpecialRateGroups | None = None) -> FederalTax:
    """
    taxable_income : total taxable income (ordinary + preferential + special)
    pref_income    : qualified dividends + net LTCG in the 0/15/20 stack (>= 0)
    """
    special_total = unrecap_1250 + collectibles
    ordinary_taxable = maxm(taxable_income - pref_income - special_total, ZERO)

    # 1. Ordinary income taxed through ordinary brackets, alone.
    ordinary_tax = apply_brackets(ordinary_taxable, brackets)

    # 2. Preferential income fills the preferential brackets, but starting
    #    from the top of ordinary income — NOT from zero.
    pref_tax = ZERO
    remaining = minm(pref_income, maxm(taxable_income - ordinary_taxable, ZERO))
    floor = ordinary_taxable
    for band in pref_brackets:  # ascending
        if remaining <= ZERO:
            break
        band_top = None if band.up_to is None else Money(band.up_to)
        if band_top is not None and band_top <= floor:
            continue  # band fully consumed by ordinary income
        room = remaining if band_top is None else minm(remaining, band_top - floor)
        if room > ZERO:
            pref_tax += room * band.rate
            remaining -= room
            floor += room

    # 3. 25% and 28% groups are separate stacks; each is taxed at the LESSER
    #    of its statutory rate and the rate that would apply if it were
    #    ordinary income.
    special_tax = ZERO
    if special_rates is not None and special_total > ZERO:
        base_tax = apply_brackets(ordinary_taxable, brackets)
        stack = ordinary_taxable
        for amount, rate in ((unrecap_1250, special_rates.unrecaptured_1250),
                             (collectibles, special_rates.collectibles)):
            if amount <= ZERO:
                continue
            as_ordinary = apply_brackets(stack + amount, brackets) - base_tax
            special_tax += minm(amount * rate, as_ordinary)
            stack += amount
            base_tax = apply_brackets(stack, brackets)

    # 4. QDCGT worksheet line 25 (Schedule D Tax Worksheet line 47): the tax
    #    is the smaller of the worksheet result and the tax on all taxable
    #    income as ordinary income. Taxing everything as ordinary wins where
    #    the gain sits above the 0% breakpoint but still inside the 12%
    #    bracket (single: $49,450 to $50,400 in 2026).
    if pref_income + special_total > ZERO:
        excess = ordinary_tax + pref_tax + special_tax - apply_brackets(
            taxable_income, brackets)
        if excess > ZERO:
            cut = minm(excess, pref_tax)
            pref_tax -= cut
            special_tax -= excess - cut

    return FederalTax(ordinary=ordinary_tax, preferential=pref_tax,
                      special=special_tax)


def amt_additional(taxable_income: Money, pref_income: Money,
                   deduction_mode: str, standard_amount: Money,
                   salt_deducted: Money, status: FilingStatus,
                   amt: Amt, pref_brackets: list[Bracket],
                   regular_income_tax: Money, *,
                   regular_ordinary: Money | None = None,
                   other_addbacks: Money = ZERO) -> tuple[Money, Money]:
    """Simplified parallel AMT computation (fidelity: approximate).

    Returns (additional AMT owed, tentative minimum tax). The TMT is needed
    for the AMT credit carryforward: prior-year AMT becomes a credit usable
    only to the extent regular tax exceeds TMT (Form 8801).

    AMTI ≈ taxable income plus the standard deduction (if taken) or the SALT
    deduction (if itemized) — the two most common preference addbacks — plus
    `other_addbacks` (the Schedule 1-A senior deduction: Form 6251 line 1a
    subtracts Schedule 1-A line 43 from Form 1040 line 14, so it isn't
    allowed). ISO bargain elements and other adjustments are not modeled.

    `regular_ordinary` is the regular-tax ordinary income (QDCGT worksheet
    line 5). Form 6251 Part III measures the 0% and 15% breakpoints from it
    (lines 20 and 27), not from the AMT ordinary base. It defaults to
    taxable income less preferential income.
    """
    addback = standard_amount if deduction_mode == DeductionMode.STANDARD else salt_deducted
    amti = taxable_income + addback + other_addbacks
    exemption = Money(amt.exemption[status])
    threshold = Money(amt.phaseout_threshold[status])
    exemption = maxm(ZERO, exemption - maxm(ZERO, amti - threshold) * amt.phaseout_rate)
    base = maxm(ZERO, amti - exemption)

    # Form 6251 Part III. Preferential income keeps its 0/15/20 rates.
    brackets = amt.brackets_for(status)
    pref_in_base = minm(maxm(pref_income, ZERO), base)       # line 22
    if pref_in_base <= ZERO:
        tmt = apply_brackets(base, brackets)
        return maxm(ZERO, tmt - regular_income_tax), tmt
    ord_base = base - pref_in_base                            # line 17
    tmt = apply_brackets(ord_base, brackets)                  # line 18
    if regular_ordinary is None:
        regular_ordinary = maxm(ZERO, taxable_income - pref_income)
    # Each preferential band's room runs from max(band start, regular-tax
    # ordinary income) to its top: lines 19–23 (0%), 25–30 (15%), 33 (20%).
    floor = regular_ordinary
    remaining = pref_in_base
    for band in pref_brackets:
        if remaining <= ZERO:
            break
        band_top = None if band.up_to is None else Money(band.up_to)
        if band_top is not None and band_top <= floor:
            continue
        room = remaining if band_top is None else minm(remaining, band_top - floor)
        if room > ZERO:
            tmt += room * band.rate
            remaining -= room
            floor = floor + room if band_top is None else maxm(floor, band_top)
    # Line 40: the smaller of that and the whole base at AMT rates (line 39).
    tmt = minm(tmt, apply_brackets(base, brackets))

    return maxm(ZERO, tmt - regular_income_tax), tmt
