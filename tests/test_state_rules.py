"""State data features added for rtrimble13/ouch#28: exemption credits with an
AGI phase-out (California), AGI-gated and limit-reduced modifications
(Colorado), and status-dependent, income-limited and scheduled credits (the
NYC school tax credits).

Figures: FTB 2025 Personal Income Tax Booklet (Form 540 lines 7–10 and the
line 32 AGI Limitation Worksheet); CO DOR Individual Income Tax Guide (rev.
January 2026) Part 3; NY DTF IT-201-I (2025) lines 69 and 69a.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from ouch.engine import pipeline
from ouch.engine.state import exemption_credits
from ouch.model.money import Money, ZERO
from ouch.taxdata import loader
from ouch.taxdata.schema import ExemptionCredits, Modification, StateCredit
from tests.conftest import make_input

CA = ExemptionCredits.model_validate({
    "personal": 153, "senior": 153, "blind": 153, "dependent": 475,
    "phaseout": {"threshold": {"single": 252_203, "married_filing_jointly": 504_411,
                               "married_filing_separately": 252_203,
                               "head_of_household": 378_310,
                               "qualifying_surviving_spouse": 504_411},
                 "step": 2_500, "step_mfs": 1_250, "reduction_per_step": 6}})


def _inp(status="single", year=2025, **raw):
    return make_input(tax_year=year, taxpayer={"filing_status": status, "state": "",
                                               **raw.pop("taxpayer", {})}, **raw)


KID = {"name": "a", "birth_date": "2016-01-01", "relationship": "child"}


def test_exemption_credits_count_filers_seniors_blind_and_dependents():
    """MFJ, both 65+, one blind, two children, AGI under the threshold:
    2 × 153 + 2 × 153 (senior) + 153 (blind) + 2 × 475 = 1,715."""
    inp = _inp("married_filing_jointly",
               taxpayer={"birth_date": "1955-01-01", "blind": True},
               spouse={"birth_date": "1958-01-01"}, dependents=[KID, KID])
    assert exemption_credits(inp, Money(200_000), CA) == Money(1_715)


def test_qss_gets_two_personal_credits():
    """Form 540 line 7: box 2 or 5 (joint, qualifying surviving spouse) → 2."""
    inp = _inp("qualifying_surviving_spouse", dependents=[KID])
    assert exemption_credits(inp, Money(100_000), CA) == Money(2 * 153 + 475)


def test_exemption_credit_phaseout_by_steps_of_2500_rounded_up():
    """Single, AGI 300,000: 47,797 over → 19.12 → 20 steps × $6 = 120;
    153 − 120 = 33."""
    assert exemption_credits(_inp(), Money(300_000), CA) == Money(33)


def test_exemption_credit_phaseout_mfs_uses_1250_steps():
    """MFS, AGI 260,000: 7,797 over → 6.24 → 7 steps × 6 = 42; 153 − 42."""
    assert exemption_credits(_inp("married_filing_separately"), Money(260_000), CA) \
        == Money(111)


def test_dependent_credits_phase_out_separately_and_floor_at_zero():
    """Single, one child, AGI 400,000: 147,797 over → 60 steps × 6 = 360.
    Personal 153 − 360 → 0; dependent 475 − 360 = 115."""
    inp = _inp(dependents=[KID])
    assert exemption_credits(inp, Money(400_000), CA) == Money(115)


# ----- Colorado modifications ----------------------------------------------

def _co(year, wages, **income):
    raw = {"tax_year": year, "taxpayer": {"filing_status": "single", "state": "CO"},
           "income": {"wages": {"taxpayer_w2": str(wages), **income}}}
    data = pipeline.ResolvedData(federal=loader.load_federal(year),
                                 state=loader.load_state("CO", year))
    return pipeline.run(make_input(**raw), data, compute_marginals=False)


def test_co_deduction_addback_only_above_300000_agi():
    """2025: AGI 300,000 isn't over the threshold; AGI 300,001 is, adding
    back 15,750 − 12,000 = 3,750."""
    at = _co(2025, 300_000)
    over = _co(2025, 300_001)
    assert at.state.agi == at.taxable_income
    assert over.state.agi == over.taxable_income + Money(3_750)


def test_co_2026_deduction_limit_is_1000():
    """2026, AGI 400,000: 16,100 − 1,000 = 15,100 added back."""
    r = _co(2026, 400_000)
    assert r.state.agi == r.taxable_income + Money(15_100)


def test_co_2026_adds_back_overtime_not_tips():
    """Wages 100,000 with 5,000 overtime and 4,000 tips: only the 5,000
    overtime deduction comes back (no deduction addback below 300,000)."""
    r = _co(2026, 100_000, taxpayer_qualified_overtime="5000",
            taxpayer_qualified_tips="4000")
    assert r.schedule_1a_deduction == Money(9_000)
    assert r.state.agi == r.taxable_income + Money(5_000)


def test_co_2025_has_no_overtime_addback():
    r = _co(2025, 100_000, taxpayer_qualified_overtime="5000")
    assert r.state.agi == r.taxable_income


def test_modification_thresholds_need_every_status():
    with pytest.raises(ValidationError, match="min_agi missing"):
        Modification.model_validate({"id": "x", "label": "x", "min_agi": {"single": 1}})


# ----- NYC school tax credits -----------------------------------------------

def _nyc(status, wages, ira="0"):
    raw = {"tax_year": 2025,
           "taxpayer": {"filing_status": status, "state": "NY", "locality": "NYC"},
           "income": {"wages": {"taxpayer_w2": str(wages)},
                      "retirement": {"ira_distributions": ira}}}
    data = pipeline.ResolvedData(federal=loader.load_federal(2025),
                                 state=loader.load_state("NY", 2025),
                                 local=loader.load_local("NYC", 2025))
    return pipeline.run(make_input(**raw), data, compute_marginals=False)


def test_nyc_credits_single():
    """Single, wages 100,000: NY taxable 92,000. Fixed 63; rate reduction
    0.171% × 12,000 + 0.228% × 80,000 = 20.52 + 182.40 = 202.92."""
    r = _nyc("single", 100_000)
    assert r.local.credits == Money("265.92")


def test_nyc_fixed_credit_is_125_joint():
    """MFJ, wages 100,000: NY taxable 83,950. Fixed 125; rate reduction
    0.171% × 21,600 + 0.228% × 62,350 = 36.936 + 142.158 = 179.094."""
    r = _nyc("married_filing_jointly", 100_000)
    assert r.local.credits == Money("304.094")


def test_nyc_fixed_credit_lost_over_250000_rate_reduction_kept():
    """Single, wages 300,000: no fixed credit; NY taxable 292,000 →
    20.52 + 0.228% × 280,000 (638.40) = 658.92."""
    r = _nyc("single", 300_000)
    assert r.local.credits == Money("658.92")


def test_nyc_income_test_excludes_ira_distributions():
    """AGI 260,000 of which 20,000 is IRA distributions: income 240,000,
    so the fixed credit still applies. NY taxable 252,000 →
    63 + 20.52 + 0.228% × 240,000 (547.20) = 630.72."""
    r = _nyc("single", 240_000, ira="20000")
    assert r.agi == Money(260_000)
    assert r.local.credits == Money("630.72")


def test_nyc_no_credits_over_500000():
    assert _nyc("single", 600_000).local.credits == ZERO


def test_scheduled_credit_needs_every_status():
    with pytest.raises(ValidationError, match="schedule missing"):
        StateCredit.model_validate({"id": "x", "schedule": {"single": [{"rate": 0.01}]}})


def test_ca_surtax_folded_into_brackets():
    """1% Behavioral Health Services Tax: the top single rate above
    $1,000,000 is 12.3% + 1%."""
    ca = loader.load_state("CA", 2025)
    top = ca.brackets["single"][-2:]
    assert top[0].up_to == Decimal(1_000_000) and top[1].rate == Decimal("0.133")
