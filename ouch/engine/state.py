"""State and local computation, driven entirely by data files (spec §9.9).

Three regimes (none / flat / progressive) are expressed in data; the same
bracket machinery serves both state and local files.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from ouch.engine.brackets import apply_brackets
from ouch.errors import DataSchemaError
from ouch.model.enums import FilingStatus, StartingPoint, StateRegime
from ouch.model.input import TaxInput
from ouch.model.money import Money, ZERO, maxm, minm
from ouch.model.result import LocalResult, StateResult
from ouch.taxdata.schema import (ExemptionCredits, LocalData, Modification,
                                 StateCredit, StateData)


@dataclass(frozen=True)
class FederalContext:
    """Federal figures a state computation may start from or modify."""
    total_income: Money
    agi: Money
    taxable_income: Money
    wages: Money
    taxable_social_security: Money
    itemized_total: Money
    itemized_salt_income: Money  # state/local income tax deducted federally
    deduction_taken: Money = ZERO     # Form 1040 line 12e (standard or itemized)
    qbi_deduction: Money = ZERO       # Form 1040 line 13b (2026; 13a for 2025)
    overtime_deduction: Money = ZERO  # Schedule 1-A Part III


def _resolve_source_field(field: str | None, inp: TaxInput,
                          ctx: FederalContext) -> Money:
    """Map a data-file `source_field` to a computed or profile value."""
    if field is None:
        return ZERO
    inv = inp.income.investment
    mapping = {
        "taxable_social_security": ctx.taxable_social_security,
        "tax_exempt_interest_out_of_state":
            Money(inv.tax_exempt_interest) - Money(inv.in_state_muni_interest),
        "treasury_interest": Money(inv.treasury_interest),
        "pension": Money(inp.income.retirement.pension),
        "itemized_salt_income": ctx.itemized_salt_income,
        "federal_deduction": ctx.deduction_taken,
        "federal_qbi_deduction": ctx.qbi_deduction,
        "federal_overtime_deduction": ctx.overtime_deduction,
    }
    if field not in mapping:
        raise DataSchemaError(
            f"unknown modification source_field '{field}' in state data file",
            hint="supported: " + ", ".join(sorted(mapping)),
        )
    return mapping[field]


def _apply_modification(mod: Modification, inp: TaxInput,
                        ctx: FederalContext) -> Money:
    status = inp.taxpayer.filing_status
    if mod.min_agi is not None and ctx.agi <= Money(mod.min_agi[status]):
        return ZERO
    value = _resolve_source_field(mod.source_field, inp, ctx)
    if mod.less is not None:
        value -= Money(mod.less[status])
    if mod.min_age is not None:
        age = inp.age_at_year_end(inp.taxpayer.birth_date)
        if age is None or Decimal(age) < mod.min_age:
            return ZERO
    if mod.cap is not None:
        value = minm(value, Money(mod.cap))
    return maxm(value, ZERO)


def _starting_income(point: StartingPoint, ctx: FederalContext) -> Money:
    return {
        StartingPoint.FEDERAL_AGI: ctx.agi,
        StartingPoint.FEDERAL_TAXABLE: ctx.taxable_income,
        StartingPoint.FEDERAL_WAGES: ctx.wages,
        StartingPoint.INDEPENDENT: ctx.agi,  # v1: approximate independents from AGI
        StartingPoint.STATE_TAXABLE: ctx.taxable_income,
    }[point]


def _credits(credits: list[StateCredit], inp: TaxInput, ctx: FederalContext,
             taxable: Money) -> Money:
    """Credits declared in the data file. A credit is a fixed `amount`, an
    `amount_by_status`, or a `schedule` applied to `taxable`, and is lost
    entirely above `max_income`. pct_of_federal credits (EITC, care) need
    the federal counterpart, which isn't computed for states yet: skipped.
    Subtracted from the tax, not below zero."""
    status = inp.taxpayer.filing_status
    total = ZERO
    for credit in credits:
        if credit.max_income is not None:
            income = ctx.agi
            if credit.income == "agi_less_ira":
                income -= Money(inp.income.retirement.ira_distributions)
            if income > Money(credit.max_income):
                continue
        if credit.amount is not None:
            total += Money(credit.amount)
        if credit.amount_by_status is not None:
            total += Money(credit.amount_by_status[status])
        if credit.schedule is not None:
            total += apply_brackets(maxm(taxable, ZERO), credit.schedule[status])
    return total


def exemption_credits(inp: TaxInput, agi: Money, ec: ExemptionCredits) -> Money:
    """California Form 540 lines 7–10 and the AGI Limitation Worksheet:
    each credit loses `reduction_per_step` per `step` (rounded up) of AGI
    over the threshold; personal/senior/blind and dependent credits are
    each floored at zero as groups (worksheet lines i and m)."""
    status = inp.taxpayer.filing_status
    joint = status in (FilingStatus.MARRIED_FILING_JOINTLY,
                       FilingStatus.QUALIFYING_SURVIVING_SPOUSE)
    people = [inp.taxpayer]
    if status == FilingStatus.MARRIED_FILING_JOINTLY and inp.spouse is not None:
        people.append(inp.spouse)
    seniors = sum(1 for p in people if inp.reaches_age_by_year_end(p.birth_date, 65))
    blind = sum(1 for p in people if p.blind)
    n_filer = (2 if joint else 1) + seniors + blind
    filer = (Money(ec.personal) * (2 if joint else 1) + Money(ec.senior) * seniors
             + Money(ec.blind) * blind)
    n_dep = len(inp.dependents)
    dependent = Money(ec.dependent) * n_dep
    if ec.phaseout is not None:
        excess = agi - Money(ec.phaseout.threshold[status])
        if excess > ZERO:
            step = (ec.phaseout.step_mfs if status == FilingStatus.MARRIED_FILING_SEPARATELY
                    else ec.phaseout.step)
            steps = math.ceil(excess.ratio(Money(step)))
            cut = Money(ec.phaseout.reduction_per_step) * steps
            filer = maxm(ZERO, filer - cut * n_filer)
            dependent = maxm(ZERO, dependent - cut * n_dep)
    return filer + dependent


def compute_state(inp: TaxInput, ctx: FederalContext,
                  data: StateData) -> StateResult:
    code = data.meta.jurisdiction
    status = inp.taxpayer.filing_status

    if data.regime == StateRegime.NONE:
        return StateResult(code=code, starting_income=ZERO, agi=ZERO,
                           deduction=ZERO, exemptions=ZERO, taxable=ZERO,
                           tax=ZERO, credits=ZERO)

    starting = _starting_income(data.starting_point, ctx)
    additions = sum((_apply_modification(m, inp, ctx)
                     for m in data.modifications.additions), ZERO)
    subtractions = sum((_apply_modification(m, inp, ctx)
                        for m in data.modifications.subtractions), ZERO)
    state_agi = starting + additions - subtractions

    deduction = ZERO
    if data.standard_deduction is not None:
        deduction = Money(data.standard_deduction[status])
    if data.itemized.allowed:
        state_itemized = ctx.itemized_total
        if not data.itemized.salt_deductible:
            state_itemized -= ctx.itemized_salt_income
        deduction = maxm(deduction, maxm(state_itemized, ZERO))

    exemptions = (Money(data.personal_exemption.per_dependent) * len(inp.dependents)
                  + Money(data.personal_exemption.per_filer))

    taxable = maxm(ZERO, state_agi - deduction - exemptions)

    if data.regime == StateRegime.FLAT:
        tax = taxable * data.rate
    else:
        if data.brackets is None or status not in data.brackets:
            raise DataSchemaError(
                f"state {code}: no brackets for filing status '{status}'")
        tax = apply_brackets(taxable, data.brackets[status])

    credits = _credits(data.credits, inp, ctx, taxable)
    if data.exemption_credits is not None:
        credits += exemption_credits(inp, ctx.agi, data.exemption_credits)

    tax = maxm(ZERO, tax - credits)
    return StateResult(code=code, starting_income=starting, agi=state_agi,
                       deduction=deduction, exemptions=exemptions,
                       taxable=taxable, tax=tax, credits=credits)


def compute_local(inp: TaxInput, ctx: FederalContext, state: StateResult | None,
                  data: LocalData) -> LocalResult:
    name = data.meta.jurisdiction
    status = inp.taxpayer.filing_status

    if data.regime == StateRegime.NONE:
        return LocalResult(name=name, taxable=ZERO, tax=ZERO, credits=ZERO)

    if data.starting_point == StartingPoint.STATE_TAXABLE and state is not None:
        base = state.taxable
    else:
        base = _starting_income(data.starting_point, ctx)
    base = maxm(base, ZERO)

    if data.regime == StateRegime.FLAT:
        tax = base * data.rate
    else:
        if data.brackets is None or status not in data.brackets:
            raise DataSchemaError(
                f"locality {name}: no brackets for filing status '{status}'")
        tax = apply_brackets(base, data.brackets[status])

    credits = _credits(data.credits, inp, ctx, base)
    tax = maxm(ZERO, tax - credits)
    return LocalResult(name=name, taxable=base, tax=tax, credits=credits)
