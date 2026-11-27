"""2026 rule changes that need engine or schema work (rtrimble13/ouch#25).

Sources are cited per test. Hand computations use the 2026 file (Rev. Proc.
2025-32): standard deduction 16,100 single / 32,200 MFJ; single brackets 10%
to 12,400, 12% to 50,400, 22% to 105,700.
"""

import pytest

from ouch.engine import pipeline
from ouch.engine.federal import amt_additional
from ouch.engine.pipeline import ResolvedData
from ouch.model.enums import FilingStatus as F
from ouch.model.money import Money, ZERO
from ouch.taxdata import loader
from tests.conftest import make_input


@pytest.fixture(scope="module")
def fed():
    return loader.load_federal(2026)


@pytest.fixture(scope="module")
def data(fed):
    return ResolvedData(federal=fed)


def _run(data, **raw):
    raw.setdefault("tax_year", 2026)
    return pipeline.run(make_input(**raw), data, compute_marginals=False)


# ----- AMT: the engine applies the data's 50% phase-out (OBBBA §70107) -----

def test_amt_exemption_phases_out_at_50_percent(fed):
    """Single, standard deduction 16,100, taxable 583,900 → AMTI 600,000.
    exemption = 90,100 − 50% × (600,000 − 500,000) = 40,100
    base 559,900 → 26% × 244,500 (63,570) + 28% × 315,400 (88,312) = 151,882.
    At the pre-2026 25% rate above 626,350 the exemption would have been the
    full 90,100 and TMT 137,854: the engine needs no change, only the data."""
    _, tmt = amt_additional(Money(583_900), ZERO, "standard", Money(16_100), ZERO,
                            F.SINGLE, fed.amt, fed.preferential_brackets[F.SINGLE], ZERO)
    assert tmt == Money(151_882)


# ----- Child tax credit: SSN requirement disclosed (OBBBA §70104) ----------

def test_ctc_discloses_the_ssn_assumption(data):
    """2026 Form 1040-ES: the claimant needs an SSN valid for employment
    (one spouse is enough on a joint return). ouch has no SSN inputs."""
    kid = [{"name": "a", "birth_date": "2018-05-01", "relationship": "child"}]
    r = _run(data, dependents=kid, income={"wages": {"taxpayer_w2": "80000"}})
    assert r.credits_nonrefundable > ZERO
    assert any("Social Security number valid for employment" in w for w in r.warnings)


def test_no_ssn_warning_without_children(data):
    r = _run(data, income={"wages": {"taxpayer_w2": "80000"}})
    assert not any("valid for employment" in w for w in r.warnings)


# ----- Child and dependent care credit: the 2026 rate schedule (OBBBA §70405) -

# Draft 2026 Instructions for Form 2441, line 8, "2026 Phaseout Schedule":
# (over, not over, decimal) — joint returns, then any other filing status.
_FIRST = [(0, 15_000, "0.50")] + [
    (15_000 + 2_000 * i, 17_000 + 2_000 * i, f"0.{49 - i}") for i in range(14)]
SCHEDULE_MFJ = _FIRST + [(43_000, 150_000, "0.35")] + [
    (150_000 + 4_000 * i, 154_000 + 4_000 * i, f"0.{34 - i}") for i in range(14)] + [
    (206_000, 10_000_000, "0.20")]
SCHEDULE_OTHER = _FIRST + [(43_000, 75_000, "0.35")] + [
    (75_000 + 2_000 * i, 77_000 + 2_000 * i, f"0.{34 - i}") for i in range(14)] + [
    (103_000, 10_000_000, "0.20")]


def test_schedule_transcription_matches_the_printed_rows():
    """Spot-check the generated rows against lines printed in the draft."""
    assert (41_000, 43_000, "0.36") in SCHEDULE_MFJ
    assert (150_000, 154_000, "0.34") in SCHEDULE_MFJ
    assert (202_000, 206_000, "0.21") in SCHEDULE_MFJ
    assert (101_000, 103_000, "0.21") in SCHEDULE_OTHER
    assert len(SCHEDULE_MFJ) == len(SCHEDULE_OTHER) == 31


