"""Pipeline-level tests: hand-computed golden values, purity, invariants,
NIIT threshold crossing (stacking matrix case 6), deduction optimality.
"""

from decimal import Decimal

import pytest

from ouch.engine import pipeline
from ouch.model.money import Money, ZERO
from tests.conftest import make_input


def test_golden_single_tx_wages_only(data_federal_only):
    """Hand computation (SOURCE: 2025 single brackets, Rev. Proc. 2024-40;
    standard deduction 15,750, Rev. Proc. 2025-32 §3.01):
    wages 100,000 → taxable 84,250
    10%×11,925 = 1,192.50 ; 12%×36,550 = 4,386.00 ; 22%×35,775 = 7,870.50
    total = 13,449.00
    """
    inp = make_input(income={"wages": {"taxpayer_w2": "100000"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r.taxable_income == Money(84_250)
    assert r.federal_total_tax.round_cent() == Money("13449.00")
    assert r.deduction_mode == "standard"


def test_golden_pref_stacking_with_real_brackets(data_federal_only):
    """wages 142,000 + interest 850 + non-qual div 150 + QD 1,950 + LTCG 3,400
    ordinary taxable = 148,350 − 15,750 − 5,350 = 127,250
    tax: 1,192.50 + 4,386.00 + 22%×54,875 (=12,072.50) + 24%×23,900 (=5,736)
       = 23,387.00 ; pref floor 127,250 > 48,350 → 15%×5,350 = 802.50
    """
    inp = make_input(income={
        "wages": {"taxpayer_w2": "142000"},
        "investment": {"interest": "850", "ordinary_dividends": "2100",
                       "qualified_dividends": "1950",
                       "long_term_gains": "3400"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r.tax_ordinary.round_cent() == Money("23387.00")
    assert r.tax_preferential.round_cent() == Money("802.50")


def test_case6_pref_income_pushes_across_niit_threshold(data_federal_only):
    """Stacking matrix case 6: preferential income pushes MAGI across the
    NIIT threshold. wages 190,000 + LTCG 20,000 → MAGI 210,000
    NIIT = 3.8% × min(20,000, 210,000−200,000) = 380."""
    inp = make_input(income={"wages": {"taxpayer_w2": "190000"},
                             "investment": {"long_term_gains": "20000"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r.niit.round_cent() == Money("380.00")
    # Without the gains, no NIIT:
    inp2 = make_input(income={"wages": {"taxpayer_w2": "190000"}})
    r2 = pipeline.run(inp2, data_federal_only, compute_marginals=False)
    assert r2.niit == ZERO


def test_purity_and_fingerprint_stability(data_federal_only):
    inp = make_input(income={"wages": {"taxpayer_w2": "80000"}})
    snapshot = inp.model_dump_json()
    r1 = pipeline.run(inp, data_federal_only, compute_marginals=False)
    r2 = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r1.federal_total_tax == r2.federal_total_tax
    assert r1.input_fingerprint == r2.input_fingerprint
    assert inp.model_dump_json() == snapshot  # input not mutated


def test_deduction_auto_never_worse_than_forced(data_federal_only):
    base = {
        "income": {"wages": {"taxpayer_w2": "150000"}},
        "deductions": {"mode": "auto",
                       "itemized": {"mortgage_interest": "14000",
                                    "real_estate_tax": "9000",
                                    "charitable_cash": "2000"}},
    }
    auto = pipeline.run(make_input(**base), data_federal_only,
                        compute_marginals=False)
    for forced in ("standard", "itemized"):
        base["deductions"]["mode"] = forced
        r = pipeline.run(make_input(**base), data_federal_only,
                         compute_marginals=False)
        assert auto.federal_total_tax <= r.federal_total_tax


def test_salt_cap_binds(data_federal_only):
    inp = make_input(deductions={"itemized": {
        "state_local_income_tax": "30000", "real_estate_tax": "20000",
        "mortgage_interest": "10000"}},
        income={"wages": {"taxpayer_w2": "400000"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    # MAGI 400,000 is under the 500,000 phase-down threshold, so the 2025
    # cap is the full 40,000: SALT 50,000 → 40,000; + 10,000 mortgage = 50,000
    assert r.deduction_taken == Money(50_000)
    assert r.deduction_mode == "itemized"


def test_ctc_phaseout(data_federal_only):
    dep = [{"name": "kid", "birth_date": "2016-02-01", "relationship": "child"}]
    # AGI 150,000 < 200,000 → full 2,200 credit (2025, OBBBA §70104)
    r1 = pipeline.run(make_input(dependents=dep, income={
        "wages": {"taxpayer_w2": "150000"}}), data_federal_only,
        compute_marginals=False)
    assert r1.credits_nonrefundable == Money(2_200)
    # AGI 210,000 → 10 steps × 50 = 500 reduction → 1,700
    r2 = pipeline.run(make_input(dependents=dep, income={
        "wages": {"taxpayer_w2": "210000"}}), data_federal_only,
        compute_marginals=False)
    assert r2.credits_nonrefundable == Money(1_700)


def test_qbi_below_threshold(data_federal_only):
    inp = make_input(income={"business": {"schedule_c_net": "50000",
                                          "qbi_eligible_income": "50000"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    # Hand computation: ½SE tax = 50,000×0.9235×0.153/2 = 3,532.3875
    # tentative = 20% × (50,000 − 3,532.3875) = 9,293.5225
    # overall limit = 20% × taxable-before-QBI
    #              = 20% × (50,000 − 3,532.3875 − 15,750) = 6,143.5225 ← binds
    expected = (Money("50000") - Money("3532.3875") - Money("15750")) * Decimal("0.20")
    assert abs(r.qbi_deduction - expected) < Money("0.01")


def test_mfj_ny_nyc_full_stack(data_ny_nyc):
    """End-to-end: SALT loop converges, all jurisdictions sum, trace is a DAG."""
    inp = make_input(
        taxpayer={"filing_status": "married_filing_jointly", "state": "NY",
                  "locality": "NYC"},
        income={"wages": {"taxpayer_w2": "185000", "spouse_w2": "96000"},
                "investment": {"qualified_dividends": "12500",
                               "ordinary_dividends": "14000",
                               "long_term_gains": "41000"}},
    )
    r = pipeline.run(inp, data_ny_nyc, compute_marginals=False)
    assert r.state is not None and r.state.tax > ZERO
    assert r.local is not None and r.local.tax > ZERO
    assert (r.total_tax_all_jurisdictions
            == r.federal_total_tax + r.state.tax + r.local.tax)
    assert r.trace.get("fed.tax.total")  # trace built and DAG-verified
    assert r.effective_rate_agi > Decimal(0)


def test_part_year_residency_allocates_by_ratio(data_federal_only):
    """Part-year (M5): state tax scales by residency months, loudly marked
    approximate. Previously refused with exit 7."""
    from ouch.engine.pipeline import ResolvedData
    from ouch.taxdata import loader
    data = ResolvedData(federal=data_federal_only.federal,
                        state=loader.load_state("PA", 2025))
    full = pipeline.run(make_input(
        taxpayer={"filing_status": "single", "state": "PA"},
        income={"wages": {"taxpayer_w2": "100000"}}), data,
        compute_marginals=False)
    half = pipeline.run(make_input(
        taxpayer={"filing_status": "single", "state": "PA",
                  "residency_months": 6}),
        data, compute_marginals=False)
    # rebuild half with same income
    half = pipeline.run(make_input(
        taxpayer={"filing_status": "single", "state": "PA",
                  "residency_months": 6},
        income={"wages": {"taxpayer_w2": "100000"}}), data,
        compute_marginals=False)
    assert half.state.tax.round_cent() == (full.state.tax / 2).round_cent()
    assert any("part-year" in w for w in half.warnings)


def test_part_year_with_former_state(data_federal_only):
    """8 months PA + 4 months MA: both states taxed by their month ratio."""
    from ouch.engine.pipeline import ResolvedData
    from ouch.taxdata import loader
    data = ResolvedData(federal=data_federal_only.federal,
                        state=loader.load_state("PA", 2025),
                        former_state=loader.load_state("MA", 2025))
    r = pipeline.run(make_input(
        taxpayer={"filing_status": "single", "state": "PA",
                  "residency_months": 8, "former_state": "MA"},
        income={"wages": {"taxpayer_w2": "120000"}}), data,
        compute_marginals=False)
    assert r.other_state is not None and r.other_state.code == "MA"
    # PA flat 3.07% × 8/12; MA flat 5% × 4/12 on (AGI − std... MA has no
    # deduction here) — both scaled from their full-year computations.
    assert r.state.tax > ZERO and r.other_state.tax > ZERO
    assert (r.total_tax_all_jurisdictions
            == r.federal_total_tax + r.state.tax + r.other_state.tax)
    assert r.trace.has("ma.tax")


def test_marginal_rate_numeric(data_federal_only):
    inp = make_input(income={"wages": {"taxpayer_w2": "100000"}})
    r = pipeline.run(inp, data_federal_only)
    # 100k wages puts the next $1,000 fully in the 22% bracket
    assert r.marginal_rate_federal == Decimal("0.2200")


def test_amt_triggers_on_huge_salt(data_ny_nyc):
    """A large SALT deduction cannot trigger AMT post-TCJA (capped at 10k),
    but the parallel computation must never produce a negative addition."""
    inp = make_input(income={"wages": {"taxpayer_w2": "500000"}})
    r = pipeline.run(inp, data_ny_nyc, compute_marginals=False)
    assert r.amt_additional >= ZERO


# --- Issue #2: Additional Medicare uses uncapped Medicare wages -------------


def test_additional_medicare_ignores_capped_box3(data_federal_only):
    """Single, $300,000 box 1 with a real (capped) box 3 of $176,100.
    Form 8959: (300,000 − 200,000) × 0.9% = $900. Box 3 must not be the base."""
    capped = make_input(income={"wages": {"taxpayer_w2": "300000",
                                          "taxpayer_ss_wages": "176100"}})
    absent = make_input(income={"wages": {"taxpayer_w2": "300000"}})
    r_capped = pipeline.run(capped, data_federal_only, compute_marginals=False)
    r_absent = pipeline.run(absent, data_federal_only, compute_marginals=False)
    assert r_capped.additional_medicare.round_cent() == Money("900.00")
    assert r_absent.additional_medicare.round_cent() == Money("900.00")


def test_additional_medicare_uses_box5_when_supplied(data_federal_only):
    """Box 5 exceeds box 1 by the $23,500 401(k) deferral:
    (323,500 − 200,000) × 0.9% = $1,111.50."""
    inp = make_input(income={"wages": {"taxpayer_w2": "300000",
                                       "taxpayer_ss_wages": "176100",
                                       "taxpayer_medicare_wages": "323500"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r.additional_medicare.round_cent() == Money("1111.50")


def test_additional_medicare_box5_defaults_per_person(data_federal_only):
    """MFJ: taxpayer supplies box 5 = 223,500 (box 1 = 200,000); spouse
    supplies only box 1 = 100,000, which stands in for their box 5.
    (223,500 + 100,000 − 250,000) × 0.9% = $661.50."""
    inp = make_input(
        taxpayer={"filing_status": "married_filing_jointly", "state": ""},
        income={"wages": {"taxpayer_w2": "200000",
                          "taxpayer_medicare_wages": "223500",
                          "spouse_w2": "100000"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r.additional_medicare.round_cent() == Money("661.50")


def test_marginal_rate_includes_additional_medicare_with_box5(data_federal_only):
    """The numeric marginal bump must move an explicit box 5 with box 1, or
    the 0.9% Additional Medicare tax vanishes from the marginal rate."""
    explicit = make_input(income={"wages": {"taxpayer_w2": "300000",
                                            "taxpayer_medicare_wages": "300000"}})
    implicit = make_input(income={"wages": {"taxpayer_w2": "300000"}})
    r_explicit = pipeline.run(explicit, data_federal_only)
    r_implicit = pipeline.run(implicit, data_federal_only)
    assert r_explicit.marginal_rate_federal == r_implicit.marginal_rate_federal


# --- Issue #3: Schedule C losses reduce AGI ---------------------------------


def test_schedule_c_loss_reduces_agi(data_federal_only):
    """Single, wages 100,000, Schedule C −20,000 (Schedule 1 line 3).
    total income = AGI = 80,000 ; taxable = 80,000 − 15,750 = 64,250
    10%×11,925 = 1,192.50 ; 12%×36,550 = 4,386.00 ; 22%×15,775 = 3,470.50
    total = 9,049.00 — and no SE tax on a loss."""
    inp = make_input(income={"wages": {"taxpayer_w2": "100000"},
                             "business": {"schedule_c_net": "-20000"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r.total_income == Money(80_000)
    assert r.agi == Money(80_000)
    assert r.taxable_income == Money(64_250)
    assert r.se_tax == ZERO
    assert r.federal_total_tax.round_cent() == Money("9049.00")


def test_schedule_c_loss_is_disclosed(data_federal_only):
    """The loss-limitation rules are out of scope — that must be loud."""
    inp = make_input(income={"wages": {"taxpayer_w2": "100000"},
                             "business": {"schedule_c_net": "-20000"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert any("Schedule C loss" in w and "not modeled" in w
               for w in r.warnings)
    total = r.trace.get("fed.income.total")
    assert str(total.fidelity) == "approximate"
    assert str(r.fidelity) == "approximate"


def test_schedule_c_profit_unchanged_and_exact(data_federal_only):
    """No disclosure noise when there is no loss."""
    inp = make_input(income={"wages": {"taxpayer_w2": "100000"},
                             "business": {"schedule_c_net": "20000"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r.total_income == Money(120_000)
    assert not any("Schedule C loss" in w for w in r.warnings)
    assert str(r.trace.get("fed.income.total").fidelity) == "exact"


# --- SS wage base is per person: SE tax coordinates against the owner -------
# 2025 wage base 176,100. Schedule C 50,000 → SE base 46,175.
#   SS portion  12.4% × 46,175 = 5,725.70
#   Medicare     2.9% × 46,175 = 1,339.08 (1,339.075)
#   full SE tax                = 7,064.78 ; Medicare only = 1,339.08

MFJ = {"filing_status": "married_filing_jointly", "state": ""}


def _se_tax(data, wages: dict, owner: str | None = None) -> Money:
    business = {"schedule_c_net": "50000"}
    if owner is not None:
        business["owner"] = owner
    inp = make_input(taxpayer=MFJ,
                     income={"wages": wages, "business": business})
    return pipeline.run(inp, data, compute_marginals=False).se_tax.round_cent()


def test_spouse_w2_does_not_consume_owners_wage_base(data_federal_only):
    """The taxpayer's business owes full SE tax: the spouse's $180,000 W-2
    exhausts only the spouse's own wage base."""
    assert _se_tax(data_federal_only, {"spouse_w2": "180000"}) == Money("7064.78")


def test_spouse_owned_business_coordinates_with_spouse_w2(data_federal_only):
    """Same household, business owned by the spouse whose W-2 is over the
    wage base: Medicare portion only."""
    assert _se_tax(data_federal_only, {"spouse_w2": "180000"},
                   owner="spouse") == Money("1339.08")


def test_box3_defaults_per_person(data_federal_only):
    """Taxpayer supplies a capped box 3 of 176,100; the spouse supplies only
    box 1 = 100,000, which stands in for their box 3 (base left 76,100 ≥
    46,175). Previously the household sum (176,100) was used for both."""
    wages = {"taxpayer_w2": "200000", "taxpayer_ss_wages": "176100",
             "spouse_w2": "100000"}
    assert _se_tax(data_federal_only, wages, owner="spouse") == Money("7064.78")
    assert _se_tax(data_federal_only, wages, owner="taxpayer") == Money("1339.08")


def test_partial_wage_base_remaining_for_owner(data_federal_only):
    """Owner's W-2 150,000 leaves 26,100 of base: 12.4% × 26,100 = 3,236.40,
    + 1,339.075 Medicare = 4,575.475 → 4,575.48. The spouse's wages are
    irrelevant to it."""
    wages = {"taxpayer_w2": "150000", "spouse_w2": "150000"}
    assert _se_tax(data_federal_only, wages) == Money("4575.48")


def test_spouse_owner_requires_joint_return():
    spouse_biz = {"business": {"owner": "spouse", "schedule_c_net": "1000"}}
    make_input(taxpayer=MFJ, income=spouse_biz)          # accepted jointly
    for status in ("single", "married_filing_separately", "head_of_household"):
        with pytest.raises(ValueError, match="owner is 'spouse'.*"
                                             "married_filing_jointly"):
            make_input(taxpayer={"filing_status": status, "state": ""},
                       income=spouse_biz)
