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

    return FederalTax(ordinary=ordinary_tax, preferential=pref_tax,
                      special=special_tax)


def amt_additional(taxable_income: Money, pref_income: Money,
                   deduction_mode: str, standard_amount: Money,
                   salt_deducted: Money, status: FilingStatus,
                   amt: Amt, pref_brackets: list[Bracket],
                   regular_income_tax: Money) -> Money:
    """Simplified parallel AMT computation (fidelity: approximate).

    AMTI ≈ taxable income plus the standard deduction (if taken) or the SALT
    deduction (if itemized) — the two most common preference addbacks. ISO
    bargain elements and other adjustments are not modeled in v1.
    """
    addback = standard_amount if deduction_mode == DeductionMode.STANDARD else salt_deducted
    amti = taxable_income + addback
    exemption = Money(amt.exemption[status])
    threshold = Money(amt.phaseout_threshold[status])
    exemption = maxm(ZERO, exemption - maxm(ZERO, amti - threshold) * amt.phaseout_rate)
    base = maxm(ZERO, amti - exemption)

    # Preferential income keeps its 0/15/20 rates under AMT.
    pref_in_base = minm(maxm(pref_income, ZERO), base)
    ord_base = base - pref_in_base
    tmt = apply_brackets(ord_base, amt.brackets)
    floor = ord_base
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
            floor += room

    return maxm(ZERO, tmt - regular_income_tax)
