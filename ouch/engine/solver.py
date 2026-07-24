"""Withholding solver: goal-seek by bisection over the pure pipeline
(spec §10.2). Because the pipeline is pure and monotonic in withholding,
bisection converges to the cent. No analytic inversion is attempted —
phase-outs and the safe-harbor floor make the function piecewise.
"""

from __future__ import annotations

from ouch.engine import pipeline
from ouch.engine.pipeline import ResolvedData
from ouch.errors import ConvergenceError, UsageError
from ouch.model.input import TaxInput
from ouch.model.money import Money, ZERO, maxm

MAX_ITER = 64
TOLERANCE = Money("0.01")


def with_withholding_per_period(inp: TaxInput, per_period: Money,
                                periods: int | None = None) -> TaxInput:
    w = inp.payments.withholding
    update: dict = {"federal_per_period": per_period.amount}
    if periods is not None:
        update["periods_remaining"] = periods
    return inp.model_copy(update={
        "payments": inp.payments.model_copy(update={
            "withholding": w.model_copy(update=update)})})


def _estimate_upper_bound(inp: TaxInput, data: ResolvedData,
                          periods: int) -> Money:
    base = pipeline.run(inp, data, compute_marginals=False)
    return maxm(base.total_tax_all_jurisdictions, Money(1000)) / periods * 3 + Money(1000)


def solve_withholding(inp: TaxInput, data: ResolvedData, target: Money,
                      *, periods: int | None = None) -> Money:
    """Find the federal per-period withholding producing
    `balance_due_or_refund == target` (negative target = desired refund)."""
    if periods is None:
        periods = inp.payments.withholding.periods_remaining
    if periods <= 0:
        raise UsageError(
            "no pay periods remain — the solver has nothing to adjust",
            hint="set payments.withholding.periods_remaining or pass "
                 "--periods-remaining")

    # Already at or past the target with no additional withholding? Money
    # cannot be un-withheld, so zero is the best available answer.
    at_zero = pipeline.run(with_withholding_per_period(inp, ZERO, periods),
                           data, compute_marginals=False)
    if at_zero.balance_due_or_refund - target <= TOLERANCE:
        return ZERO

    lo, hi = ZERO, _estimate_upper_bound(inp, data, periods)
    # Ensure the bound actually brackets the target.
    for _ in range(8):
        result = pipeline.run(with_withholding_per_period(inp, hi, periods),
                              data, compute_marginals=False)
        if result.balance_due_or_refund - target <= ZERO:
            break
        hi = hi * 2
    for _ in range(MAX_ITER):
        mid = (lo + hi) / 2
        result = pipeline.run(with_withholding_per_period(inp, mid, periods),
                              data, compute_marginals=False)
        delta = result.balance_due_or_refund - target
        if abs(delta) <= TOLERANCE:
            return mid.round_cent()
        if delta > ZERO:
            lo = mid  # still owing too much → withhold more
        else:
            hi = mid
    raise ConvergenceError(
        "withholding solver failed to converge within 64 iterations")


def solve_safe_harbor(inp: TaxInput, data: ResolvedData,
                      *, periods: int | None = None) -> Money:
    """Minimum per-period withholding that satisfies the safe harbor."""
    if periods is None:
        periods = inp.payments.withholding.periods_remaining
    if periods <= 0:
        raise UsageError(
            "no pay periods remain — the solver has nothing to adjust",
            hint="set payments.withholding.periods_remaining")
    current = Money(inp.payments.withholding.federal_per_period)
    base = pipeline.run(with_withholding_per_period(inp, current, periods),
                        data, compute_marginals=False)
    sh = base.safe_harbor
    if sh is None or sh.required is None:
        raise UsageError(
            "safe-harbor requirement cannot be determined",
            hint="prior-year figures are missing; set payments.prior_year")
    if sh.shortfall <= ZERO:
        return current.round_cent()
    return (current + sh.shortfall / periods).round_cent()
