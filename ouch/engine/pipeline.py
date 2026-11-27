"""Pipeline orchestration — the canonical ordering (spec §9.1).

Pure: `TaxInput × ResolvedData -> TaxResult`. No I/O, no clock, no globals,
no mutation of inputs. Invariants are asserted between steps (§15.3) and
raise exit-code-9 errors rather than emitting a wrong number.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from ouch.engine import setax
from ouch.engine.credits import compute_credits
from ouch.engine.deductions import (ItemizedResult, QbiResult,
                                    itemized_deduction, itemized_limitation,
                                    nonitemizer_charitable, qbi_deduction,
                                    schedule_1a_items, senior_deduction,
                                    standard_deduction)
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
    former_state: StateData | None = None   # part-year: prior residence


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
    schedule_1a: Money
    line_12f: Money
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
    # The Social Security wage base is per person, so SE tax is coordinated
    # against the business owner's own box 3 only — never the household's.
    # Each person's box 3 defaults to their own box 1 when not supplied.
    taxpayer_ss_wages = Money(w.taxpayer_ss_wages or w.taxpayer_w2)
    spouse_ss_wages = Money(w.spouse_ss_wages or w.spouse_w2)
    owner_ss_wages = (spouse_ss_wages if biz.owner == "spouse"
                      else taxpayer_ss_wages)
    # Medicare wages (box 5) are uncapped — never substitute capped box 3.
    # Each person's box 5 defaults to their own box 1 when not supplied.
    medicare_wages = (
        Money(w.taxpayer_medicare_wages or w.taxpayer_w2)
        + Money(w.spouse_medicare_wages or w.spouse_w2))
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
    se = setax.self_employment_tax(se_net, owner_ss_wages, fed)
    tb.add("fed.setax", "Self-employment tax", se.se_tax, jurisdiction="federal",
           rule="92.35% of SE net income; SS portion limited to the wage base "
                f"remaining after the {biz.owner}'s own W-2 social security "
                "wages (the wage base is per person)",
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
    # Schedule C flows to Schedule 1 line 3 unfloored: a business loss
    # reduces total income. (SE tax, SE health and earned income floor it
    # separately, as the statute does.)
    income_ex_ss = (wages + se_net + ordinary_unearned_ex_ss
                    + pref_income + netting.unrecap_1250 + netting.collectibles)
    se_loss_warnings: tuple[str, ...] = ()
    if se_net < ZERO:
        se_loss_warnings = (
            f"Schedule C loss of ${(-se_net).round_dollar().amount:,.0f} "
            "reduces income in full — at-risk, passive-activity, hobby-loss "
            "and excess-business-loss (§461(l)) limits are not modeled",)
        warnings.extend(se_loss_warnings)
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
           inputs=("fed.income.wages", "fed.income.capital"),
           fidelity=Fidelity.APPROXIMATE if se_loss_warnings else Fidelity.EXACT,
           warnings=se_loss_warnings)
    tb.add("fed.agi", "Adjusted gross income", agi, jurisdiction="federal",
           rule="total income less above-the-line adjustments",
           form_ref="1040 line 11", authority="IRC §62",
           inputs=("fed.income.total", "fed.adjustments"))
    if agi > total_income:
        raise InvariantError("AGI exceeds total income")

    # 6a. Schedule 1-A additional deductions -----------------------------------
    # Below AGI, available whether or not the filer itemizes, and dependent on
    # AGI only, so they're settled before the standard/itemized choice (which
    # the §68 limitation needs them for).
    senior = senior_deduction(inp, agi, fed)  # MAGI = AGI (no exclusion inputs)
    warnings.extend(senior.warnings)
    schedule_1a = senior.deduction
    if senior.deduction > ZERO:
        sec = fed.schedule_1a.senior  # type: ignore[union-attr]
        tb.add("fed.deduction.senior", "Enhanced deduction for seniors",
               senior.deduction, jurisdiction="federal",
               rule=(f"${sec.amount:,.0f} less "
                     f"{(sec.phaseout_rate * 100).normalize():f}% of MAGI over "
                     f"${sec.phaseout_threshold[status]:,.0f} = "
                     f"${senior.per_person.round_dollar().amount:,.0f} × "
                     f"{senior.qualifying} qualifying "
                     f"{'person' if senior.qualifying == 1 else 'people'} "
                     f"aged {sec.min_age}+; MAGI taken as AGI"),
               form_ref="Schedule 1-A Part V", authority="P.L. 119-21 (OBBBA)",
               inputs=("fed.agi",), warnings=senior.warnings)
    parts = ["fed.deduction.senior"] if senior.deduction > ZERO else []
    form_parts = {"tips": "Part II", "overtime": "Part III",
                  "car_loan_interest": "Part IV"}
    for item in schedule_1a_items(inp, agi, fed):
        warnings.extend(item.warnings)
        if item.amount <= ZERO:
            continue
        sec = item.section
        rounding = "rounded down" if sec.round_steps == "down" else "rounded up"
        tb.add(f"fed.deduction.{item.key}", item.label, item.amount,
               jurisdiction="federal",
               rule=(f"min(${item.claimed.round_dollar().amount:,.0f}, cap "
                     f"${sec.cap[status]:,.0f}) less ${sec.reduction_per_step:,.0f} "
                     f"per ${sec.step:,.0f} of MAGI over "
                     f"${sec.phaseout_threshold[status]:,.0f} ({rounding}); "
                     f"MAGI taken as AGI"),
               form_ref=f"Schedule 1-A {form_parts[item.key]}",
               authority="P.L. 119-21 (OBBBA)",
               inputs=("fed.agi",), warnings=item.warnings)
        parts.append(f"fed.deduction.{item.key}")
        schedule_1a += item.amount
    if schedule_1a > ZERO:
        tb.add("fed.schedule_1a", "Schedule 1-A additional deductions",
               schedule_1a, jurisdiction="federal",
               rule="sum of Schedule 1-A deductions",
               form_ref="Form 1040 line 13 (13b for 2025, 13a from 2026)",
               authority="Schedule 1-A Part VI", inputs=tuple(parts))

    def qbi_given(line_12: Money) -> QbiResult:
        # Form 8995 line 11: taxable income before QBI is AGI less lines 12
        # (12e and 12f) and the Schedule 1-A deductions.
        return qbi_deduction(inp, maxm(ZERO, agi - line_12 - schedule_1a),
                             pref_income, se.se_deduction, se_health, fed)

    # 6. Deduction: standard vs. itemized ------------------------------------
    std = standard_deduction(inp, fed)
    itemized = itemized_deduction(inp, agi, salt_estimate,
                                  interest + nonqualified_div, fed)
    # 2026 onward: cash gifts are deductible on line 12f without itemizing.
    line_12f = nonitemizer_charitable(inp, fed)
    # 2026 onward: §68 reduces itemized deductions in the top bracket. It
    # "will not apply when figuring any QBID" (2026 Form 1040-ES), so the
    # QBI here, and the one actually claimed when itemizing, uses the
    # unreduced itemized total.
    limitation = ZERO
    if fed.itemized.limitation is not None and itemized.total > ZERO:
        qbi_itemizing = qbi_given(itemized.total)
        limitation = itemized_limitation(
            itemized.total, agi - schedule_1a - qbi_itemizing.deduction,
            status, fed)
    itemized_allowed = itemized.total - limitation

    mode_setting = inp.deductions.mode
    if mode_setting == DeductionMode.STANDARD:
        mode = "standard"
    elif mode_setting == DeductionMode.ITEMIZED:
        mode = "itemized"
    elif itemized_allowed > std + line_12f:
        mode = "itemized"
    else:
        mode = "standard"
    deduction = itemized_allowed if mode == "itemized" else std
    line_12f = line_12f if mode == "standard" else ZERO
    crossover = itemized_allowed - (std + line_12f)
    salt_note = ""
    if itemized.salt_cap_reduced:
        sc = fed.itemized.salt_cap
        assert sc.phasedown is not None
        salt_note = (
            f"; SALT cap ${itemized.salt_cap.round_dollar().amount:,.0f} "
            f"(${sc.for_status(status):,.0f} less "
            f"{(sc.phasedown.rate * 100).normalize():f}% of MAGI over "
            f"${sc.phasedown.threshold.for_status(status):,.0f}, floor "
            f"${sc.phasedown.floor.for_status(status):,.0f})")
    if itemized.charitable_floor > ZERO:
        salt_note += (f"; charitable gifts less "
                      f"${itemized.charitable_floor.round_dollar().amount:,.0f} "
                      f"(0.5%-of-AGI floor)")
    if limitation > ZERO:
        salt_note += (f"; itemized reduced by "
                      f"${limitation.round_dollar().amount:,.0f} (§68)")
    deduction_warnings: list[str] = []
    if mode == "standard" and itemized_allowed > ZERO:
        deduction_warnings.append(
            f"itemizing trails the standard deduction by "
            f"${(-crossover).round_dollar().amount:,.0f}")
    if mode == "itemized" and itemized.charitable_floor > ZERO:
        deduction_warnings.append(
            f"${itemized.charitable_floor.round_dollar().amount:,.0f} of "
            f"charitable gifts fall under the 0.5%-of-AGI floor; that amount "
            f"carries forward to later years, which ouch doesn't track")
    warnings.extend(deduction_warnings)
    tb.add("fed.deduction", f"Deduction ({mode})", deduction,
           jurisdiction="federal",
           rule=(f"max(standard ${std.round_dollar().amount:,.0f}"
                 + (f" + ${line_12f.round_dollar().amount:,.0f} line 12f"
                    if line_12f > ZERO else "")
                 + f", itemized ${itemized_allowed.round_dollar().amount:,.0f})"
                 if mode_setting == DeductionMode.AUTO
                 else f"forced {mode}") + salt_note,
           form_ref="1040 line 12", authority="IRC §63",
           inputs=("fed.agi",), warnings=tuple(deduction_warnings))
    if limitation > ZERO and mode == "itemized":
        lim = fed.itemized.limitation
        tb.add("fed.deduction.itemized_limitation",
               "Overall limitation on itemized deductions", limitation,
               jurisdiction="federal",
               rule=(f"{(lim.rate * 100).normalize():f}% × lesser of itemized "
                     f"${itemized.total.round_dollar().amount:,.0f} and income "
                     f"(AGI less Schedule 1-A and QBI) over "
                     f"${lim.threshold[status]:,.0f}"),
               form_ref="Schedule A line 18 (Itemized Deductions Worksheet)",
               authority="IRC §68 (P.L. 119-21)", inputs=("fed.agi",),
               fidelity=Fidelity.APPROXIMATE,
               warnings=("rate and thresholds from the 2026 Form 1040-ES; the "
                         "Schedule A worksheet isn't published yet",))
    if line_12f > ZERO:
        tb.add("fed.deduction.charitable_nonitemizer",
               "Charitable deduction for non-itemizers", line_12f,
               jurisdiction="federal",
               rule=(f"cash gifts (not to donor-advised funds or supporting "
                     f"organizations), up to "
                     f"${fed.itemized.nonitemizer_charitable.mfj_amount if status == FilingStatus.MARRIED_FILING_JOINTLY else fed.itemized.nonitemizer_charitable.amount:,.0f}"),  # type: ignore[union-attr]
               form_ref="1040 line 12f", authority="P.L. 119-21 (OBBBA)",
               inputs=("fed.agi",))
        warnings.append("charitable deduction for non-itemizers assumes the cash "
                        "gifts went to qualifying charities; enter gifts to "
                        "donor-advised funds or supporting organizations as "
                        "charitable_cash_daf")

    # 7. QBI deduction -------------------------------------------------------
    # When itemizing, QBI uses the itemized total before §68.
    qbi = qbi_given((itemized.total if mode == "itemized" else deduction) + line_12f)
    taxable_before_qbi = maxm(ZERO, agi - deduction - line_12f - schedule_1a)
    warnings.extend(qbi.warnings)
    if qbi.deduction > ZERO:
        tb.add("fed.qbi", "QBI deduction", qbi.deduction,
               jurisdiction="federal",
               rule="20% of qualified business income after allocable "
               "adjustments, limited to 20% of taxable income less net "
               "capital gain; wage/UBIA limit above the threshold"
               + ("; at least the minimum for active QBI" if qbi.warnings else ""),
               form_ref="Form 8995", authority="IRC §199A",
               inputs=("fed.deduction", "fed.agi"),
               fidelity=Fidelity.APPROXIMATE)

    # 8. Taxable income ------------------------------------------------------
    taxable_income = maxm(ZERO, taxable_before_qbi - qbi.deduction)
    tb.add("fed.taxable", "Taxable income", taxable_income,
           jurisdiction="federal",
           rule="AGI less deduction"
                + (" less line 12f" if line_12f > ZERO else "")
                + (" less Schedule 1-A" if schedule_1a > ZERO else "")
                + " less QBI",
           form_ref="1040 line 15", authority="IRC §63",
           inputs=("fed.agi", "fed.deduction")
           + (("fed.deduction.charitable_nonitemizer",) if line_12f > ZERO else ())
           + (("fed.schedule_1a",) if schedule_1a > ZERO else ())
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
    amt_add, tmt = amt_additional(
        taxable_income, pref_income, mode, std,
        # §68 doesn't apply for AMT (§56(b)(1)(F)), so AMTI gets back the
        # reduction along with the SALT addback.
        itemized.salt - limitation if mode == "itemized" else ZERO,
        status, fed.amt, fed.preferential_brackets[status], regular_tax,
        regular_ordinary=maxm(ZERO, taxable_income - pref_income
                              - netting.unrecap_1250 - netting.collectibles),
        other_addbacks=senior.deduction)
    if amt_add > ZERO:
        tb.add("fed.amt.additional", "Alternative minimum tax (excess)",
               amt_add, jurisdiction="federal",
               rule="tentative minimum tax over regular tax; AMTI approximated "
                    "as taxable income plus the standard/SALT addback and "
                    "the Schedule 1-A senior deduction",
               form_ref="Form 6251", authority="IRC §55",
               inputs=("fed.taxable",), fidelity=Fidelity.APPROXIMATE)
    elif regular_tax > ZERO and tmt > regular_tax * Decimal("0.9"):
        # AMT-proximity warning (§15.4): within 10% of regular tax
        warnings.append("AMT within 10% of regular tax — a small change "
                        "could trigger it")

    # 11. Additional Medicare tax; NIIT --------------------------------------
    addl_med = setax.additional_medicare(medicare_wages, se.se_base, status, fed)
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

    # 12–13. Credits (ordered cascade — spec §9.8) ---------------------------
    earned_income = wages + maxm(se_net, ZERO)
    income_tax_liability = regular_tax + amt_add
    # EITC investment income: interest (incl. tax-exempt) + dividends + net
    # capital gain included in income
    eitc_investment_income = (
        interest + Money(inv.tax_exempt_interest)
        + Money(inv.ordinary_dividends)
        + maxm(ZERO, netting.ordinary_component + netting.preferential_gain
               + netting.unrecap_1250 + netting.collectibles))
    credits = compute_credits(inp, agi, income_tax_liability, earned_income,
                              eitc_investment_income, fed)
    if credits.nonrefundable_used > income_tax_liability:
        raise InvariantError("nonrefundable credits exceed tax liability")
    for item in credits.items:
        tb.add(item.id, item.label.capitalize(), item.amount,
               jurisdiction="federal",
               rule=("refundable credit" if item.refundable
                     else "nonrefundable credit, clamped to remaining "
                          "liability"),
               inputs=("fed.agi", data_ref),
               fidelity=Fidelity.APPROXIMATE)
    warnings.extend(credits.warnings)

    # AMT credit carryforward (Form 8801): prior-year AMT is recoverable to
    # the extent regular tax exceeds tentative minimum tax this year.
    amt_credit_used = ZERO
    carryover = Money(inp.carryovers.amt_credit)
    if carryover > ZERO and amt_add == ZERO:
        # Form 8801 lines 22–25: regular tax less the other nonrefundable
        # credits (Form 1040 line 19, Schedule 3 lines 1–6z), over TMT.
        liability_left = (income_tax_liability - credits.nonrefundable_used)
        headroom = maxm(ZERO, liability_left - tmt)
        amt_credit_used = minm(carryover, headroom)
        if amt_credit_used > ZERO:
            tb.add("fed.credits.amt", "Minimum tax credit (AMT carryforward)",
                   amt_credit_used, jurisdiction="federal",
                   rule="prior-year AMT recovered up to the excess of regular "
                        "tax over tentative minimum tax",
                   form_ref="Form 8801", authority="IRC §53",
                   inputs=("fed.taxable",), fidelity=Fidelity.APPROXIMATE)
        remaining_carryover = carryover - amt_credit_used
        if remaining_carryover > ZERO:
            warnings.append(
                f"AMT credit carryforward remaining: "
                f"${remaining_carryover.round_dollar().amount:,.0f} "
                "(carries to future years)")

    # 14. Federal total tax --------------------------------------------------
    federal_total = (income_tax_liability + se.se_tax + addl_med + niit_tax
                     - credits.nonrefundable_used - amt_credit_used
                     - credits.refundable)
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
               "fed.credits.amt" if amt_credit_used > ZERO else None,
           ) if i) + tuple(item.id for item in credits.items))

    excluded = (Money(inv.tax_exempt_interest)
                + maxm(ZERO, Money(ret.social_security_gross) - taxable_ss))

    return _FederalPass(
        tb=tb, total_income=total_income, agi=agi,
        adjustments_total=adjustments_total, deduction=deduction,
        deduction_mode=mode, itemized=itemized, standard_amount=std,
        qbi=qbi.deduction, schedule_1a=schedule_1a, line_12f=line_12f,
        taxable_income=taxable_income,
        tax_ordinary=tax.ordinary, tax_preferential=tax.preferential,
        tax_special=tax.special, amt_add=amt_add,
        se_tax=se.se_tax, se_deduction=se.se_deduction,
        addl_medicare=addl_med, niit_tax=niit_tax,
        credits_nonrefundable=credits.nonrefundable_used + amt_credit_used,
        credits_refundable=credits.refundable, federal_total=federal_total,
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

    # Part-year residency (§9.9 v1.5): income is allocated to each state by
    # the residency-month ratio — a planning-grade approximation of the
    # per-state part-year allocation schedules (fidelity: approximate).
    residency_fraction = Decimal(inp.taxpayer.residency_months) / 12
    if residency_fraction < 1:
        warnings.append(
            f"part-year residency: state tax allocated by month ratio "
            f"({inp.taxpayer.residency_months}/12 in "
            f"{inp.taxpayer.state.upper() or 'primary state'}"
            + (f", remainder in {inp.taxpayer.former_state.upper()}"
               if inp.taxpayer.former_state else
               ", remaining months unallocated — set taxpayer.former_state "
               "if another taxing state applies")
            + ") — approximate; states use their own allocation schedules")

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
        if residency_fraction < 1:
            state_res = replace(state_res,
                                tax=(state_res.tax * residency_fraction)
                                .round_cent())
        local_res = (compute_local(inp, ctx, state_res, data.local)
                     if data.local is not None else None)
        if local_res is not None and residency_fraction < 1:
            local_res = replace(local_res,
                                tax=(local_res.tax * residency_fraction)
                                .round_cent())
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

    # Former state (part-year): the remaining months' allocation.
    former_res = None
    if (data.former_state is not None and residency_fraction < 1
            and inp.taxpayer.former_state):
        former_res = compute_state(inp, ctx, data.former_state)
        former_res = replace(
            former_res,
            tax=(former_res.tax * (Decimal(1) - residency_fraction))
            .round_cent())

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
    if former_res is not None:
        code = former_res.code.lower()
        tb.add(f"{code}.tax", f"{former_res.code} income tax (part-year)",
               former_res.tax, jurisdiction=former_res.code,
               rule=f"full-year {former_res.code} tax × "
                    f"{12 - inp.taxpayer.residency_months}/12 residency ratio",
               inputs=("fed.agi",), fidelity=Fidelity.APPROXIMATE)

    # 17. Payments, safe harbor, balance due ---------------------------------
    payments = project_payments(inp)
    sh = safe_harbor(inp, fp.federal_total, payments.federal, fed)
    state_tax = state_res.tax if state_res else ZERO
    local_tax = local_res.tax if local_res else ZERO
    former_tax = former_res.tax if former_res else ZERO
    total_tax = fp.federal_total + state_tax + local_tax + former_tax
    balance = total_tax - payments.total
    tb.add("total.tax", "Total tax, all jurisdictions", total_tax,
           jurisdiction="all",
           rule="federal + state + local"
                + (" + former state (part-year)" if former_res else ""),
           inputs=tuple(i for i in (
               "fed.tax.total",
               f"{state_res.code.lower()}.tax" if state_res else None,
               f"{local_res.name.lower()}.tax" if local_res else None,
               f"{former_res.code.lower()}.tax" if former_res else None) if i))
    tb.add("total.payments", "Withholding and estimated payments projected "
           "through year end", payments.total, jurisdiction="all",
           rule="YTD withholding + per-period × periods remaining + estimates")
    tb.add("total.balance", "Projected balance due / (refund)", balance,
           jurisdiction="all", rule="total tax less total payments",
           inputs=("total.tax", "total.payments"))

    # Warnings (§15.4) -------------------------------------------------------
    if not fed.meta.verified:
        warnings.append(f"Federal tax data for {inp.tax_year} is unverified")
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

    # 18. Rate metrics (numeric marginal — captures phase-out cliffs) --------
    marginal_fed = Decimal(0)
    marginal_combined = Decimal(0)
    if compute_marginals:
        step = Money(1000)
        w_in = inp.income.wages

        def _bump(explicit: Decimal) -> Decimal:
            # An explicit box-3/box-5 figure moves with box 1; an absent one
            # stays absent and keeps defaulting to box 1.
            return explicit + 1000 if explicit > 0 else explicit

        bumped = inp.model_copy(deep=True, update={
            "income": inp.income.model_copy(update={
                "wages": w_in.model_copy(update={
                    "taxpayer_w2": w_in.taxpayer_w2 + 1000,
                    "taxpayer_ss_wages": _bump(w_in.taxpayer_ss_wages),
                    "taxpayer_medicare_wages":
                        _bump(w_in.taxpayer_medicare_wages),
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
    if former_res is not None:
        avg_by_jur[former_res.code] = _rate(former_tax, fp.agi)

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
        schedule_1a_deduction=fp.schedule_1a,
        nonitemizer_charitable_deduction=fp.line_12f,
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
        other_state=former_res,
    )
