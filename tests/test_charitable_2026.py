"""2026 charitable changes and the §68 limit on itemized deductions
(rtrimble13/ouch#24).

Sources:
- draft 2026 Form 1040 instructions, What's New and line 12f: itemizers deduct
  only gifts "more than 0.5% of your adjusted gross income"; non-itemizers
  deduct cash gifts up to $1,000 ($2,000 MFJ), not to donor-advised funds or
  §509(a)(3) organizations, and not noncash gifts or carryovers.
- 2026 Form 1040-ES, What's New: itemized deductions "reduced by 5.4% of the
  lesser of (1) your total itemized deductions or (2) the amount your taxable
  income is more than" $768,700 (MFJ, QSS), $640,600 (single, HoH), $384,350
  (MFS), "applied after any other applicable limitations … and will not
  apply when figuring any QBID".
- draft 2026 Schedule A line 18: the income measured is Form 1040 line 11b
  less lines 13a and 13b (AGI less the Schedule 1-A and QBI deductions).

Hand computations use the 2026 file: standard deduction 16,100 single /
32,200 MFJ; single brackets 10% to 12,400, 12% to 50,400, 22% to 105,700,
24% to 201,775; MFJ 10% to 24,800, 12% to 100,800, 37% from 768,700 (tax
there 206,583.50).
"""

import pytest
from pydantic import ValidationError

from ouch.engine import pipeline
from ouch.engine.pipeline import ResolvedData
from ouch.model.money import Money, ZERO
from ouch.taxdata import loader
from tests.conftest import make_input


@pytest.fixture(scope="module")
def data():
    return ResolvedData(federal=loader.load_federal(2026))


def _run(data, wages, status="single", year=2026, **itemized):
    mode = itemized.pop("mode", "auto")
    raw = {"tax_year": year,
           "taxpayer": {"filing_status": status, "state": ""},
           "income": {"wages": {"taxpayer_w2": str(wages)}},
           "deductions": {"mode": mode, "itemized": itemized}}
    return pipeline.run(make_input(**raw), data, compute_marginals=False)


# ----- the non-itemizer deduction (line 12f) --------------------------------

def test_nonitemizer_single_capped_at_1000(data):
    """Single, wages 80,000, cash gifts 1,500: line 12f 1,000.
    taxable = 80,000 − 16,100 − 1,000 = 62,900
    tax = 1,240 + 12% × 38,000 (4,560) + 22% × 12,500 (2,750) = 8,550.00"""
    r = _run(data, 80_000, charitable_cash="1500")
    assert r.deduction_mode == "standard"
    assert r.deduction_taken == Money(16_100)
    assert r.nonitemizer_charitable_deduction == Money(1_000)
    assert r.taxable_income == Money(62_900)
    assert r.federal_total_tax.round_cent() == Money("8550.00")
    assert r.trace.get("fed.deduction.charitable_nonitemizer").form_ref == "1040 line 12f"


def test_nonitemizer_mfj_up_to_2000(data):
    """MFJ, wages 120,000, cash gifts 1,500 (under the 2,000 cap).
    taxable = 120,000 − 32,200 − 1,500 = 86,300
    tax = 2,480 + 12% × 61,500 (7,380) = 9,860.00"""
    r = _run(data, 120_000, status="married_filing_jointly", charitable_cash="1500")
    assert r.nonitemizer_charitable_deduction == Money(1_500)
    assert r.federal_total_tax.round_cent() == Money("9860.00")


def test_nonitemizer_excludes_donor_advised_funds(data):
    """1,500 of cash gifts, 1,000 of them to a donor-advised fund → 500."""
    r = _run(data, 80_000, charitable_cash="1500", charitable_cash_daf="1000")
    assert r.nonitemizer_charitable_deduction == Money(500)


def test_nonitemizer_excludes_noncash_gifts(data):
    r = _run(data, 80_000, charitable_noncash="3000")
    assert r.nonitemizer_charitable_deduction == ZERO


def test_daf_cannot_exceed_cash():
    with pytest.raises(ValidationError, match="charitable_cash_daf"):
        make_input(deductions={"itemized": {"charitable_cash": "500",
                                            "charitable_cash_daf": "600"}})


# ----- the 0.5% floor for itemizers -----------------------------------------

