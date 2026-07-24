"""Withholding, estimated payments, safe harbor (spec §9.1 step 17, §10.1)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ouch.model.enums import FilingStatus
from ouch.model.input import TaxInput
from ouch.model.money import Money, ZERO, maxm, minm
from ouch.model.result import SafeHarborResult
from ouch.taxdata.schema import FederalData


@dataclass(frozen=True)
class PaymentsProjection:
    federal: Money
    state: Money
    local: Money

    @property
    def total(self) -> Money:
        return self.federal + self.state + self.local


def project_payments(inp: TaxInput) -> PaymentsProjection:
    w = inp.payments.withholding
    e = inp.payments.estimated
    n = w.periods_remaining
    federal = (Money(w.federal_ytd) + Money(w.federal_per_period) * n
               + Money(e.q1_federal) + Money(e.q2_federal)
               + Money(e.q3_federal) + Money(e.q4_federal))
    state = Money(w.state_ytd) + Money(w.state_per_period) * n + Money(e.state_total)
    local = Money(w.local_ytd) + Money(w.local_per_period) * n + Money(e.local_total)
    return PaymentsProjection(federal=federal, state=state, local=local)


def safe_harbor(inp: TaxInput, federal_total_tax: Money,
                projected_federal_payments: Money,
                fed: FederalData) -> SafeHarborResult:
    sh = fed.estimated_payments.safe_harbor
    prior = inp.payments.prior_year
    status = inp.taxpayer.filing_status

    current_90 = federal_total_tax * sh.current_year_pct

    prior_req: Money | None = None
    prior_label = ""
    if prior.total_tax > 0:
        hi_threshold = (sh.high_income_agi_threshold_mfs
                        if status == FilingStatus.MARRIED_FILING_SEPARATELY
                        else sh.high_income_agi_threshold)
        if prior.agi > hi_threshold:
            pct = sh.prior_year_pct_high_income
            prior_label = f"{pct * 100:.0f}%"
        else:
            pct = sh.prior_year_pct
            prior_label = f"{pct * 100:.0f}%"
        prior_req = Money(prior.total_tax) * pct

    if prior_req is not None:
        required = minm(current_90, prior_req)
        met = projected_federal_payments >= required
    else:
        required = current_90
        met = None  # prior-year data missing disables the definitive test

    shortfall = maxm(ZERO, required - projected_federal_payments)

    # Form 2210 approximation (fidelity: heuristic): shortfall carried for an
    # average of half the year at the average underpayment rate.
    rates = fed.estimated_payments.underpayment_rate_by_quarter
    avg_rate = sum(rates) / len(rates) if rates else Decimal(0)
    penalty = shortfall * avg_rate / 2

    return SafeHarborResult(
        current_year_90pct=current_90,
        prior_year_pct=prior_req,
        prior_year_pct_label=prior_label,
        required=required,
        projected_federal_payments=projected_federal_payments,
        met=met,
        shortfall=shortfall,
        estimated_penalty=penalty,
    )


@dataclass(frozen=True)
class QuarterlyInstallment:
    quarter: int
    due_date: str            # ISO date, Q4 lands in the following January
    required: Money
    paid: Money


def quarterly_schedule(inp: TaxInput, fed: FederalData,
                       federal_total_tax: Money,
                       projected_withholding: Money, *,
                       target_zero: bool = False) -> tuple[Money, list[QuarterlyInstallment]]:
    """Four-payment estimated schedule (spec §10.4).

    The annual requirement is the safe-harbor minimum (or the full liability
    with target_zero) less withholding, which is treated as paid evenly
    across the year. With `payments.annualized_income_fractions` set, each
    installment follows the income fraction earned by that period — the
    annualized income installment method (fidelity: approximate; the
    statutory Schedule AI annualization factors are not applied).
    """
    sh = safe_harbor(inp, federal_total_tax, projected_withholding, fed)
    if target_zero:
        annual = federal_total_tax
    elif sh.required is not None:
        annual = sh.required
    else:
        annual = sh.current_year_90pct
    via_estimates = maxm(ZERO, annual - projected_withholding)

    fractions = inp.payments.annualized_income_fractions
    if fractions is None:
        shares = [Decimal("0.25")] * 4
    else:
        shares = [Decimal(f) for f in fractions]

    paid = [Money(inp.payments.estimated.q1_federal),
            Money(inp.payments.estimated.q2_federal),
            Money(inp.payments.estimated.q3_federal),
            Money(inp.payments.estimated.q4_federal)]

    installments = []
    for i, due in enumerate(fed.estimated_payments.due_dates[:4]):
        month, day = due.split("-")
        year = inp.tax_year + 1 if int(month) < 4 else inp.tax_year
        installments.append(QuarterlyInstallment(
            quarter=i + 1,
            due_date=f"{year}-{month}-{day}",
            required=(via_estimates * shares[i]).round_cent(),
            paid=paid[i]))
    return via_estimates, installments
