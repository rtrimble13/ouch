"""Enhanced deduction for seniors, 2025–2028 (rtrimble13/ouch#21).

Rules from Schedule 1-A (Form 1040) (2025), Part V:
  line 32  $75,000 ($150,000 if married filing jointly)
  line 34  6% of MAGI over line 32
  line 35  $6,000 less line 34, not below zero
  line 36  line 35 once for each of the taxpayer and (joint return only) the
           spouse who has a valid SSN and was born before January 2, 1961
  caution  "If married, you must file jointly to claim this deduction."
Part VI line 38 carries it to Form 1040 line 13b: below AGI, for itemizers
and non-itemizers alike.

Hand computations use the shipped 2025 file: standard deduction 15,750
single / 31,500 MFJ (Rev. Proc. 2025-32 §3.01); additional age-65 amount 2,000 single / 1,600 married;
single brackets 10% to 11,925, 12% to 48,475, 22% to 103,350; MFJ 10% to
23,850, 12% to 96,950.
"""

from decimal import Decimal

import pytest

from ouch.engine import pipeline
from ouch.engine.pipeline import ResolvedData
from ouch.model.money import Money, ZERO
from tests.conftest import make_input

SENIOR = "1955-03-01"   # 70 at the end of 2025
YOUNG = "1980-03-01"


def _run(data, status="single", wages="60000", birth=SENIOR, spouse=None,
         **extra):
    raw = {"taxpayer": {"filing_status": status, "state": "",
                        "birth_date": birth},
           "income": {"wages": {"taxpayer_w2": wages}}}
    if spouse is not None:
        raw["spouse"] = {"birth_date": spouse} if spouse else {}
    for key, value in extra.items():
        raw.setdefault(key, {}).update(value)
    return pipeline.run(make_input(**raw), data, compute_marginals=False)


def test_single_70_below_threshold_full_6000(data_federal_only):
    """Wages 60,000 = MAGI, below 75,000 → 6,000.
    taxable = 60,000 − (15,750 + 2,000) − 6,000 = 36,250
    tax = 1,192.50 + 12% × 24,325 (2,919.00) = 4,111.50"""
    r = _run(data_federal_only)
    assert r.schedule_1a_deduction == Money(6_000)
    assert r.deduction_taken == Money(17_750)  # line 12 is unchanged
    assert r.agi == Money(60_000)              # below the line: AGI unchanged
    assert r.taxable_income == Money(36_250)
    assert r.federal_total_tax.round_cent() == Money("4111.50")


def test_mfj_both_65_plus_12000(data_federal_only):
    """Wages 100,000, MAGI below 150,000 → 2 × 6,000.
    taxable = 100,000 − (31,500 + 2 × 1,600) − 12,000 = 53,300
    tax = 2,385.00 + 12% × 29,450 (3,534.00) = 5,919.00"""
    r = _run(data_federal_only, status="married_filing_jointly",
             wages="100000", spouse="1958-07-04")
    assert r.schedule_1a_deduction == Money(12_000)
    assert r.taxable_income == Money(53_300)
    assert r.federal_total_tax.round_cent() == Money("5919.00")


def test_mfj_one_spouse_qualifies(data_federal_only):
    r = _run(data_federal_only, status="married_filing_jointly",
             wages="100000", spouse=YOUNG)
    assert r.schedule_1a_deduction == Money(6_000)


def test_single_in_phaseout_band(data_federal_only):
    """MAGI 100,000: 6% × 25,000 = 1,500 → 4,500.
    taxable = 100,000 − 17,750 − 4,500 = 77,750
    tax = 1,192.50 + 4,386.00 + 22% × 29,275 (6,440.50) = 12,019.00"""
    r = _run(data_federal_only, wages="100000")
    assert r.schedule_1a_deduction == Money(4_500)
    assert r.taxable_income == Money(77_750)
    assert r.federal_total_tax.round_cent() == Money("12019.00")
    assert "6% of MAGI over $75,000" in r.trace.get("fed.deduction.senior").rule


def test_mfj_phaseout_applies_to_each_person(data_federal_only):
    """MAGI 200,000: line 35 = 6,000 − 6% × 50,000 = 3,000, entered on both
    36a and 36b → 6,000."""
    r = _run(data_federal_only, status="married_filing_jointly",
             wages="200000", spouse="1958-07-04")
    assert r.schedule_1a_deduction == Money(6_000)


@pytest.mark.parametrize("wages, expected", [
    ("174000", "60"),    # 6,000 − 6% × 99,000 = 60
    ("175000", "0"),     # 6,000 − 6% × 100,000 = 0
    ("300000", "0"),     # never negative
])
def test_phaseout_to_zero(data_federal_only, wages, expected):
    r = _run(data_federal_only, wages=wages)
    assert r.schedule_1a_deduction == Money(expected)
    assert r.trace.has("fed.deduction.senior") is (expected != "0")


def test_head_of_household_uses_single_threshold(data_federal_only):
    """HoH, MAGI 100,000: over $75,000 by 25,000 → 4,500."""
    r = _run(data_federal_only, status="head_of_household", wages="100000")
    assert r.schedule_1a_deduction == Money(4_500)