def test_itemizer_floor_half_percent_of_agi(data):
    """Single, AGI 200,000: SALT 30,000 (under the 40,400 cap), mortgage
    interest 10,000, cash gifts 5,000. Floor 0.5% × 200,000 = 1,000 → 4,000.
    itemized = 30,000 + 10,000 + 4,000 = 44,000 (beats 16,100 + 1,000)
    taxable = 156,000; tax = 17,966 + 24% × 50,300 (12,072) = 30,038.00"""
    r = _run(data, 200_000, state_local_income_tax="20000", real_estate_tax="10000",
             mortgage_interest="10000", charitable_cash="5000")
    assert r.deduction_mode == "itemized"
    assert r.deduction_taken == Money(44_000)
    assert r.nonitemizer_charitable_deduction == ZERO
    assert r.federal_total_tax.round_cent() == Money("30038.00")
    assert any("0.5%-of-AGI floor" in w and "carries forward" in w for w in r.warnings)


def test_auto_mode_counts_line_12f_with_the_standard_deduction(data):
    """Single, wages 60,000: real estate tax 14,000, mortgage 2,000, cash 1,200.
    Itemized = 14,000 + 2,000 + (1,200 − 0.5% × 60,000 = 900) = 16,900, which
    beats the 16,100 standard deduction alone but not standard + line 12f
    (16,100 + 1,000 = 17,100). So AUTO takes the standard deduction.
    taxable = 60,000 − 17,100 = 42,900; tax = 1,240 + 12% × 30,500 = 4,900.00"""
    r = _run(data, 60_000, real_estate_tax="14000", mortgage_interest="2000",
             charitable_cash="1200")
    assert r.deduction_mode == "standard"
    assert r.nonitemizer_charitable_deduction == Money(1_000)
    assert r.taxable_income == Money(42_900)
    assert r.federal_total_tax.round_cent() == Money("4900.00")


# ----- the §68 limitation ---------------------------------------------------

def test_itemized_limitation_capped_by_itemized_total(data):
    """MFJ, wages 1,000,000. SALT cap at this MAGI: max(10,000, 40,400 − 30%
    × 495,000) = 10,000. Mortgage 30,000; cash gifts 60,000 less the floor
    0.5% × 1,000,000 = 5,000 → 55,000. Itemized before §68 = 95,000.
    Income over 768,700 = 231,300 > 95,000 → reduction 5.4% × 95,000 = 5,130.
    Allowed itemized = 89,870; taxable = 910,130
    tax = 206,583.50 + 37% × 141,430 (52,329.10) = 258,912.60
    Additional Medicare 0.9% × 750,000 = 6,750 → 265,662.60
    (AMT: AMTI = 910,130 + 10,000 SALT − 5,130 = 915,000; exemption 140,200
    → TMT 63,570 + 28% × 530,300 = 212,054, under the regular tax.)"""
    r = _run(data, 1_000_000, status="married_filing_jointly",
             state_local_income_tax="50000", mortgage_interest="30000",
             charitable_cash="60000")
    assert r.deduction_mode == "itemized"
    assert r.deduction_taken == Money(89_870)
    assert r.trace.get("fed.deduction.itemized_limitation").amount == Money(5_130)
    assert r.amt_additional == ZERO
    assert r.federal_total_tax.round_cent() == Money("265662.60")


def test_itemized_limitation_capped_by_excess_income(data):
    """MFJ, wages 800,000: SALT floor 10,000 (40,400 − 30% × 295,000 < 10,000),
    mortgage 30,000, cash 60,000 less 4,000 floor → itemized 96,000.
    Excess 800,000 − 768,700 = 31,300 < 96,000 → 5.4% × 31,300 = 1,690.20.
    Allowed 94,309.80."""
    r = _run(data, 800_000, status="married_filing_jointly",
             state_local_income_tax="50000", mortgage_interest="30000",
             charitable_cash="60000")
    assert r.deduction_taken == Money("94309.80")


def test_no_limitation_below_the_37_percent_bracket(data):
    r = _run(data, 700_000, status="married_filing_jointly",
             state_local_income_tax="50000", mortgage_interest="30000")
    assert not r.trace.has("fed.deduction.itemized_limitation")


# ----- 2025 is unchanged ----------------------------------------------------

def test_2025_has_no_floor_no_line_12f_no_limitation(federal_2025):
    """The 2025 file carries none of the three sections.
    Single, wages 200,000: same itemizer as above → 30,000 + 10,000 + 5,000."""
    data = ResolvedData(federal=federal_2025)
    r = _run(data, 200_000, year=2025, state_local_income_tax="20000",
             real_estate_tax="10000", mortgage_interest="10000",
             charitable_cash="5000")
    assert r.deduction_taken == Money(45_000)
    r = _run(data, 80_000, year=2025, charitable_cash="1500")
    assert r.nonitemizer_charitable_deduction == ZERO
