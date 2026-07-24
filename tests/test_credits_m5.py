"""M5 credit suite: EITC, dependent care, education, saver's — every
expected value hand-computed from the 2025 parameters in the data file.
"""

from decimal import Decimal

import pytest

from ouch.engine import pipeline
from ouch.model.money import Money, ZERO
from tests.conftest import make_input


def run(data, **kw):
    return pipeline.run(make_input(**kw), data, compute_marginals=False)


# ----- EITC -----------------------------------------------------------------


def test_eitc_plateau_one_child(data_federal_only):
    """Single, 1 child, earned 20,000 (AGI 20,000): plateau region —
    min(20,000×34%, 4,328) = 4,328, phaseout starts at 23,350 > 20,000."""
    r = run(data_federal_only,
            dependents=[{"name": "k", "birth_date": "2018-01-01",
                         "relationship": "child"}],
            income={"wages": {"taxpayer_w2": "20000"}})
    eitc = r.trace.get("fed.credits.eitc")
    assert eitc.amount == Money(4_328)


def test_eitc_phaseout_one_child(data_federal_only):
    """Earned/AGI 30,000: 4,328 − (30,000 − 23,350) × 15.98% = 4,328 −
    1,062.67 = 3,265.33."""
    r = run(data_federal_only,
            dependents=[{"name": "k", "birth_date": "2018-01-01",
                         "relationship": "child"}],
            income={"wages": {"taxpayer_w2": "30000"}})
    assert r.trace.get("fed.credits.eitc").amount == Money("3265.33")


def test_eitc_childless_phase_in(data_federal_only):
    """No children, earned 5,000: 5,000 × 7.65% = 382.50 (below the 649
    max; phaseout starts at 10,620)."""
    r = run(data_federal_only, income={"wages": {"taxpayer_w2": "5000"}})
    assert r.trace.get("fed.credits.eitc").amount == Money("382.50")
    # Refundable: drives the federal total negative
    assert r.federal_total_tax < ZERO


def test_eitc_investment_income_limit(data_federal_only):
    """Investment income above $11,950 disqualifies entirely."""
    r = run(data_federal_only,
            dependents=[{"name": "k", "birth_date": "2018-01-01",
                         "relationship": "child"}],
            income={"wages": {"taxpayer_w2": "20000"},
                    "investment": {"interest": "12000"}})
    assert not r.trace.has("fed.credits.eitc")
    assert any("investment income" in w for w in r.warnings)


def test_eitc_mfs_ineligible(data_federal_only):
    r = run(data_federal_only,
            taxpayer={"filing_status": "married_filing_separately",
                      "state": ""},
            income={"wages": {"taxpayer_w2": "20000"}})
    assert not r.trace.has("fed.credits.eitc")


def test_eitc_student_child_under_24_qualifies(data_federal_only):
    """A 20-year-old student counts for EITC (not for CTC)."""
    r = run(data_federal_only,
            dependents=[{"name": "k", "birth_date": "2005-06-01",
                         "relationship": "child", "student": True}],
            income={"wages": {"taxpayer_w2": "20000"}})
    assert r.trace.get("fed.credits.eitc").amount == Money(4_328)


# ----- Child & dependent care ----------------------------------------------


def test_dependent_care_credit_rate_floor(data_federal_only):
    """AGI 100,000 → rate floored at 20%. One child under 13, 5,000 of
    expenses → min(5,000, 3,000) × 20% = 600, nonrefundable."""
    r = run(data_federal_only,
            dependents=[{"name": "k", "birth_date": "2018-01-01",
                         "relationship": "child"}],
            income={"wages": {"taxpayer_w2": "100000"}},
            expenses={"dependent_care": "5000"})
    assert r.trace.get("fed.credits.care").amount == Money(600)


def test_dependent_care_max_rate_low_agi(data_federal_only):
    """AGI 15,000 → full 35% rate: 2,000 expenses × 35% = 700, but clamped
    to the (small) income-tax liability."""
    r = run(data_federal_only,
            dependents=[{"name": "k", "birth_date": "2018-01-01",
                         "relationship": "child"}],
            income={"wages": {"taxpayer_w2": "15000"}},
            expenses={"dependent_care": "2000"})
    # taxable 0 (15,000 − 15,000 std) → liability 0 → credit fully clamped
    assert not r.trace.has("fed.credits.care")
    assert any("lost to the liability limit" in w for w in r.warnings)


