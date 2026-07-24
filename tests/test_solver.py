"""Withholding solver inversion (spec §10.2, §16.3)."""

import pytest

from ouch.engine import pipeline, solver
from ouch.errors import UsageError
from ouch.model.money import Money, ZERO
from tests.conftest import make_input


def _inp(**kw):
    base = {
        "income": {"wages": {"taxpayer_w2": "150000"}},
        "payments": {"withholding": {"federal_ytd": "10000",
                                     "federal_per_period": "500",
                                     "pay_periods_per_year": 24,
                                     "periods_remaining": 10}},
    }
    base.update(kw)
    return make_input(**base)


def test_solver_inverts_to_zero(data_federal_only):
    inp = _inp()
    pp = solver.solve_withholding(inp, data_federal_only, ZERO)
    r = pipeline.run(solver.with_withholding_per_period(inp, pp),
                     data_federal_only, compute_marginals=False)
    assert abs(r.balance_due_or_refund) <= Money("0.02")


def test_solver_inverts_to_refund(data_federal_only):
    inp = _inp()
    target = Money(-2_000)  # a $2,000 refund
    pp = solver.solve_withholding(inp, data_federal_only, target)
    r = pipeline.run(solver.with_withholding_per_period(inp, pp),
                     data_federal_only, compute_marginals=False)
    assert abs(r.balance_due_or_refund - target) <= Money("0.02")


def test_solver_refuses_zero_periods(data_federal_only):
    inp = make_input(income={"wages": {"taxpayer_w2": "150000"}})
    with pytest.raises(UsageError):
        solver.solve_withholding(inp, data_federal_only, ZERO)


def test_safe_harbor_solver(data_federal_only):
    inp = _inp(payments={
        "withholding": {"federal_ytd": "10000", "federal_per_period": "500",
                        "pay_periods_per_year": 24, "periods_remaining": 10},
        "prior_year": {"agi": "140000", "total_tax": "25000"}})
    pp = solver.solve_safe_harbor(inp, data_federal_only)
    r = pipeline.run(solver.with_withholding_per_period(inp, pp),
                     data_federal_only, compute_marginals=False)
    assert r.safe_harbor is not None
    assert r.safe_harbor.met is True
    assert r.safe_harbor.shortfall <= Money("0.01")
