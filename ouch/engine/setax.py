"""SE tax, Additional Medicare tax, NIIT (spec §9.7).

The W-2/SE Social Security coordination is mandatory: a wage earner with a
side business must not pay the SS portion twice above the wage base.
"""

from __future__ import annotations

from dataclasses import dataclass

from ouch.model.enums import FilingStatus
from ouch.model.money import Money, ZERO, maxm, minm
from ouch.taxdata.schema import FederalData


@dataclass(frozen=True)
class SETaxResult:
    se_base: Money
    ss_portion: Money
    medicare_portion: Money
    se_tax: Money
    se_deduction: Money


def self_employment_tax(se_net_income: Money, w2_ss_wages: Money,
                        fed: FederalData) -> SETaxResult:
    p = fed.payroll
    if se_net_income <= ZERO:
        return SETaxResult(ZERO, ZERO, ZERO, ZERO, ZERO)
    se_base = se_net_income * p.se_income_factor            # 92.35%
    wage_base = Money(p.social_security.wage_base)
    ss_available = maxm(ZERO, wage_base - w2_ss_wages)      # coordination!
    ss_portion = minm(se_base, ss_available) * p.social_security.rate_self_employed
    medicare = se_base * p.medicare.rate_self_employed
    se_tax = ss_portion + medicare
    return SETaxResult(
        se_base=se_base, ss_portion=ss_portion, medicare_portion=medicare,
        se_tax=se_tax, se_deduction=se_tax * p.se_deduction_pct,
    )


def additional_medicare(medicare_wages: Money, se_base: Money,
                        status: FilingStatus, fed: FederalData) -> Money:
    am = fed.payroll.additional_medicare
    threshold = Money(am.threshold[status])
    excess = maxm(ZERO, medicare_wages + se_base - threshold)
    return excess * am.rate


def niit(net_investment_income: Money, magi: Money,
         status: FilingStatus, fed: FederalData) -> Money:
    threshold = Money(fed.niit.threshold[status])
    base = minm(maxm(net_investment_income, ZERO), maxm(ZERO, magi - threshold))
    return base * fed.niit.rate
