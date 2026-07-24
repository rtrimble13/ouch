"""Pipeline-level tests: hand-computed golden values, purity, invariants,
NIIT threshold crossing (stacking matrix case 6), deduction optimality.
"""

from decimal import Decimal

import pytest

from ouch.engine import pipeline
from ouch.model.money import Money, ZERO
from tests.conftest import make_input


def test_golden_single_tx_wages_only(data_federal_only):
    """Hand computation (SOURCE: 2025 single brackets, std deduction 15,000):
    wages 100,000 → taxable 85,000
    10%×11,925 = 1,192.50 ; 12%×36,550 = 4,386.00 ; 22%×36,525 = 8,035.50
    total = 13,614.00
    """
    inp = make_input(income={"wages": {"taxpayer_w2": "100000"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r.taxable_income == Money(85_000)
    assert r.federal_total_tax.round_cent() == Money("13614.00")
    assert r.deduction_mode == "standard"


def test_golden_pref_stacking_with_real_brackets(data_federal_only):
    """wages 142,000 + interest 850 + non-qual div 150 + QD 1,950 + LTCG 3,400
    ordinary taxable = 148,350 − 15,000 − 5,350 = 128,000
    tax: 1,192.50 + 4,386.00 + 22%×54,875 (=12,072.50) + 24%×24,650 (=5,916)
       = 23,567.00 ; pref floor 128,000 > 48,350 → 15%×5,350 = 802.50
    """
    inp = make_input(income={
        "wages": {"taxpayer_w2": "142000"},
        "investment": {"interest": "850", "ordinary_dividends": "2100",
                       "qualified_dividends": "1950",
                       "long_term_gains": "3400"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r.tax_ordinary.round_cent() == Money("23567.00")
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
    # SALT capped at 10,000 → itemized = 10,000 + 10,000 mortgage = 20,000
    assert r.deduction_taken == Money(20_000)
    assert r.deduction_mode == "itemized"


def test_ctc_phaseout(data_federal_only):
    dep = [{"name": "kid", "birth_date": "2016-02-01", "relationship": "child"}]
    # AGI 150,000 < 200,000 → full 2,000 credit
    r1 = pipeline.run(make_input(dependents=dep, income={
        "wages": {"taxpayer_w2": "150000"}}), data_federal_only,
        compute_marginals=False)
    assert r1.credits_nonrefundable == Money(2_000)
    # AGI 210,000 → 10 steps × 50 = 500 reduction
    r2 = pipeline.run(make_input(dependents=dep, income={
        "wages": {"taxpayer_w2": "210000"}}), data_federal_only,
        compute_marginals=False)
    assert r2.credits_nonrefundable == Money(1_500)


def test_qbi_below_threshold(data_federal_only):
    inp = make_input(income={"business": {"schedule_c_net": "50000",
                                          "qbi_eligible_income": "50000"}})
    r = pipeline.run(inp, data_federal_only, compute_marginals=False)
    # Hand computation: ½SE tax = 50,000×0.9235×0.153/2 = 3,532.3875
    # tentative = 20% × (50,000 − 3,532.3875) = 9,293.5225
    # overall limit = 20% × taxable-before-QBI
    #              = 20% × (50,000 − 3,532.3875 − 15,000) = 6,293.5225 ← binds
    expected = (Money("50000") - Money("3532.3875") - Money("15000")) * Decimal("0.20")
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


def test_part_year_residency_refused(data_federal_only):
    from ouch.errors import JurisdictionError
    inp = make_input(taxpayer={"filing_status": "single", "state": "",
                               "residency_months": 6})
    with pytest.raises(JurisdictionError):
        pipeline.run(inp, data_federal_only, compute_marginals=False)


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
