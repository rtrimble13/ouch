"""The 2026 federal data file against its primary sources (rtrimble13/ouch#22).

Two kinds of check:

- Identities inside Rev. Proc. 2025-32 itself. Its rate tables print the tax
  at each bracket floor, its EITC table prints the completed phase-out
  amounts, and its AMT table prints the complete phase-out of the exemption.
  Those are independent figures, so recomputing them from the brackets and
  rates in the data file catches a mistyped number.
- Hand-computed returns, with the working in each docstring.
"""

from decimal import ROUND_HALF_UP, Decimal

import pytest

from ouch.engine import pipeline
from ouch.engine.brackets import apply_brackets
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


# ----- identities inside Rev. Proc. 2025-32 --------------------------------

# §4.01 Tables 1–4: "If taxable income is over $X … the tax is $Y plus …"
RATE_TABLE_FLOORS = {
    F.MARRIED_FILING_JOINTLY: [(24_800, "2480"), (100_800, "11600"), (211_400, "35932"),
                               (403_550, "82048"), (512_450, "116896"),
                               (768_700, "206583.50")],
    F.HEAD_OF_HOUSEHOLD: [(17_700, "1770"), (67_450, "7740"), (105_700, "16155"),
                          (201_750, "39207"), (256_200, "56631"), (640_600, "191171")],
    F.SINGLE: [(12_400, "1240"), (50_400, "5800"), (105_700, "17966"),
               (201_775, "41024"), (256_225, "58448"), (640_600, "192979.25")],
    F.MARRIED_FILING_SEPARATELY: [(12_400, "1240"), (50_400, "5800"), (105_700, "17966"),
                                  (201_775, "41024"), (256_225, "58448"),
                                  (384_350, "103291.75")],
}
RATE_TABLE_FLOORS[F.QUALIFYING_SURVIVING_SPOUSE] = RATE_TABLE_FLOORS[F.MARRIED_FILING_JOINTLY]


@pytest.mark.parametrize("status", list(RATE_TABLE_FLOORS))
def test_brackets_reproduce_the_rate_tables(fed, status):
    for taxable, tax in RATE_TABLE_FLOORS[status]:
        got = apply_brackets(Money(taxable), fed.ordinary_brackets[status]).round_cent()
        assert got == Money(tax), (status, taxable)


# §4.06: completed phase-out amounts (MFJ, other), by number of children
EITC_COMPLETED = {0: (26_820, 19_540), 1: (58_863, 51_593),
                  2: (65_899, 58_629), 3: (70_244, 62_974)}


def test_eitc_table_is_internally_consistent(fed):
    for tier in fed.credits.eitc.by_children:
        max_credit = (tier.phase_in_rate * tier.earned_income_amount).quantize(
            Decimal(1), ROUND_HALF_UP)
        assert max_credit == tier.max_credit
        mfj, other = EITC_COMPLETED[tier.children]
        span = tier.max_credit / tier.phaseout_rate
        assert (tier.phaseout_start_mfj + span).quantize(Decimal(1)) == mfj
        assert (tier.phaseout_start_other + span).quantize(Decimal(1)) == other


@pytest.mark.parametrize("status, complete", [
    (F.MARRIED_FILING_JOINTLY, 1_280_400),
    (F.SINGLE, 680_200),
    (F.MARRIED_FILING_SEPARATELY, 640_200),
])
def test_amt_phaseout_rate_is_50_percent(fed, status, complete):
    """§4.10: the exemption is gone at threshold + 2 × exemption."""
    amt = fed.amt
    assert amt.phaseout_threshold[status] + amt.exemption[status] / amt.phaseout_rate == complete


def test_qbi_phase_in_ends(fed):
    """§4.26 prints the end of the phase-in range; the file stores its width."""
    q = fed.qbi
    assert q.threshold[F.MARRIED_FILING_JOINTLY] + q.phase_in_range[F.MARRIED_FILING_JOINTLY] == 553_500
    assert q.threshold[F.MARRIED_FILING_SEPARATELY] + q.phase_in_range[F.MARRIED_FILING_SEPARATELY] == 276_775
    for status in (F.SINGLE, F.HEAD_OF_HOUSEHOLD, F.QUALIFYING_SURVIVING_SPOUSE):
        assert q.threshold[status] + q.phase_in_range[status] == 276_750


# ----- hand-computed returns ------------------------------------------------

def test_single_wages_100k(data):
    """taxable = 100,000 − 16,100 = 83,900
    tax = 5,800 + 22% × (83,900 − 50,400) = 5,800 + 7,370 = 13,170.00"""
    r = _run(data, income={"wages": {"taxpayer_w2": "100000"}})
    assert r.deduction_taken == Money(16_100)
    assert r.taxable_income == Money(83_900)
    assert r.federal_total_tax.round_cent() == Money("13170.00")