def test_dependent_care_two_children_cap(data_federal_only):
    r = run(data_federal_only,
            dependents=[{"name": "a", "birth_date": "2018-01-01",
                         "relationship": "child"},
                        {"name": "b", "birth_date": "2020-01-01",
                         "relationship": "child"}],
            income={"wages": {"taxpayer_w2": "100000"}},
            expenses={"dependent_care": "10000"})
    # cap 6,000 × 20% = 1,200
    assert r.trace.get("fed.credits.care").amount == Money(1_200)


# ----- Education ------------------------------------------------------------


def test_aotc_full_split(data_federal_only):
    """MAGI 70,000 (below phaseout), 4,000 expenses:
    100%×2,000 + 25%×2,000 = 2,500 → 1,000 refundable + 1,500 nonref."""
    r = run(data_federal_only,
            income={"wages": {"taxpayer_w2": "70000"}},
            expenses={"education_aotc": "4000"})
    assert r.trace.get("fed.credits.aotc").amount == Money(1_500)
    assert r.trace.get("fed.credits.aotc_refundable").amount == Money(1_000)


def test_aotc_phased_out(data_federal_only):
    """Single MAGI 100,000 ≥ 90,000 end → zero."""
    r = run(data_federal_only,
            income={"wages": {"taxpayer_w2": "100000"}},
            expenses={"education_aotc": "4000"})
    assert not r.trace.has("fed.credits.aotc")


def test_aotc_partial_phaseout(data_federal_only):
    """Single MAGI 85,000: halfway through 80k–90k → 2,500 × 0.5 = 1,250
    (750 nonref + 500 refundable)."""
    r = run(data_federal_only,
            income={"wages": {"taxpayer_w2": "85000"}},
            expenses={"education_aotc": "4000"})
    assert r.trace.get("fed.credits.aotc").amount == Money(750)
    assert r.trace.get("fed.credits.aotc_refundable").amount == Money(500)


def test_llc_credit(data_federal_only):
    """MAGI 70,000, 10,000 expenses → 20% = 2,000 nonrefundable."""
    r = run(data_federal_only,
            income={"wages": {"taxpayer_w2": "70000"}},
            expenses={"education_llc": "10000"})
    assert r.trace.get("fed.credits.llc").amount == Money(2_000)


# ----- Saver's credit -------------------------------------------------------


def test_savers_credit_10pct_tier_fully_used(data_federal_only):
    """Single wages 38,000 − 3,000 IRA = AGI 35,000 ≤ 39,500 (10% tier)
    → 10% × min(2,000, 3,000) = 200; taxable 20,000 gives ample liability."""
    r = run(data_federal_only,
            income={"wages": {"taxpayer_w2": "38000"}},
            adjustments={"traditional_ira": "3000"})
    assert r.trace.get("fed.credits.saver").amount == Money(200)


def test_savers_credit_clamped_by_liability(data_federal_only):
    """Wages 23,000 − 3,000 IRA = AGI 20,000 → 1,000 gross credit, but
    taxable is only 5,000 → 500 of liability → 500 used, 500 lost."""
    r = run(data_federal_only,
            income={"wages": {"taxpayer_w2": "23000"}},
            adjustments={"traditional_ira": "3000"})
    assert r.trace.get("fed.credits.saver").amount == Money(500)
    assert any("saver's credit lost" in w for w in r.warnings)


def test_savers_credit_above_all_tiers(data_federal_only):
    r = run(data_federal_only,
            income={"wages": {"taxpayer_w2": "60000"}},
            adjustments={"traditional_ira": "3000"})
    assert not r.trace.has("fed.credits.saver")


# ----- interactions ---------------------------------------------------------


def test_nonrefundable_cascade_clamps_in_order(data_federal_only):
    """When liability runs out mid-cascade, later credits report residue and
    the total never goes below zero from nonrefundable credits alone."""
    r = run(data_federal_only,
            dependents=[{"name": "k", "birth_date": "2018-01-01",
                         "relationship": "child"}],
            income={"wages": {"taxpayer_w2": "24000"}},
            adjustments={"traditional_ira": "2000"},
            expenses={"dependent_care": "3000", "education_llc": "10000"})
    assert r.credits_nonrefundable <= (r.tax_ordinary + r.tax_preferential
                                       + r.amt_additional)
    # EITC/ACTC refundable still flow
    assert r.credits_refundable > ZERO


def test_ctc_still_works_after_refactor(data_federal_only):
    """M1 behavior preserved through the orchestrator: 1 child, AGI 150k →
    full 2,000 nonrefundable CTC."""
    r = run(data_federal_only,
            dependents=[{"name": "k", "birth_date": "2016-02-01",
                         "relationship": "child"}],
            income={"wages": {"taxpayer_w2": "150000"}})
    assert r.credits_nonrefundable == Money(2_000)