@pytest.mark.parametrize("birth, qualifies", [
    ("1961-06-01", False),   # 64 at the end of 2025
    ("1961-01-02", False),   # turns 65 on Jan 2, 2026: not "before Jan 2, 1961"
    ("1961-01-01", True),    # treated as 65 on Dec 31, 2025 (day-before rule)
    ("1960-12-31", True),
])
def test_age_test_is_born_before_january_2(data_federal_only, birth, qualifies):
    r = _run(data_federal_only, birth=birth)
    assert r.schedule_1a_deduction == (Money(6_000) if qualifies else ZERO)


def test_no_birth_date_never_qualifies(data_federal_only):
    r = _run(data_federal_only, birth=None)
    assert r.schedule_1a_deduction == ZERO


def test_spouse_without_birth_date_not_counted(data_federal_only):
    r = _run(data_federal_only, status="married_filing_jointly",
             wages="100000", spouse="")
    assert r.schedule_1a_deduction == Money(6_000)


def test_married_filing_separately_denied_with_warning(data_federal_only):
    r = _run(data_federal_only, status="married_filing_separately")
    assert r.schedule_1a_deduction == ZERO
    assert any("filing separately" in w for w in r.warnings)


def test_itemizers_also_claim_it(data_federal_only):
    r = _run(data_federal_only, deductions={
        "mode": "itemized",
        "itemized": {"mortgage_interest": "20000"}})
    assert r.deduction_mode == "itemized"
    assert r.deduction_taken == Money(20_000)
    assert r.schedule_1a_deduction == Money(6_000)
    assert r.taxable_income == Money(60_000 - 20_000 - 6_000)


def test_ssn_assumption_is_disclosed(data_federal_only):
    r = _run(data_federal_only)
    assert any("Social Security number" in w for w in r.warnings)


def test_under_65_gets_nothing_and_no_warning(data_federal_only):
    r = _run(data_federal_only, birth=YOUNG)
    assert r.schedule_1a_deduction == ZERO
    assert not r.trace.has("fed.schedule_1a")
    assert not any("seniors" in w for w in r.warnings)


def test_trace_lines_and_taxable_inputs(data_federal_only):
    r = _run(data_federal_only)
    senior = r.trace.get("fed.deduction.senior")
    assert senior.form_ref == "Schedule 1-A Part V"
    assert "× 1 qualifying person" in senior.rule
    total = r.trace.get("fed.schedule_1a")
    # Schedule 1-A is Form 1040 line 13b for 2025 and 13a from 2026 (draft
    # 2026 Form 1040: "Lines 13a and 13b order flipped").
    assert total.form_ref == "Form 1040 line 13 (13b for 2025, 13a from 2026)"
    assert total.inputs == ("fed.deduction.senior",)
    taxable = r.trace.get("fed.taxable")
    assert "fed.schedule_1a" in taxable.inputs
    assert "Schedule 1-A" in taxable.rule


def test_qbi_limit_measured_after_schedule_1a(data_federal_only):
    """Single, 70, wages 40,000, QBI 50,000 (no SE income).
    Taxable before QBI = 40,000 − 17,750 − 6,000 = 16,250; the overall
    limit 20% × 16,250 = 3,250 binds against 20% × 50,000 = 10,000.
    (Without the senior deduction the limit would be 4,450.)"""
    r = _run(data_federal_only, wages="40000",
             income={"business": {"qbi_eligible_income": "50000"}})
    assert r.schedule_1a_deduction == Money(6_000)
    assert r.qbi_deduction == Money(3_250)
    assert r.taxable_income == Money(13_000)


def test_absent_section_means_not_in_force(federal_2025):
    """A data year without schedule_1a.senior (e.g. 2029) gives nothing,
    with no year checks in the engine."""
    fed = federal_2025.model_copy(update={"schedule_1a": None})
    r = _run(ResolvedData(federal=fed))
    assert r.schedule_1a_deduction == ZERO
    assert not any("seniors" in w for w in r.warnings)


def test_json_output_carries_the_field(data_federal_only):
    from ouch.render.json_out import result_to_dict
    d = result_to_dict(_run(data_federal_only))
    assert d["schedule_1a_deduction"] == "6000.00"


def test_shipped_2026_file_carries_the_section():
    from ouch.taxdata import loader
    sec = loader.load_federal(2026).schedule_1a.senior
    assert sec.amount == Decimal(6_000)
    assert sec.phaseout_rate == Decimal("0.06")


def test_schema_requires_every_status_threshold():
    from pydantic import ValidationError
    from ouch.taxdata.schema import SeniorDeduction
    with pytest.raises(ValidationError, match="missing"):
        SeniorDeduction.model_validate({
            "amount": 6000, "phaseout_rate": "0.06",
            "phaseout_threshold": {"single": 75000,
                                   "married_filing_jointly": 150000}})


@pytest.mark.parametrize("birth, standard", [
    ("1961-01-01", 17_750),  # treated as 65 on Dec 31, 2025: 15,750 + 2,000
    ("1961-01-02", 15_750),  # still 64
])
def test_additional_standard_deduction_uses_the_same_age_rule(
        data_federal_only, birth, standard):
    """Form 1040 (2025): the age-65 box is "born before January 2, 1961".
    Calendar age said 64 for a January 1, 1961 birthday."""
    r = _run(data_federal_only, birth=birth)
    assert r.deduction_taken == Money(standard)