def test_mfj_two_children_ctc_2200(data):
    """MFJ, wages 200,000, children born 2015 and 2018.
    taxable = 200,000 − 32,200 = 167,800
    tax = 11,600 + 22% × 67,000 (14,740) = 26,340
    CTC 2 × 2,200 = 4,400 (AGI under 400,000) → 21,940.00"""
    kids = [{"name": "a", "birth_date": "2015-05-01", "relationship": "child"},
            {"name": "b", "birth_date": "2018-05-01", "relationship": "child"}]
    r = _run(data, taxpayer={"filing_status": "married_filing_jointly", "state": ""},
             dependents=kids, income={"wages": {"taxpayer_w2": "200000"}})
    assert r.taxable_income == Money(167_800)
    assert r.federal_total_tax.round_cent() == Money("21940.00")


def test_salt_phasedown_2026_parameters(data):
    """MFJ, wages 600,000, SALT 50,000, mortgage interest 30,000.
    cap = 40,400 − 30% × (600,000 − 505,000) = 40,400 − 28,500 = 11,900
    itemized = 11,900 + 30,000 = 41,900 (> standard 32,200)
    taxable = 558,100; tax = 116,896 + 35% × 45,650 (15,977.50) = 132,873.50
    Additional Medicare = 0.9% × 350,000 = 3,150 → 136,023.50
    (AMT: AMTI 570,000 − 140,200 = 429,800 → TMT 115,454 < regular tax)"""
    r = _run(data, taxpayer={"filing_status": "married_filing_jointly", "state": ""},
             income={"wages": {"taxpayer_w2": "600000"}},
             deductions={"itemized": {"state_local_income_tax": "35000",
                                      "real_estate_tax": "15000",
                                      "mortgage_interest": "30000"}})
    assert r.deduction_taken == Money(41_900)
    assert r.taxable_income == Money(558_100)
    assert r.amt_additional == ZERO
    assert r.federal_total_tax.round_cent() == Money("136023.50")


def test_salt_below_threshold_gets_full_40400(data):
    """MFJ, wages 400,000: SALT 50,000 capped at the full 40,400."""
    r = _run(data, taxpayer={"filing_status": "married_filing_jointly", "state": ""},
             income={"wages": {"taxpayer_w2": "400000"}},
             deductions={"itemized": {"state_local_income_tax": "35000",
                                      "real_estate_tax": "15000"}})
    assert r.deduction_taken == Money(40_400)


def test_self_employment_wage_base_184500(data):
    """Single, Schedule C 200,000, no wages.
    net SE earnings = 92.35% × 200,000 = 184,700
    SE tax = 12.4% × 184,500 (22,878.00) + 2.9% × 184,700 (5,356.30) = 28,234.30"""
    r = _run(data, income={"business": {"schedule_c_net": "200000"}})
    assert r.se_tax.round_cent() == Money("28234.30")


def test_additional_medicare_qss_threshold_is_200k(data):
    """QSS, wages 220,000: 0.9% × (220,000 − 200,000) = 180.00.
    Form 8959 gives a qualifying surviving spouse $200,000, not the joint
    $250,000 the file used before."""
    kid = [{"name": "a", "birth_date": "2015-05-01", "relationship": "child"}]
    r = _run(data, taxpayer={"filing_status": "qualifying_surviving_spouse", "state": ""},
             dependents=kid, income={"wages": {"taxpayer_w2": "220000"}})
    assert r.additional_medicare.round_cent() == Money("180.00")


def test_amt_mfs_uses_half_the_28_percent_breakpoint(fed):
    """MFS, standard deduction 16,100, taxable 254,000:
    AMTI = 270,100; exemption 70,100 (no phase-out below 500,000)
    base 200,000 → 26% × 122,250 (31,785) + 28% × 77,750 (21,770) = 53,555
    (the all-status breakpoint of 244,500 would give 52,000)."""
    _, tmt = amt_additional(Money(254_000), ZERO, "standard", Money(16_100), ZERO,
                            F.MARRIED_FILING_SEPARATELY, fed.amt,
                            fed.preferential_brackets[F.MARRIED_FILING_SEPARATELY], ZERO)
    assert tmt == Money(53_555)


def test_eitc_one_child_plateau(data):
    """Single, one child, wages 13,020 (the earned income amount): 4,427."""
    kid = [{"name": "a", "birth_date": "2018-05-01", "relationship": "child"}]
    r = _run(data, taxpayer={"filing_status": "head_of_household", "state": ""},
             dependents=kid, income={"wages": {"taxpayer_w2": "13020"}})
    eitc = r.trace.get("fed.credits.eitc")
    assert eitc.amount == Money(4_427)
