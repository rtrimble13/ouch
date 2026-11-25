"""M5 depth: AMT credit carryforward, quarterly estimates (incl. annualized
method), new state files.
"""

from decimal import Decimal

import pytest

from ouch.engine import pipeline
from ouch.engine.payments import quarterly_schedule
from ouch.model.money import Money, ZERO
from ouch.taxdata import loader
from tests.conftest import make_input


# ----- AMT credit carryforward ----------------------------------------------


def test_amt_credit_used_up_to_headroom(data_federal_only):
    """Single, 100k wages: taxable 84,250; regular tax 13,449.
    AMTI = 84,250 + 15,750 std = 100,000; exemption 88,100 → base 11,900
    × 26% = TMT 3,094. Headroom = 13,449 − 3,094 = 10,355.
    A 5,000 carryover is fully usable: total drops by exactly 5,000."""
    base = make_input(income={"wages": {"taxpayer_w2": "100000"}})
    with_credit = make_input(income={"wages": {"taxpayer_w2": "100000"}},
                             carryovers={"amt_credit": "5000"})
    r0 = pipeline.run(base, data_federal_only, compute_marginals=False)
    r1 = pipeline.run(with_credit, data_federal_only, compute_marginals=False)
    assert r0.federal_total_tax - r1.federal_total_tax == Money(5_000)
    assert r1.trace.get("fed.credits.amt").amount == Money(5_000)


def test_amt_credit_limited_by_headroom(data_federal_only):
    """A 50,000 carryover exceeds the 10,355 headroom → only 10,355 used,
    remainder carried forward with a warning."""
    inp = make_input(income={"wages": {"taxpayer_w2": "100000"}},
                     carryovers={"amt_credit": "50000"})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r.trace.get("fed.credits.amt").amount == Money(10_355)
    assert any("carryforward remaining" in w for w in r.warnings)


# ----- quarterly estimates --------------------------------------------------


def _est_input(**payments_extra):
    payments = {"prior_year": {"agi": "100000", "total_tax": "28000"}}
    payments.update(payments_extra)
    return make_input(
        income={"business": {"schedule_c_net": "130000",
                             "qbi_eligible_income": "130000"}},
        payments=payments)


def test_quarterly_schedule_even(data_federal_only):
    """Prior-year 28,000 (AGI < 150k → 100%) beats 90% of current → the
    requirement is 28,000, split 7,000 per quarter, no withholding."""
    inp = _est_input()
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    annual, schedule = quarterly_schedule(
        inp, data_federal_only.federal, r.federal_total_tax, ZERO)
    assert annual == Money(28_000)
    assert [q.required for q in schedule] == [Money(7_000)] * 4
    assert schedule[0].due_date == "2025-04-15"
    assert schedule[3].due_date == "2026-01-15"  # Q4 lands in January


def test_quarterly_schedule_annualized(data_federal_only):
    """Income fractions 10/20/30/40 shift the requirement toward the
    late quarters: 2,800 / 5,600 / 8,400 / 11,200."""
    inp = _est_input(annualized_income_fractions=["0.1", "0.2", "0.3", "0.4"])
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    annual, schedule = quarterly_schedule(
        inp, data_federal_only.federal, r.federal_total_tax, ZERO)
    assert [q.required for q in schedule] == [
        Money(2_800), Money(5_600), Money(8_400), Money(11_200)]


def test_quarterly_schedule_target_zero_and_withholding(data_federal_only):
    """target zero uses the full liability; withholding reduces the amount
    needed via estimates."""
    inp = _est_input()
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    annual, _ = quarterly_schedule(
        inp, data_federal_only.federal, r.federal_total_tax, Money(10_000),
        target_zero=True)
    assert annual == r.federal_total_tax - Money(10_000)


def test_annualized_fractions_must_sum_to_one():
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="must sum to 1.0"):
        make_input(payments={
            "annualized_income_fractions": ["0.1", "0.1", "0.1", "0.1"]})


# ----- new states -----------------------------------------------------------


def test_colorado_flat_on_federal_taxable(data_federal_only):
    """CO: 4.4% of federal taxable income. 100k wages → 84,250 × 4.4%
    = 3,707."""
    data = pipeline.ResolvedData(federal=data_federal_only.federal,
                                 state=loader.load_state("CO", 2025))
    r = pipeline.run(make_input(
        taxpayer={"filing_status": "single", "state": "CO"},
        income={"wages": {"taxpayer_w2": "100000"}}), data,
        compute_marginals=False)
    assert r.state.tax == Money(3_707)


def test_california_progressive(data_federal_only):
    """CA: AGI 100,000 − 5,540 std = 94,460 taxable. Hand-computed through
    the placeholder brackets:
    1%×10,756 + 2%×14,743 + 4%×14,746 + 6%×15,621 + 8%×14,740
    + 9.3%×(94,460−70,606) = 107.56+294.86+589.84+937.26+1,179.20+2,218.42
    = 5,327.14."""
    data = pipeline.ResolvedData(federal=data_federal_only.federal,
                                 state=loader.load_state("CA", 2025))
    r = pipeline.run(make_input(
        taxpayer={"filing_status": "single", "state": "CA"},
        income={"wages": {"taxpayer_w2": "100000"}}), data,
        compute_marginals=False)
    assert r.state.tax.round_cent() == Money("5327.14")


def test_washington_none_with_gain_warning_in_notes():
    """WA is regime none; its data file carries the excise-tax caveat."""
    wa = loader.load_state("WA", 2025)
    assert wa.regime.value == "none"
    assert "capital gains" in wa.meta.notes
