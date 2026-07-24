"""Pipeline orchestration — the canonical ordering (spec §9.1).

Pure: `TaxInput × ResolvedData -> TaxResult`. No I/O, no clock, no globals,
no mutation of inputs. Invariants are asserted between steps (§15.3) and
raise exit-code-9 errors rather than emitting a wrong number.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ouch.engine import setax
from ouch.engine.credits import child_tax_credit
from ouch.engine.deductions import (ItemizedResult, itemized_deduction,
                                    qbi_deduction, standard_deduction)
from ouch.engine.federal import amt_additional, federal_income_tax
from ouch.engine.income import net_capital
from ouch.engine.payments import project_payments, safe_harbor
from ouch.engine.state import FederalContext, compute_local, compute_state
from ouch.errors import ConvergenceError, InvariantError
from ouch.model.enums import DeductionMode, Fidelity, FilingStatus
from ouch.model.input import TaxInput
from ouch.model.money import Money, ZERO, maxm, minm
from ouch.model.result import (ComputationTrace, TaxResult, TraceBuilder)
from ouch.taxdata.schema import FederalData, LocalData, StateData

MAX_SALT_ITERATIONS = 6
SALT_CONVERGENCE = Money(1)

# States known to levy local income taxes — used only for a warning when the
# profile has no locality set (a zero local tax there is almost surely wrong).
LOCAL_TAX_STATES = {"NY", "PA", "OH", "MD", "MI", "KY", "IN", "MO", "AL", "DE", "WV"}


@dataclass(frozen=True)
class ResolvedData:
    federal: FederalData
    state: StateData | None = None
    local: LocalData | None = None


@dataclass(frozen=True)
class _FederalPass:
    tb: TraceBuilder
    total_income: Money
    agi: Money
    adjustments_total: Money
    deduction: Money
    deduction_mode: str
    itemized: ItemizedResult
    standard_amount: Money
    qbi: Money
    taxable_income: Money
    tax_ordinary: Money
    tax_preferential: Money
    tax_special: Money
    amt_add: Money
    se_tax: Money
    se_deduction: Money
    addl_medicare: Money
    niit_tax: Money
    credits_nonrefundable: Money
    credits_refundable: Money
    federal_total: Money
    wages: Money
    taxable_ss: Money
    excluded_income: Money
    pref_income: Money
    earned_income: Money
    warnings: tuple[str, ...]


def _mfs_or_single_offset(inp: TaxInput, fed: FederalData) -> Money:
    if inp.taxpayer.filing_status == FilingStatus.MARRIED_FILING_SEPARATELY:
        return Money(fed.capital_loss.mfs_offset)
    return Money(fed.capital_loss.annual_ordinary_offset)


def _taxable_social_security(agi_ex_ss: Money, tax_exempt: Money, gross: Money,
                             status: FilingStatus, fed: FederalData) -> Money:
    """Tiered inclusion (spec §9.3). The provisional-income base here does not
    itself depend on taxable SS, so the fixed point is reached in one step;
    the guard loop is retained per spec in case future adjustments couple it.
    """
    if gross <= ZERO:
        return ZERO
    t = fed.social_security_taxability
    base = Money(t.base_amount[status])
    adj = Money(t.adjusted_base[status])
    half = Decimal("0.5")
    ss_taxable = ZERO
    for _ in range(8):
        provisional = agi_ex_ss + tax_exempt + gross * half
        if provisional <= base:
            new = ZERO
        elif provisional <= adj:
            new = minm((provisional - base) * half, gross * half)
        else:
            lower = minm((adj - base) * half, gross * half)
            new = minm((provisional - adj) * Decimal("0.85") + lower,
                       gross * t.max_inclusion)
        if abs(new - ss_taxable) < Money("0.01"):
            return new
        ss_taxable = new
    raise ConvergenceError("taxable Social Security computation failed to converge")


def _compute_federal(inp: TaxInput, fed: FederalData,
                     salt_estimate: Money) -> _FederalPass:
    tb = TraceBuilder()
    status = inp.taxpayer.filing_status
    warnings: list[str] = []
    year = inp.tax_year
    data_ref = f"taxdata.federal.{year}"

    # 1. Classify and aggregate income by rate group -------------------------
    w = inp.income.wages
    inv = inp.income.investment
    biz = inp.income.business
    ret = inp.income.retirement
    oth = inp.income.other

    wages = Money(w.taxpayer_w2) + Money(w.spouse_w2)
    ss_wages = Money(w.taxpayer_ss_wages) + Money(w.spouse_ss_wages)
    if ss_wages == ZERO:
        ss_wages = wages  # box 3 defaults to box 1 when not supplied
    se_net = Money(biz.schedule_c_net)

    netting = net_capital(
        Money(inv.short_term_gains), Money(inv.long_term_gains),
        Money(inv.capital_loss_carryforward),
        Money(inv.section_1250_gain), Money(inv.collectibles_gain),
        _mfs_or_single_offset(inp, fed),
    )

    qualified_div = Money(inv.qualified_dividends)
    nonqualified_div = Money(inv.ordinary_dividends) - qualified_div
    interest = Money(inv.interest) + Money(inv.treasury_interest)
    pref_income = qualified_div + netting.preferential_gain

    tb.add("fed.income.wages", "Wages", wages, jurisdiction="federal",
           rule="sum of W-2 box 1 wages", form_ref="1040 line 1a")
    tb.add("fed.income.capital", "Net capital gain/(loss) in income",
           netting.ordinary_component + pref_income - qualified_div
           + netting.unrecap_1250 + netting.collectibles,
           jurisdiction="federal", form_ref="Schedule D",
           rule="statutory netting: ST vs ST, LT vs LT, cross-net, "
                "ordinary offset limited",
           authority="IRC §1211, §1212",
           fidelity=Fidelity.APPROXIMATE if inv.capital_loss_carryforward > 0
           else Fidelity.EXACT)
    if netting.carryforward_st + netting.carryforward_lt > ZERO:
        warnings.append(
            f"capital loss carryforward to {year + 1}: "
            f"${(netting.carryforward_st + netting.carryforward_lt).round_dollar().amount:,.0f} "
            "(character preserved)")

    # 2. Self-employment tax → SE deduction ----------------------------------
    se = setax.self_employment_tax(se_net, ss_wages, fed)
    tb.add("fed.setax", "Self-employment tax", se.se_tax, jurisdiction="federal",
           rule="92.35% of SE net income; SS portion limited to the wage base "
                "remaining after W-2 social security wages",
           form_ref="Schedule SE", authority="IRC §1401",
           inputs=(f"{data_ref}",))

    # 3. Above-the-line adjustments (incl. ½ SE tax, SE health) --------------
    adj = inp.adjustments
    se_health = minm(Money(biz.se_health_premiums), maxm(se_net, ZERO))
    adjustments_total = (se.se_deduction + se_health + Money(adj.traditional_ira)
                         + Money(adj.hsa) + Money(adj.student_loan_interest)
                         + Money(adj.educator_expenses) + Money(adj.sep_solo401k)
                         + Money(adj.alimony_paid)
                         + Money(adj.early_withdrawal_penalty))
    tb.add("fed.adjustments", "Above-the-line adjustments", adjustments_total,
           jurisdiction="federal", rule="½ SE tax + SE health (limited to SE "
           "income) + IRA/HSA/retirement and other adjustments",
           form_ref="Schedule 1 Part II", authority="IRC §62",
           inputs=("fed.setax",),
           fidelity=Fidelity.APPROXIMATE if adj.student_loan_interest > 0
           else Fidelity.EXACT,
           warnings=("student loan interest phase-out not modeled",)
           if adj.student_loan_interest > 0 else ())

    # 4. Taxable Social Security (iterative) ---------------------------------
    ordinary_unearned_ex_ss = (
        interest + nonqualified_div + Money(ret.pension)
        + Money(ret.ira_distributions) + Money(ret.roth_conversion)
        + Money(oth.rental_net) + Money(oth.k1_ordinary)
        + Money(oth.unemployment) + Money(oth.other_income)
        + netting.ordinary_component)
    income_ex_ss = (wages + maxm(se_net, ZERO) + ordinary_unearned_ex_ss
                    + pref_income + netting.unrecap_1250 + netting.collectibles)
    agi_ex_ss = income_ex_ss - adjustments_total
    taxable_ss = _taxable_social_security(
        agi_ex_ss, Money(inv.tax_exempt_interest),
        Money(ret.social_security_gross), status, fed)
    if ret.taxable_social_security > 0:
        taxable_ss = Money(ret.taxable_social_security)  # explicit override
    if taxable_ss > ZERO:
        tb.add("fed.income.taxable_ss", "Taxable Social Security", taxable_ss,
               jurisdiction="federal", rule="tiered inclusion of benefits based "
               "on provisional income", authority="IRC §86",
               form_ref="1040 line 6b", inputs=("fed.adjustments",))

    # 5. Adjusted Gross Income ----------------------------------------------
    total_income = income_ex_ss + taxable_ss
    agi = total_income - adjustments_total
    tb.add("fed.income.total", "Total income", total_income,
           jurisdiction="federal", rule="sum of all income included in gross "
           "income, by rate group", form_ref="1040 line 9", authority="IRC §61",
           inputs=("fed.income.wages", "fed.income.capital"))
    tb.add("fed.agi", "Adjusted gross income", agi, jurisdiction="federal",
           rule="total income less above-the-line adjustments",
           form_ref="1040 line 11", authority="IRC §62",
           inputs=("fed.income.total", "fed.adjustments"))
    if agi > total_income:
        raise InvariantError("AGI exceeds total income")

    # 6. Deduction: standard vs. itemized ------------------------------------
    std = standard_deduction(inp, fed)
    itemized = itemized_deduction(inp, agi, salt_estimate,
                                  interest + nonqualified_div, fed)
    mode_setting = inp.deductions.mode
    if mode_setting == DeductionMode.STANDARD:
        mode, deduction = "standard", std
    elif mode_setting == DeductionMode.ITEMIZED:
        mode, deduction = "itemized", itemized.total
    elif itemized.total > std:
        mode, deduction = "itemized", itemized.total
    else:
        mode, deduction = "standard", std
    crossover = itemized.total - std
    tb.add("fed.deduction", f"Deduction ({mode})", deduction,
           jurisdiction="federal",
           rule=(f"max(standard ${std.round_dollar().amount:,.0f}, itemized "
                 f"${itemized.total.round_dollar().amount:,.0f})"
                 if mode_setting == DeductionMode.AUTO
                 else f"forced {mode}"),
           form_ref="1040 line 12", authority="IRC §63",
           inputs=("fed.agi",),
           warnings=((f"itemizing trails the standard deduction by "
                      f"${(-crossover).round_dollar().amount:,.0f}",)
                     if mode == "standard" and itemized.total > ZERO else ()))

    # 7. QBI deduction -------------------------------------------------------
    taxable_before_qbi = maxm(ZERO, agi - deduction)
    qbi = qbi_deduction(inp, taxable_before_qbi, pref_income,
                        se.se_deduction, se_health, fed)
    if qbi.deduction > ZERO:
        tb.add("fed.qbi", "QBI deduction", qbi.deduction,
               jurisdiction="federal",
               rule="20% of qualified business income after allocable "
               "adjustments, limited to 20% of taxable income less net "
               "capital gain; wage/UBIA limit above the threshold",
               form_ref="Form 8995", authority="IRC §199A",
               inputs=("fed.deduction", "fed.agi"),
               fidelity=Fidelity.APPROXIMATE)

    # 8. Taxable income ------------------------------------------------------
    taxable_income = maxm(ZERO, taxable_before_qbi - qbi.deduction)
    tb.add("fed.taxable", "Taxable income", taxable_income,
           jurisdiction="federal", rule="AGI less deduction less QBI",
           form_ref="1040 line 15", authority="IRC §63",
           inputs=("fed.agi", "fed.deduction")
           + (("fed.qbi",) if qbi.deduction > ZERO else ()))
    if taxable_income < ZERO:
        raise InvariantError("taxable income is negative")

    # 9. Federal tax: preferential stacking ----------------------------------
    tax = federal_income_tax(
        taxable_income, pref_income,
        fed.ordinary_brackets[status], fed.preferential_brackets[status],
        unrecap_1250=netting.unrecap_1250, collectibles=netting.collectibles,
        special_rates=fed.special_rate_groups)
    max_pref_rate = max(b.rate for b in fed.preferential_brackets[status])
    if tax.preferential > pref_income * max_pref_rate + Money("0.01"):
        raise InvariantError("preferential tax exceeds maximum preferential rate")
    tb.add("fed.tax.ordinary", "Ordinary income tax", tax.ordinary,
           jurisdiction="federal",
           rule="progressive brackets applied to ordinary taxable income, "
                "computed as if preferential income did not exist",
           form_ref="1040 line 16", authority="IRC §1(j)",
           inputs=("fed.taxable", data_ref))
    tb.add("fed.tax.preferential", "Tax on qualified dividends and LTCG",
           tax.preferential, jurisdiction="federal",
           rule="preferential income stacks on top of ordinary income and "
                "fills the 0/15/20 brackets from that floor",
           form_ref="QD & CG Tax Worksheet", authority="IRC §1(h)",
           inputs=("fed.taxable", data_ref))
    if tax.special > ZERO:
        tb.add("fed.tax.special", "Tax on 25%/28% rate groups", tax.special,
               jurisdiction="federal",
               rule="unrecaptured §1250 and collectibles taxed at the lesser "
                    "of the statutory rate and the ordinary rate",
               authority="IRC §1(h)", inputs=("fed.taxable", data_ref),
               fidelity=Fidelity.APPROXIMATE)

    regular_tax = tax.total

    # 10. AMT parallel computation -------------------------------------------
    amt_add = amt_additional(
        taxable_income, pref_income, mode, std,
        itemized.salt if mode == "itemized" else ZERO,
        status, fed.amt, fed.preferential_brackets[status], regular_tax)
    if amt_add > ZERO:
        tb.add("fed.amt.additional", "Alternative minimum tax (excess)",
               amt_add, jurisdiction="federal",
               rule="tentative minimum tax over regular tax; AMTI approximated "
                    "as taxable income plus standard/SALT addback",
               form_ref="Form 6251", authority="IRC §55",
               inputs=("fed.taxable",), fidelity=Fidelity.APPROXIMATE)
    elif regular_tax > ZERO:
        # AMT-proximity warning (§15.4)
        tentative = regular_tax - amt_add
        # recompute closeness cheaply: flag when within 10%
        probe = amt_additional(
            taxable_income, pref_income, mode, std,
            itemized.salt if mode == "itemized" else ZERO,
            status, fed.amt, fed.preferential_brackets[status],
            regular_tax * Decimal("0.9"))
        if probe > ZERO:
            warnings.append("AMT within 10% of regular tax — a small change "
                            "could trigger it")

    # 11. Additional Medicare tax; NIIT --------------------------------------
    addl_med = setax.additional_medicare(ss_wages, se.se_base, status, fed)
    if addl_med > ZERO:
        tb.add("fed.medicare.additional", "Additional Medicare tax", addl_med,
               jurisdiction="federal",
               rule="0.9% of Medicare wages + SE income above the threshold; "
                    "employers withhold only above $200k per job",
               form_ref="Form 8959", authority="IRC §3101(b)(2)",
               inputs=(data_ref,))

    # interest + all dividends + net capital gain included in income
    # + passive rents (spec §9.7)
    nii = (interest + Money(inv.ordinary_dividends)
           + netting.ordinary_component + netting.preferential_gain
           + netting.unrecap_1250 + netting.collectibles
           + Money(oth.rental_net))
    niit_tax = setax.niit(nii, agi, status, fed)
    if niit_tax > ZERO:
        tb.add("fed.niit", "Net investment income tax", niit_tax,
               jurisdiction="federal",
               rule="3.8% of the lesser of net investment income and MAGI "
                    "over the threshold",
               form_ref="Form 8960", authority="IRC §1411",
               inputs=("fed.agi", data_ref))

    # 12–13. Credits ---------------------------------------------------------
    earned_income = wages + maxm(se_net, ZERO)
    income_tax_liability = regular_tax + amt_add
    ctc = child_tax_credit(inp, agi, income_tax_liability, earned_income, fed)
    if ctc.nonrefundable_used > income_tax_liability:
        raise InvariantError("nonrefundable credits exceed tax liability")
    if ctc.after_phaseout > ZERO:
        tb.add("fed.credits.ctc", "Child tax credit / credit for other "
               "dependents", ctc.after_phaseout, jurisdiction="federal",
               rule=f"{ctc.qualifying_children} qualifying children × "
                    f"${fed.credits.child_tax_credit.amount_per_child:,.0f} + "
                    f"{ctc.other_dependents} other dependents × "
                    f"${fed.credits.other_dependent_credit.amount:,.0f}, "
                    "phased out $50 per $1,000 of AGI over the threshold",
               form_ref="Schedule 8812", authority="IRC §24",
               inputs=("fed.agi", data_ref))
    warnings.extend(ctc.warnings)

    # 14. Federal total tax --------------------------------------------------
    federal_total = (income_tax_liability + se.se_tax + addl_med + niit_tax
                     - ctc.nonrefundable_used - ctc.refundable)
    tb.add("fed.tax.total", "Federal total tax", federal_total,
           jurisdiction="federal",
           rule="income tax + AMT + SE tax + Additional Medicare + NIIT − credits",
           form_ref="1040 line 24",
           inputs=tuple(i for i in (
               "fed.tax.ordinary", "fed.tax.preferential",
               "fed.tax.special" if tax.special > ZERO else None,
               "fed.amt.additional" if amt_add > ZERO else None,
               "fed.setax",
               "fed.medicare.additional" if addl_med > ZERO else None,
               "fed.niit" if niit_tax > ZERO else None,
               "fed.credits.ctc" if ctc.after_phaseout > ZERO else None,
           ) if i))

    excluded = (Money(inv.tax_exempt_interest)
                + maxm(ZERO, Money(ret.social_security_gross) - taxable_ss))

    return _FederalPass(
        tb=tb, total_income=total_income, agi=agi,
        adjustments_total=adjustments_total, deduction=deduction,
        deduction_mode=mode, itemized=itemized, standard_amount=std,
        qbi=qbi.deduction, taxable_income=taxable_income,
        tax_ordinary=tax.ordinary, tax_preferential=tax.preferential,
        tax_special=tax.special, amt_add=amt_add,
        se_tax=se.se_tax, se_deduction=se.se_deduction,
        addl_medicare=addl_med, niit_tax=niit_tax,
        credits_nonrefundable=ctc.nonrefundable_used,
        credits_refundable=ctc.refundable, federal_total=federal_total,
        wages=wages, taxable_ss=taxable_ss, excluded_income=excluded,
        pref_income=pref_income, earned_income=earned_income,
        warnings=tuple(warnings),
    )


def _rate(numer: Money, denom: Money) -> Decimal:
    if denom <= ZERO:
        return Decimal(0)
    return numer.ratio(denom).quantize(Decimal("0.000001"))


def run(inp: TaxInput, data: ResolvedData, *,
        compute_marginals: bool = True) -> TaxResult:
    fed = data.federal
    warnings: list[str] = []

    # Steps 1–14 with the state/local circular dependency resolved by
    # fixed-point iteration (§9.9): federal itemized SALT ↔ state liability.
    w = inp.payments.withholding
    salt_estimate = Money(w.state_ytd) + Money(w.local_ytd)  # initial guess
    fp = None
    state_res = None
    local_res = None
    converged = data.state is None
    for _ in range(MAX_SALT_ITERATIONS):
        fp = _compute_federal(inp, fed, salt_estimate)
        ctx = FederalContext(
            total_income=fp.total_income, agi=fp.agi,
            taxable_income=fp.taxable_income, wages=fp.wages,
            taxable_social_security=fp.taxable_ss,
            itemized_total=fp.itemized.total,
            itemized_salt_income=fp.itemized.salt_income_component,
        )
        if data.state is None:
            break
        state_res = compute_state(inp, ctx, data.state)
        local_res = (compute_local(inp, ctx, state_res, data.local)
                     if data.local is not None else None)
        new_estimate = state_res.tax + (local_res.tax if local_res else ZERO)
        # When the user supplied the SALT figure, or the deduction is standard,
        # or the SALT cap binds, the loop is already settled — short-circuit.
        if (inp.deductions.itemized.state_local_income_tax > 0
                or fp.deduction_mode == "standard"
                or fp.itemized.salt_capped
                or abs(new_estimate - salt_estimate) < SALT_CONVERGENCE):
            converged = True
            break
        salt_estimate = new_estimate
    if not converged:
        raise ConvergenceError(
            "state/federal SALT iteration failed to converge after "
            f"{MAX_SALT_ITERATIONS} iterations")
    assert fp is not None
    tb = fp.tb
    warnings.extend(fp.warnings)

    # 15–16. State and local trace lines -------------------------------------
    if state_res is not None and data.state is not None:
        code = state_res.code.lower()
        if data.state.regime.value == "none":
            tb.add(f"{code}.tax", f"{state_res.code} income tax", ZERO,
                   jurisdiction=state_res.code,
                   rule=f"{state_res.code} has no personal income tax")
        else:
            tb.add(f"{code}.agi", f"{state_res.code} AGI", state_res.agi,
                   jurisdiction=state_res.code,
                   rule=f"{data.state.starting_point.value} + additions − "
                        "subtractions", inputs=("fed.agi",))
            tb.add(f"{code}.taxable", f"{state_res.code} taxable income",
                   state_res.taxable, jurisdiction=state_res.code,
                   rule="state AGI less deduction and exemptions",
                   inputs=(f"{code}.agi",))
            tb.add(f"{code}.tax", f"{state_res.code} income tax", state_res.tax,
                   jurisdiction=state_res.code,
                   rule=f"{data.state.regime.value} rate schedule less credits",
                   inputs=(f"{code}.taxable",))
    if local_res is not None:
        name = local_res.name.lower()
        tb.add(f"{name}.tax", f"{local_res.name} income tax", local_res.tax,
               jurisdiction=local_res.name,
               rule="local rate schedule applied to its starting income",
               inputs=(f"{state_res.code.lower()}.taxable",)
               if state_res is not None and state_res.taxable > ZERO else ())

    # 17. Payments, safe harbor, balance due ---------------------------------
    payments = project_payments(inp)
    sh = safe_harbor(inp, fp.federal_total, payments.federal, fed)
    state_tax = state_res.tax if state_res else ZERO
    local_tax = local_res.tax if local_res else ZERO
    total_tax = fp.federal_total + state_tax + local_tax
    if abs(total_tax - (fp.federal_total + state_tax + local_tax)) > ZERO:
        raise InvariantError("jurisdiction taxes do not sum to total")
    balance = total_tax - payments.total
    tb.add("total.tax", "Total tax, all jurisdictions", total_tax,
           jurisdiction="all",
           rule="federal + state + local",
           inputs=tuple(i for i in (
               "fed.tax.total",
               f"{state_res.code.lower()}.tax" if state_res else None,
               f"{local_res.name.lower()}.tax" if local_res else None) if i))
    tb.add("total.payments", "Withholding and estimated payments projected "
           "through year end", payments.total, jurisdiction="all",
           rule="YTD withholding + per-period × periods remaining + estimates")
    tb.add("total.balance", "Projected balance due / (refund)", balance,
           jurisdiction="all", rule="total tax less total payments",
           inputs=("total.tax", "total.payments"))

    # Warnings (§15.4) -------------------------------------------------------
    if not fed.meta.verified:
        warnings.append(f"Tax data for {inp.tax_year} is unverified (projected)")
    if data.state is not None and not data.state.meta.verified:
        warnings.append(f"State tax data ({data.state.meta.jurisdiction} "
                        f"{inp.tax_year}) is unverified")
    if (inp.taxpayer.state.upper() in LOCAL_TAX_STATES
            and not inp.taxpayer.locality and data.local is None):
        warnings.append(f"{inp.taxpayer.state.upper()} has local income taxes "
                        "but no locality is set — local tax computed as zero, "
                        "which is probably wrong")
    if sh.met is False:
        warnings.append("Safe harbor NOT met — see `ouch withhold check`")
    if sh.met is None:
        warnings.append("Prior-year figures missing — prior-year safe-harbor "
                        "test disabled")
    if inp.taxpayer.residency_months != 12:
        from ouch.errors import JurisdictionError
        raise JurisdictionError(
            "part-year residency is not supported in v1 (full-year only)",
            hint="set taxpayer.residency_months = 12 or wait for v1.5")

    # 18. Rate metrics (numeric marginal — captures phase-out cliffs) --------
    marginal_fed = Decimal(0)
    marginal_combined = Decimal(0)
    if compute_marginals:
        step = Money(1000)
        bumped = inp.model_copy(deep=True, update={
            "income": inp.income.model_copy(update={
                "wages": inp.income.wages.model_copy(update={
                    "taxpayer_w2": inp.income.wages.taxpayer_w2 + 1000,
                    "taxpayer_ss_wages":
                        (inp.income.wages.taxpayer_ss_wages + 1000)
                        if inp.income.wages.taxpayer_ss_wages > 0
                        else inp.income.wages.taxpayer_ss_wages,
                })})})
        bumped_result = run(bumped, data, compute_marginals=False)
        marginal_fed = ((bumped_result.federal_total_tax - fp.federal_total)
                        .ratio(step)).quantize(Decimal("0.0001"))
        marginal_combined = ((bumped_result.total_tax_all_jurisdictions
                              - total_tax).ratio(step)).quantize(Decimal("0.0001"))

    gross = fp.total_income + fp.excluded_income
    avg_by_jur: dict[str, Decimal] = {"federal": _rate(fp.federal_total, fp.agi)}
    if state_res is not None:
        avg_by_jur[state_res.code] = _rate(state_tax, fp.agi)
    if local_res is not None:
        avg_by_jur[local_res.name] = _rate(local_tax, fp.agi)

    trace = tb.build()
    fidelity = Fidelity.worst(*(i.fidelity for i in trace.items))

    return TaxResult(
        year=inp.tax_year,
        input_fingerprint=inp.fingerprint(),
        total_income=fp.total_income,
        agi=fp.agi,
        deduction_taken=fp.deduction,
        deduction_mode=fp.deduction_mode,  # type: ignore[arg-type]
        qbi_deduction=fp.qbi,
        taxable_income=fp.taxable_income,
        tax_ordinary=fp.tax_ordinary,
        tax_preferential=fp.tax_preferential + fp.tax_special,
        amt_additional=fp.amt_add,
        se_tax=fp.se_tax,
        additional_medicare=fp.addl_medicare,
        niit=fp.niit_tax,
        credits_nonrefundable=fp.credits_nonrefundable,
        credits_refundable=fp.credits_refundable,
        federal_total_tax=fp.federal_total,
        state=state_res,
        local=local_res,
        total_tax_all_jurisdictions=total_tax,
        total_payments=payments.total,
        balance_due_or_refund=balance,
        effective_rate_agi=_rate(total_tax, fp.agi),
        effective_rate_gross=_rate(total_tax, gross),
        effective_rate_taxable=_rate(total_tax, fp.taxable_income),
        marginal_rate_federal=marginal_fed,
        marginal_rate_combined=marginal_combined,
        average_rate_by_jurisdiction=avg_by_jur,
        safe_harbor=sh,
        trace=trace,
        fidelity=fidelity,
        warnings=tuple(warnings),
    )
