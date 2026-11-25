"""SALT cap phase-down for high-MAGI itemizers (IRC §164(b)(7), rtrimble13/ouch#20).

Parameters are the 2025 figures confirmed in the Schedule A (Form 1040)
instructions (2025), "What's New" and the State and Local Tax Deduction
Worksheet: cap $40,000 ($20,000 MFS), reduced by 30% of MAGI over $500,000
($250,000 MFS), but not below $10,000 ($5,000 MFS).

Only the ``itemized.salt_cap`` section of the shipped 2025 file is replaced
here; the rest of that file is still pre-OBBBA (rtrimble13/ouch#27), so every
expected value below is derived by hand from these SALT parameters plus the
shipped brackets and standard deduction.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from ouch.engine import pipeline
from ouch.engine.deductions import itemized_deduction, salt_cap
from ouch.engine.pipeline import ResolvedData
from ouch.model.enums import FilingStatus
from ouch.model.money import Money
from ouch.scenario import runner
from ouch.config.profile import build_tax_input
from ouch.taxdata.schema import SaltCap
from tests.conftest import make_input

SALT_2025 = {
    "amount": 40_000, "mfs_amount": 20_000,
    "phasedown": {
        "threshold": {"amount": 500_000, "mfs_amount": 250_000},
        "rate": "0.30",
        "floor": {"amount": 10_000, "mfs_amount": 5_000},
    },
}

MFJ = FilingStatus.MARRIED_FILING_JOINTLY
MFS = FilingStatus.MARRIED_FILING_SEPARATELY


@pytest.fixture(scope="module")
def fed_obbba(federal_2025):
    itemized = federal_2025.itemized.model_copy(
        update={"salt_cap": SaltCap.model_validate(SALT_2025)})
    return federal_2025.model_copy(update={"itemized": itemized})


@pytest.fixture(scope="module")
def data_obbba(fed_obbba):
    return ResolvedData(federal=fed_obbba)


def _mfj_itemizer(agi: int, status: str = "married_filing_jointly", **itemized):
    """$50,000 of SALT ($35,000 income tax + $15,000 real estate)."""
    it = {"state_local_income_tax": "35000", "real_estate_tax": "15000"}
    it.update(itemized)
    return make_input(
        taxpayer={"filing_status": status, "state": ""},
        income={"wages": {"taxpayer_w2": str(agi)}},
        deductions={"mode": "itemized", "itemized": it})


# ----- the cap itself --------------------------------------------------------

@pytest.mark.parametrize("status, magi, expected", [
    # MFJ, below the threshold: the full $40,000.
    (MFJ, 400_000, 40_000),
    # MFJ, at the threshold: no reduction yet.
    (MFJ, 500_000, 40_000),
    # MFJ, in the band: 40,000 − 30% × (550,000 − 500,000) = 40,000 − 15,000.
    (MFJ, 550_000, 25_000),
    # MFJ, where the reduction reaches the floor exactly:
    # 40,000 − 30% × 100,000 = 10,000.
    (MFJ, 600_000, 10_000),
    # MFJ, far above: 40,000 − 60,000 < floor → $10,000.
    (MFJ, 700_000, 10_000),
    # MFS, in the band: 20,000 − 30% × (270,000 − 250,000) = 14,000.
    (MFS, 270_000, 14_000),
    # MFS, far above: the $5,000 floor.
    (MFS, 400_000, 5_000),
])
def test_salt_cap_phasedown(status, magi, expected):
    cap = salt_cap(status, Money(magi), SaltCap.model_validate(SALT_2025))
    assert cap == Money(expected)


def test_no_phasedown_is_the_flat_cap(federal_2025):
    """Shipped data without a phase-down section keeps the flat cap."""
    flat = federal_2025.itemized.salt_cap
    assert flat.phasedown is None
    assert salt_cap(MFJ, Money(5_000_000), flat) == Money(flat.amount)


# ----- itemized deduction and the pipeline -----------------------------------

@pytest.mark.parametrize("agi, allowed", [
    (400_000, 40_000),
    (550_000, 25_000),
    (700_000, 10_000),
])
def test_mfj_itemizer_with_50k_salt(fed_obbba, agi, allowed):
    inp = _mfj_itemizer(agi)
    it = itemized_deduction(inp, Money(agi), Money(0), Money(0), fed_obbba)
    assert it.salt == Money(allowed)
    assert it.salt_capped
    assert it.salt_cap == Money(allowed)
    assert it.salt_cap_reduced is (agi > 500_000)
    # the income-tax share deducted never exceeds the allowed SALT
    assert it.salt_income_component == Money(min(allowed, 35_000))


def test_mfs_itemizer_halved_amounts(fed_obbba):
    inp = _mfj_itemizer(270_000, status="married_filing_separately")
    it = itemized_deduction(inp, Money(270_000), Money(0), Money(0), fed_obbba)
    assert it.salt == Money(14_000)


def test_salt_below_reduced_cap_is_not_capped(fed_obbba):
    """$20,000 of SALT at MAGI 550,000 (cap 25,000) is deducted in full."""
    inp = _mfj_itemizer(550_000, state_local_income_tax="5000")
    it = itemized_deduction(inp, Money(550_000), Money(0), Money(0), fed_obbba)
    assert it.salt == Money(20_000)
    assert not it.salt_capped
    assert it.salt_cap_reduced


def test_pipeline_uses_reduced_cap_and_traces_it(data_obbba):
    """MFJ, wages 550,000 (AGI 550,000), SALT 50,000, mortgage interest
    20,000. Cap 25,000 → itemized 45,000 > standard 30,000.
    Taxable 505,000."""
    inp = _mfj_itemizer(550_000, mortgage_interest="20000")
    r = pipeline.run(inp, data_obbba, compute_marginals=False)
    assert r.deduction_mode == "itemized"
    assert r.deduction_taken == Money(45_000)
    assert r.taxable_income == Money(505_000)
    rule = r.trace.get("fed.deduction").rule
    assert "SALT cap $25,000" in rule
    assert "30% of MAGI over $500,000" in rule
    assert "floor $10,000" in rule


def test_trace_silent_when_cap_not_reduced(data_obbba):
    inp = _mfj_itemizer(400_000, mortgage_interest="20000")
    r = pipeline.run(inp, data_obbba, compute_marginals=False)
    assert r.deduction_taken == Money(60_000)
    assert "SALT cap" not in r.trace.get("fed.deduction").rule


def test_salt_loop_settles_under_reduced_cap(fed_obbba, federal_2025):
    """With no user SALT figure the state liability feeds SALT through the
    fixed-point loop; a binding reduced cap still short-circuits it."""
    from ouch.taxdata import loader
    data = ResolvedData(federal=fed_obbba, state=loader.load_state("NY", 2025))
    inp = make_input(
        taxpayer={"filing_status": "married_filing_jointly", "state": "NY"},
        income={"wages": {"taxpayer_w2": "550000"}},
        deductions={"mode": "itemized",
                    "itemized": {"real_estate_tax": "15000"}})
    r = pipeline.run(inp, data, compute_marginals=False)
    # NY tax on 550k is far above 10k, so SALT = the reduced 25,000 cap.
    assert r.deduction_taken == Money(25_000)


# ----- marginal rates: the band is a cliff -----------------------------------

def test_sweep_flags_phasedown_band_as_cliff(data_obbba):
    """MFJ, SALT 50,000 + mortgage 20,000, AUTO deduction, wages swept
    450k → 650k in 50k steps. 2025 MFJ brackets: 24% to 394,600 (tax there
    80,398), 32% to 501,050 (114,462), then 35%. Additional Medicare 0.9%
    over 250,000 applies at every point.

    wages  deduction        taxable   income tax    + Add'l Medicare  total
    450k   itemized 60,000  390,000    79,294.00    1,800             81,094.00
    500k   itemized 60,000  440,000    94,926.00    2,250             97,176.00
    550k   itemized 45,000  505,000   115,844.50    2,700            118,544.50
    600k   standard 30,000  570,000   138,594.50    3,150            141,744.50
    650k   standard 30,000  620,000   156,094.50    3,600            159,694.50

    Step marginals (the runner rounds to 4 places): 0.3216, 0.4274
    (21,368.50 / 50,000), 0.464, 0.359. The two steps inside the
    phase-down band (500k→600k) add 30% × the bracket rate on top of it
    (fully in band: 35% × 1.3 + 0.9% = 46.4%); the cliff flag fires on
    entering the band and again on the all-35% in-band step, and the rate
    falls back once the floor is reached.
    """
    base = {
        "tax_year": 2025,
        "taxpayer": {"filing_status": "married_filing_jointly", "state": ""},
        "income": {"wages": {"taxpayer_w2": 450_000}},
        "deductions": {"itemized": {"state_local_income_tax": 35_000,
                                    "real_estate_tax": 15_000,
                                    "mortgage_interest": 20_000}},
    }
    points = runner.sweep(
        base, "income.wages.taxpayer_w2",
        Decimal(450_000), Decimal(650_000), Decimal(50_000),
        ["total_tax_all_jurisdictions"], data_obbba,
        lambda raw: build_tax_input(raw, 2025))
    marginals = [p.step_marginal for p in points[1:]]
    assert marginals == [Decimal("0.3216"), Decimal("0.4274"),
                         Decimal("0.464"), Decimal("0.359")]
    assert [p.value for p in points if p.cliff] == [Decimal(550_000),
                                                     Decimal(600_000)]


# ----- schema ---------------------------------------------------------------

def test_schema_rejects_floor_above_cap():
    bad = {**SALT_2025, "phasedown": {**SALT_2025["phasedown"],
                                      "floor": {"amount": 50_000,
                                                "mfs_amount": 5_000}}}
    with pytest.raises(ValidationError, match="floor exceeds"):
        SaltCap.model_validate(bad)


@pytest.mark.parametrize("rate", ["0", "1.5", "-0.3"])
def test_schema_rejects_bad_rate(rate):
    bad = {**SALT_2025, "phasedown": {**SALT_2025["phasedown"], "rate": rate}}
    with pytest.raises(ValidationError):
        SaltCap.model_validate(bad)


def test_schema_rejects_untyped_phasedown():
    """The old free-form dict is gone: unknown keys are an error (P5)."""
    bad = {**SALT_2025, "phasedown": {"rate": "0.30", "threshold": 500_000}}
    with pytest.raises(ValidationError):
        SaltCap.model_validate(bad)