def _care_rate(fed, status, agi):
    from decimal import Decimal
    from ouch.engine.credits import dependent_care_credit
    inp = make_input(tax_year=2026,
                     taxpayer={"filing_status": status, "state": ""},
                     dependents=[{"name": "a", "birth_date": "2020-01-01",
                                  "relationship": "child"}],
                     expenses={"dependent_care": "3000"})
    credit = dependent_care_credit(inp, Money(agi), Money(1_000_000), fed)
    return (credit.amount / Decimal(3000)).quantize(Decimal("0.01"))


@pytest.mark.parametrize("status, schedule", [
    ("married_filing_jointly", SCHEDULE_MFJ),
    ("single", SCHEDULE_OTHER),
    ("head_of_household", SCHEDULE_OTHER),
    ("qualifying_surviving_spouse", SCHEDULE_OTHER),   # "any other filing status"
])
def test_care_rate_matches_every_row_of_the_2026_schedule(fed, status, schedule):
    from decimal import Decimal
    for over, not_over, rate in schedule:
        for agi in (over + 1, min(not_over, 9_000_000)):
            assert _care_rate(fed, status, agi) == Decimal(rate), (status, agi)


def test_care_credit_through_the_pipeline(data):
    """MFJ, wages 160,000, two children under 13, care expenses 6,000.
    Rate: 35% after the first tier; 10,000 over 150,000 → 3 steps of $4,000
    (rounded up) → 32%. Credit 32% × 6,000 = 1,920 (2025's schedule would
    give its 20% floor: 1,200)."""
    kids = [{"name": "a", "birth_date": "2018-01-01", "relationship": "child"},
            {"name": "b", "birth_date": "2021-01-01", "relationship": "child"}]
    r = _run(data, taxpayer={"filing_status": "married_filing_jointly", "state": ""},
             dependents=kids, income={"wages": {"taxpayer_w2": "160000"}},
             expenses={"dependent_care": "6000"})
    assert r.trace.get("fed.credits.care").amount == Money(1_920)


# ----- QBI minimum deduction (§199A(i), OBBBA §70105) ----------------------

def _qbi_case(data, year=2026, **business):
    biz = {"schedule_c_net": "1500", "qbi_eligible_income": "1500"}
    biz.update(business)
    return _run(data, tax_year=year, income={"wages": {"taxpayer_w2": "30000"},
                                             "business": biz})


def test_qbi_minimum_lifts_a_small_deduction_to_400(data):
    """Single, wages 30,000, Schedule C 1,500 (all QBI).
    SE tax = 15.3% × (92.35% × 1,500 = 1,385.25) = 211.94325; half 105.971625
    QBI = 1,500 − 105.971625 = 1,394.028375 (≥ 1,000, active)
    20% × QBI = 278.81; taxable-income limit 20% × 15,294.03 = 3,058.81
    Draft 2026 Form 8995 line 17: the greater of 278.81 and 400 → 400."""
    r = _qbi_case(data)
    assert r.qbi_deduction == Money(400)
    assert any("minimum for active qualified business income" in w for w in r.warnings)


def test_qbi_minimum_needs_material_participation(data):
    """Passive QBI doesn't count (draft 2026 Instructions for Form 8995,
    line 16): the deduction stays 20% × 1,394.028375 = 278.81."""
    r = _qbi_case(data, material_participation=False)
    assert r.qbi_deduction.round_cent() == Money("278.81")


def test_qbi_minimum_needs_1000_of_active_qbi(data):
    """Schedule C 1,000: QBI = 1,000 − ½ SE tax (70.647875) = 929.35 < 1,000,
    so no minimum: 20% × 929.352125 = 185.87."""
    r = _qbi_case(data, schedule_c_net="1000", qbi_eligible_income="1000")
    assert r.qbi_deduction.round_cent() == Money("185.87")


def test_qbi_minimum_not_in_2025(federal_2025):
    """The 2025 file has no minimum_deduction section, so a 2025 return
    keeps the computed amount."""
    assert federal_2025.qbi.minimum_deduction is None
    r = _qbi_case(ResolvedData(federal=federal_2025), year=2025)
    assert r.qbi_deduction < Money(400)
