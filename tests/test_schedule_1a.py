"""Schedule 1-A tips, overtime and car-loan interest deductions, 2025–2028
(rtrimble13/ouch#26).

Rules from Schedule 1-A (Form 1040) (2025):
  Part II tips      line 7 cap $25,000 per return; line 9 $150,000 ($300,000
                    MFJ); lines 11–12 $100 per $1,000 over, step count
                    rounded DOWN; joint return required if married.
  Part III overtime line 15 cap $12,500 ($25,000 MFJ); same phase-out as tips;
                    joint return required if married.
  Part IV car loan  line 24 cap $10,000; line 26 $100,000 ($200,000 MFJ);
                    lines 28–29 $200 per $1,000, step count rounded UP; no
                    joint-return condition.
MAGI is line 3 (taken as AGI). All flow to Form 1040 line 13b, below AGI.
2026 uses the same amounts (2026 Form 1040-ES, What's New).

Hand computations use the 2025 file: standard deduction 15,750 (single),
31,500 (MFJ); single brackets 10% to 11,925, 12% to 48,475.
"""

import pytest
from pydantic import ValidationError

from ouch.engine import pipeline
from ouch.engine.deductions import phased_deduction
from ouch.engine.pipeline import ResolvedData
from ouch.model.enums import FilingStatus as F
from ouch.model.money import Money, ZERO
from ouch.taxdata import loader
from tests.conftest import make_input


def _run(data, box1, status="single", year=2025, **extra):
    raw = {"tax_year": year,
           "taxpayer": {"filing_status": status, "state": ""},
           "income": {"wages": {"taxpayer_w2": str(box1)}}}
    for key, value in extra.items():
        if key == "wages":
            raw["income"]["wages"].update(value)
        else:
            raw.setdefault(key, {}).update(value)
    return pipeline.run(make_input(**raw), data, compute_marginals=False)


def _tips(fed):
    return fed.schedule_1a.tips


# ----- the phased-deduction arithmetic -------------------------------------

@pytest.mark.parametrize("magi, expected", [
    (150_000, 10_000),   # at the threshold: no reduction
    (160_500, 9_000),    # 10,500 over → 10 steps (rounded down) × 100
    (160_999, 9_000),    # 10,999 → still 10
    (161_000, 8_900),    # 11,000 → 11
    (300_000, 0),        # 150 steps × 100 = 15,000 > 10,000 → 0
])
def test_tips_phaseout_rounds_steps_down(federal_2025, magi, expected):
    got = phased_deduction(Money(10_000), Money(magi), F.SINGLE, _tips(federal_2025))
    assert got == Money(expected)


@pytest.mark.parametrize("magi, expected", [
    (100_000, 8_000),    # at the threshold
    (110_000, 6_000),    # exactly 10 steps × 200
    (110_500, 5_800),    # 10,500 over → 11 steps (rounded UP) × 200
    (100_001, 7_800),    # 1 dollar over → 1 step
    (150_000, 0),        # 50 steps × 200 = 10,000 > 8,000 → 0
])
def test_car_loan_phaseout_rounds_steps_up(federal_2025, magi, expected):
    sec = federal_2025.schedule_1a.car_loan_interest
    assert phased_deduction(Money(8_000), Money(magi), F.SINGLE, sec) == Money(expected)


def test_overtime_cap_and_phaseout(federal_2025):
    """Single, overtime 15,000 capped at 12,500. MAGI 175,250: 25,250 over
    → 25 steps × 100 = 2,500 → 10,000."""
    sec = federal_2025.schedule_1a.overtime
    assert phased_deduction(Money(15_000), Money(100_000), F.SINGLE, sec) == Money(12_500)
    assert phased_deduction(Money(15_000), Money(175_250), F.SINGLE, sec) == Money(10_000)
    assert phased_deduction(Money(30_000), Money(100_000), F.MARRIED_FILING_JOINTLY,
                            sec) == Money(25_000)


# ----- through the pipeline --------------------------------------------------

