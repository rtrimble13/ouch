"""A qualifying surviving spouse doesn't file a joint return.

Several rules give a higher amount only to "married taxpayers filing a joint
return". A qualifying surviving spouse (QSS) shares the joint *rate tables*
and standard deduction, but not those amounts. The engine wrongly treated
QSS as joint for three credits. These use the shipped 2025 file, since the
fix applies to every year.

2025 figures used: standard deduction 31,500 (QSS); MFJ/QSS brackets 10% to
23,850, 12% to 96,950.
"""

from ouch.engine import pipeline
from ouch.model.money import Money
from tests.conftest import make_input

KID = [{"name": "a", "birth_date": "2018-05-01", "relationship": "child"}]


def _qss(data, wages, **extra):
    raw = {"taxpayer": {"filing_status": "qualifying_surviving_spouse", "state": ""},
           "dependents": KID, "income": {"wages": {"taxpayer_w2": str(wages)}}}
    raw.update(extra)
    return pipeline.run(make_input(**raw), data, compute_marginals=False)


def test_eitc_uses_the_other_status_phaseout(data_federal_only):
    """One child, 2025: max 4,328; phase-out starts at 23,350 (other
    statuses), not 30,470 (joint returns), at 15.98%.
    wages 28,000: 4,328 − 15.98% × 4,650 (743.07) = 3,584.93.
    Rev. Proc. 2024-40 §3.07: the higher threshold is "for married taxpayers
    filing a joint return"."""
    r = _qss(data_federal_only, 28_000)
    assert r.trace.get("fed.credits.eitc").amount == Money("3584.93")


def test_lifetime_learning_credit_uses_the_other_range(data_federal_only):
    """LLC 20% × 10,000 = 2,000. MAGI 85,000 is halfway through the
    80,000–90,000 range → 1,000. (The joint range, 160,000–180,000, would
    allow all 2,000.) Form 8863: "$160,000 and $180,000 if you file a joint
    return". Regular tax 5,943 (taxable 53,500) is more than enough to
    absorb it."""
    r = _qss(data_federal_only, 85_000, expenses={"education_llc": "10000"})
    assert r.trace.get("fed.credits.llc").amount == Money(1_000)


def test_savers_credit_uses_the_single_column(data_federal_only):
    """Wages 41,000, traditional IRA 2,000 → AGI 39,000.
    2025 tiers, "all other" column: 10% up to 39,500 → 10% × 2,000 = 200.
    The joint column (50% up to 47,500) would give 1,000, capped at the 750
    of tax (taxable 7,500). Form 8880 groups "Single, Married filing
    separately, or Qualifying surviving spouse" in one column."""
    r = _qss(data_federal_only, 41_000, adjustments={"traditional_ira": "2000"})
    assert r.agi == Money(39_000)
    assert r.trace.get("fed.credits.saver").amount == Money(200)
