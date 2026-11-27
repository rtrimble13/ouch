"""Worksheet limits that the golden fixtures turned up (rtrimble13/ouch#23).

Each case has a matching golden fixture under tests/golden/. Sources:
- draft 2026 Form 1040 instructions, Qualified Dividends and Capital Gain
  Tax Worksheet line 25: "Enter the smaller of line 23 or line 24".
- draft 2026 Form 6251: Part III lines 20 and 27 enter "line 5 of the
  Qualified Dividends and Capital Gain Tax Worksheet … (as figured for the
  regular tax)"; line 40 is the smaller of lines 38 and 39; line 1a
  subtracts Schedule 1-A line 43 (seniors) from Form 1040 line 14.
- draft 2026 Form 8801 line 22 and its instructions: regular tax less the
  credits on Form 1040 line 19 and Schedule 3 lines 1–6z.

Hand computations use Rev. Proc. 2025-32 (2026): single brackets 10% to
12,400, 12% to 50,400, 22% to 105,700, 24% to 201,775; MFJ 22% to 211,400,
24% to 403,550; 0% capital gain rate to 49,450 single; 15% to 545,500
single; AMT exemption 90,100 single / 140,200 MFJ, 50% phase-out above
500,000 single.
"""

import pytest

from ouch.engine import pipeline
from ouch.engine.federal import amt_additional, federal_income_tax
from ouch.engine.pipeline import ResolvedData
from ouch.model.enums import FilingStatus as F
from ouch.model.money import Money, ZERO
from ouch.taxdata import loader
from tests.conftest import make_input


@pytest.fixture(scope="module")
def fed():
    return loader.load_federal(2026)


def _run(fed, **raw):
    raw.setdefault("tax_year", 2026)
    return pipeline.run(make_input(**raw), ResolvedData(federal=fed),
                        compute_marginals=False)


def test_qdcgt_line_25_takes_tax_on_all_income_when_smaller(fed):
    """Taxable 50,125 of which 600 is LTCG. Line 5 = 49,525 is above the
    49,450 breakpoint, so line 23 = tax(49,525) 5,695 + 15% × 600 (90) =
    5,785; line 24 = tax(50,125) = 1,240 + 12% × 37,725 = 5,767 → 5,767."""
    tax = federal_income_tax(Money(50_125), Money(600),
                             fed.ordinary_brackets[F.SINGLE],
                             fed.preferential_brackets[F.SINGLE])
    assert tax.ordinary == Money(5_695)
    assert tax.preferential == Money(72)
    assert tax.total == Money(5_767)


def test_qdcgt_worksheet_kept_when_smaller(fed):
    """Taxable 53,925 with 10,000 LTCG: 0% on 5,525, 15% on 4,475 (671.25);
    tax(43,925) = 5,023 → 5,694.25, under tax(53,925) = 6,575.50."""
    tax = federal_income_tax(Money(53_925), Money(10_000),
                             fed.ordinary_brackets[F.SINGLE],
                             fed.preferential_brackets[F.SINGLE])
    assert tax.preferential == Money("671.25")
    assert tax.total == Money("5694.25")


def test_amt_part_iii_measures_breakpoints_from_regular_ordinary_income(fed):
    """Single, taxable 583,900 (LTCG 450,000), standard deduction 16,100.
    AMTI 600,000; exemption 90,100 − 50% × 100,000 = 40,100; base 559,900.
    Line 18: 26% × 109,900 = 28,574. Line 20 = 133,900 (regular-tax
    ordinary income) is past 49,450, so nothing at 0%; line 29 = 545,500 −
    133,900 = 411,600 at 15% (61,740); 38,400 at 20% (7,680).
    TMT = 97,994. (Measured from the AMT ordinary base 109,900 instead, the
    15% band would hold 435,600 and TMT would be 96,794.)"""
    _, tmt = amt_additional(Money(583_900), Money(450_000), "standard",
                            Money(16_100), ZERO, F.SINGLE, fed.amt,
                            fed.preferential_brackets[F.SINGLE], ZERO)
    assert tmt == Money(97_994)


def test_amt_preferential_base_inside_the_zero_band(fed):
    """Single, taxable 100,000 of which 99,000 is qualified dividends, so
    regular-tax ordinary income is 1,000; standard deduction 16,100.
    AMTI 116,100 − 90,100 = 26,000 base, all preferential (line 22). Part
    III: 0% on min(49,450 − 1,000, 26,000) = 26,000 → line 38 = 0, under
    line 39 (26% × 26,000 = 6,760) → line 40 = 0."""
    _, tmt = amt_additional(Money(100_000), Money(99_000), "standard",
                            Money(16_100), ZERO, F.SINGLE, fed.amt,
                            fed.preferential_brackets[F.SINGLE], ZERO)
    assert tmt == ZERO


def test_senior_deduction_is_added_back_for_amt(fed):
    """MFJ, both over 65, wages 120,000 + pension 80,000. Standard 32,200
    + 2 × 1,650 = 35,500; senior 2 × (6,000 − 6% × 50,000) = 6,000;
    taxable 158,500; regular tax 11,600 + 22% × 57,700 = 24,294.
    AMTI = 158,500 + 35,500 + 6,000 = 200,000; base 59,800 × 26% = 15,548.
    Minimum tax credit = 24,294 − 15,548 = 8,746 (12,000 carried in)."""
    r = _run(fed, taxpayer={"filing_status": "married_filing_jointly",
                            "state": "", "birth_date": "1958-04-01"},
             spouse={"birth_date": "1960-09-30"},
             income={"wages": {"taxpayer_w2": "120000"},
                     "retirement": {"pension": "80000"}},
             carryovers={"amt_credit": "12000"})
    assert r.schedule_1a_deduction == Money(6_000)
    assert r.trace.get("fed.credits.amt").amount == Money(8_746)


def test_minimum_tax_credit_nets_other_credits_before_tmt(fed):
    """MFJ, wages 300,000, one child. Regular tax 35,932 + 24% × 56,400 =
    49,468; CTC 2,200. TMT 26% × (300,000 − 140,200) = 41,548.
    Form 8801 line 22 = 49,468 − 2,200 = 47,268; line 24 = 5,720."""
    r = _run(fed, taxpayer={"filing_status": "married_filing_jointly", "state": ""},
             dependents=[{"name": "a", "birth_date": "2012-01-15",
                          "relationship": "child"}],
             income={"wages": {"taxpayer_w2": "300000"}},
             carryovers={"amt_credit": "20000"})
    assert r.trace.get("fed.credits.amt").amount == Money(5_720)
    assert any("$14,280" in w for w in r.warnings)