def test_tips_under_cap_leaves_agi_alone(data_federal_only):
    """Single, wages 60,000 including 8,000 of qualified tips.
    AGI 60,000 (tips stay in box 1); deduction 8,000.
    taxable = 60,000 − 15,750 − 8,000 = 36,250
    tax = 1,192.50 + 12% × 24,325 (2,919.00) = 4,111.50"""
    r = _run(data_federal_only, 60_000, wages={"taxpayer_qualified_tips": "8000"})
    assert r.agi == Money(60_000)
    assert r.schedule_1a_deduction == Money(8_000)
    assert r.taxable_income == Money(36_250)
    assert r.federal_total_tax.round_cent() == Money("4111.50")


def test_tips_at_cap(data_federal_only):
    r = _run(data_federal_only, 80_000, wages={"taxpayer_qualified_tips": "30000"})
    assert r.schedule_1a_deduction == Money(25_000)


def test_tips_cap_is_per_return_on_mfj(data_federal_only):
    """MFJ, each spouse 15,000 of tips: 30,000 → the 25,000 return cap."""
    r = _run(data_federal_only, 60_000, status="married_filing_jointly",
             wages={"spouse_w2": "60000", "taxpayer_qualified_tips": "15000",
                    "spouse_qualified_tips": "15000"})
    assert r.schedule_1a_deduction == Money(25_000)


def test_overtime_mfj_cap_25000(data_federal_only):
    r = _run(data_federal_only, 90_000, status="married_filing_jointly",
             wages={"spouse_w2": "90000", "taxpayer_qualified_overtime": "15000",
                    "spouse_qualified_overtime": "15000"})
    assert r.schedule_1a_deduction == Money(25_000)


def test_tips_and_overtime_leave_additional_medicare_unchanged(data_federal_only):
    """Single, wages 250,000 including 20,000 of tips. The deduction is
    below AGI: Additional Medicare stays 0.9% × 50,000 = 450, and AGI stays
    250,000. Tips deduction: 100,000 over → 100 steps × 100 = 10,000 off
    20,000 → 10,000."""
    base = _run(data_federal_only, 250_000)
    tips = _run(data_federal_only, 250_000, wages={"taxpayer_qualified_tips": "20000"})
    assert tips.agi == base.agi == Money(250_000)
    assert tips.additional_medicare == base.additional_medicare == Money(450)
    assert tips.schedule_1a_deduction == Money(10_000)


def test_car_loan_interest_mfj_threshold(data_federal_only):
    """MFJ, wages 205,000, car-loan interest 10,000: 5,000 over 200,000 →
    5 steps × 200 = 1,000 → 9,000."""
    r = _run(data_federal_only, 205_000, status="married_filing_jointly",
             deductions={"car_loan_interest": "10000"})
    assert r.schedule_1a_deduction == Money(9_000)


def test_car_loan_interest_allowed_when_filing_separately(data_federal_only):
    """Part IV has no joint-return condition: MFS, wages 60,000 (under the
    100,000 threshold), interest 4,000 → 4,000."""
    r = _run(data_federal_only, 60_000, status="married_filing_separately",
             deductions={"car_loan_interest": "4000"})
    assert r.schedule_1a_deduction == Money(4_000)
    assert not any("car loan" in w and "separately" in w for w in r.warnings)


@pytest.mark.parametrize("field", ["taxpayer_qualified_tips", "taxpayer_qualified_overtime"])
def test_tips_and_overtime_denied_when_filing_separately(data_federal_only, field):
    r = _run(data_federal_only, 60_000, status="married_filing_separately",
             wages={field: "5000"})
    assert r.schedule_1a_deduction == ZERO
    assert any("filing separately" in w for w in r.warnings)


