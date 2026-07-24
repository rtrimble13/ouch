"""Property tests (spec §16.3) — hypothesis over the pure pipeline."""

from decimal import Decimal

from hypothesis import given, settings, strategies as st

from ouch.engine import pipeline
from ouch.model.money import Money, ZERO
from tests.conftest import make_input

amounts = st.integers(min_value=0, max_value=800_000)
# Above the EITC's reach: inside the phase-in, more earned income lawfully
# *reduces* total tax (the credit grows faster), so monotonicity only holds
# past the phase-out.
amounts_above_eitc = st.integers(min_value=30_000, max_value=800_000)
gains = st.integers(min_value=-50_000, max_value=200_000)


def _run(data, wages=0, interest=0, ltcg=0, stcg=0, qd=0, od=None):
    od = max(qd, od or 0)
    inp = make_input(income={
        "wages": {"taxpayer_w2": str(wages)},
        "investment": {"interest": str(interest),
                       "ordinary_dividends": str(od),
                       "qualified_dividends": str(qd),
                       "long_term_gains": str(ltcg),
                       "short_term_gains": str(stcg)}})
    return pipeline.run(inp, data, compute_marginals=False)


@settings(max_examples=40, deadline=None)
@given(wages=amounts_above_eitc, bump=st.integers(min_value=1, max_value=50_000))
def test_monotonic_in_income(data_federal_only, wages, bump):
    """More ordinary income never reduces total tax, above the EITC region
    (inside the EITC phase-in the credit legitimately grows faster)."""
    lo = _run(data_federal_only, wages=wages)
    hi = _run(data_federal_only, wages=wages + bump)
    assert hi.federal_total_tax >= lo.federal_total_tax


@settings(max_examples=40, deadline=None)
@given(wages=amounts, ltcg=gains, stcg=gains, qd=st.integers(0, 50_000))
def test_marginal_rate_bounded_and_invariants(data_federal_only, wages, ltcg,
                                              stcg, qd):
    r = _run(data_federal_only, wages=wages, ltcg=ltcg, stcg=stcg, qd=qd)
    assert r.taxable_income >= ZERO
    assert r.agi <= r.total_income
    # Refundable credits (EITC) can drive the total below zero, but never
    # below the refundable amount itself.
    assert r.federal_total_tax >= -r.credits_refundable
    assert Decimal(-1) <= r.effective_rate_agi <= Decimal(1)


@settings(max_examples=25, deadline=None)
@given(wages=amounts, qd=st.integers(0, 100_000))
def test_purity(data_federal_only, wages, qd):
    """Same input twice → identical results, input unmutated."""
    inp = make_input(income={
        "wages": {"taxpayer_w2": str(wages)},
        "investment": {"ordinary_dividends": str(qd),
                       "qualified_dividends": str(qd)}})
    before = inp.model_dump_json()
    r1 = pipeline.run(inp, data_federal_only, compute_marginals=False)
    r2 = pipeline.run(inp, data_federal_only, compute_marginals=False)
    assert r1.federal_total_tax == r2.federal_total_tax
    assert r1.input_fingerprint == r2.input_fingerprint
    assert inp.model_dump_json() == before


@settings(max_examples=25, deadline=None)
@given(wages=st.integers(min_value=10_000, max_value=800_000))
def test_deduction_choice_is_optimal(data_federal_only, wages):
    """Auto mode never produces higher tax than forcing either mode."""
    base = {"income": {"wages": {"taxpayer_w2": str(wages)}},
            "deductions": {"mode": "auto",
                           "itemized": {"mortgage_interest": "12000",
                                        "charitable_cash": "5000"}}}
    auto = pipeline.run(make_input(**base), data_federal_only,
                        compute_marginals=False)
    for mode in ("standard", "itemized"):
        base["deductions"]["mode"] = mode
        forced = pipeline.run(make_input(**base), data_federal_only,
                              compute_marginals=False)
        assert auto.federal_total_tax <= forced.federal_total_tax