def test_all_three_with_trace(data_federal_only):
    """Single, wages 80,000 including tips 10,000 and overtime 5,000;
    car-loan interest 3,000. MAGI 80,000 is under every threshold.
    Schedule 1-A = 18,000; taxable = 80,000 − 15,750 − 18,000 = 46,250
    tax = 1,192.50 + 12% × 34,325 (4,119.00) = 5,311.50"""
    r = _run(data_federal_only, 80_000,
             wages={"taxpayer_qualified_tips": "10000",
                    "taxpayer_qualified_overtime": "5000"},
             deductions={"car_loan_interest": "3000"})
    assert r.schedule_1a_deduction == Money(18_000)
    assert r.taxable_income == Money(46_250)
    assert r.federal_total_tax.round_cent() == Money("5311.50")
    parent = r.trace.get("fed.schedule_1a")
    assert set(parent.inputs) == {"fed.deduction.tips", "fed.deduction.overtime",
                                  "fed.deduction.car_loan_interest"}
    assert r.trace.get("fed.deduction.tips").form_ref == "Schedule 1-A Part II"
    assert "rounded up" in r.trace.get("fed.deduction.car_loan_interest").rule
    joined = " ".join(r.warnings)
    assert "TippedOccupations" in joined and "premium portion" in joined
    assert "applicable passenger vehicle" in joined


def test_combines_with_senior_deduction(data_federal_only):
    """Single, born 1955 (70), wages 60,000 incl. 5,000 tips:
    senior 6,000 + tips 5,000 = 11,000 on line 13b."""
    r = _run(data_federal_only, 60_000, taxpayer={"birth_date": "1955-03-01"},
             wages={"taxpayer_qualified_tips": "5000"})
    assert r.schedule_1a_deduction == Money(11_000)
    assert set(r.trace.get("fed.schedule_1a").inputs) == {
        "fed.deduction.senior", "fed.deduction.tips"}


def test_2026_same_rules(federal_2025):
    """Single 2026, wages 80,000 incl. 10,000 tips.
    taxable = 80,000 − 16,100 − 10,000 = 53,900
    tax = 1,240 + 12% × 38,000 (4,560) + 22% × 3,500 (770) = 6,570.00"""
    data = ResolvedData(federal=loader.load_federal(2026))
    r = _run(data, 80_000, year=2026, wages={"taxpayer_qualified_tips": "10000"})
    assert r.schedule_1a_deduction == Money(10_000)
    assert r.federal_total_tax.round_cent() == Money("6570.00")


def test_absent_sections_mean_not_in_force(federal_2025):
    sched = federal_2025.schedule_1a.model_copy(
        update={"tips": None, "overtime": None, "car_loan_interest": None})
    data = ResolvedData(federal=federal_2025.model_copy(update={"schedule_1a": sched}))
    r = _run(data, 60_000, wages={"taxpayer_qualified_tips": "8000"},
             deductions={"car_loan_interest": "3000"})
    assert r.schedule_1a_deduction == ZERO
    assert not r.trace.has("fed.schedule_1a")


# ----- validation -----------------------------------------------------------

def test_tips_plus_overtime_cannot_exceed_box_1():
    with pytest.raises(ValidationError, match="exceed taxpayer W-2 box 1"):
        make_input(income={"wages": {"taxpayer_w2": "10000",
                                     "taxpayer_qualified_tips": "8000",
                                     "taxpayer_qualified_overtime": "3000"}})


def test_spouse_tips_cannot_exceed_spouse_box_1():
    with pytest.raises(ValidationError, match="exceed spouse W-2 box 1"):
        make_input(taxpayer={"filing_status": "married_filing_jointly", "state": ""},
                   income={"wages": {"taxpayer_w2": "90000", "spouse_w2": "1000",
                                     "spouse_qualified_tips": "2000"}})


def test_schema_requires_every_status():
    from ouch.taxdata.schema import PhasedDeduction
    with pytest.raises(ValidationError, match="cap missing"):
        PhasedDeduction.model_validate({
            "cap": {"single": 1}, "phaseout_threshold": {s.value: 1 for s in F},
            "reduction_per_step": 100, "round_steps": "down",
            "joint_return_required": True})
    with pytest.raises(ValidationError):
        PhasedDeduction.model_validate({
            "cap": {s.value: 1 for s in F}, "phaseout_threshold": {s.value: 1 for s in F},
            "reduction_per_step": 100, "round_steps": "nearest",
            "joint_return_required": True})

