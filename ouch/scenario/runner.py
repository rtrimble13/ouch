"""Scenario runner: run, compare, sweep (spec §12.2–12.4).

Because the core is pure, a scenario run is just the pipeline again with a
modified input; sweeps cache on input fingerprint.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from ouch.engine import pipeline
from ouch.engine.pipeline import ResolvedData
from ouch.errors import ComputationError, UsageError
from ouch.model.input import TaxInput
from ouch.model.money import Money, ZERO
from ouch.model.result import TaxResult
from ouch.scenario.model import (Scenario, apply_patch, get_path,
                                 resolve_patch_value)

DEFAULT_CLIFF_THRESHOLD = Decimal("0.03")  # marginal-rate jump between steps

# Tax data for a run: either fixed, or resolved from each patched input. A
# patch can change the jurisdiction (taxpayer.state / locality /
# former_state / residency_months) or the year, so callers that accept
# arbitrary patches must pass a resolver — fixed data would apply the
# original jurisdiction's rates under the new one's name.
DataSource = ResolvedData | Callable[[TaxInput], ResolvedData]


def resolve_data(source: DataSource, inp: TaxInput) -> ResolvedData:
    return source if isinstance(source, ResolvedData) else source(inp)


def result_metric(result: TaxResult, dotted: str) -> Decimal:
    """Resolve a metric path like 'result.marginal_rate_federal' or
    'total_tax_all_jurisdictions' to a Decimal."""
    path = dotted.removeprefix("result.")
    node: Any = result
    for part in path.split("."):
        if isinstance(node, dict):
            if part not in node:
                raise UsageError(f"unknown metric '{dotted}'")
            node = node[part]
        elif hasattr(node, part):
            node = getattr(node, part)
        else:
            raise UsageError(
                f"unknown metric '{dotted}'",
                hint="use TaxResult field names, e.g. "
                     "total_tax_all_jurisdictions, marginal_rate_combined")
    if isinstance(node, Money):
        return node.round_cent().amount
    if isinstance(node, Decimal):
        return node
    if isinstance(node, int):
        return Decimal(node)
    raise UsageError(f"metric '{dotted}' is not numeric")


def check_assertions(scenario: Scenario, result: TaxResult) -> list[str]:
    """Return failure messages for violated [assert] guardrails."""
    failures = []
    ops: dict[str, Callable[[Decimal, Decimal], bool]] = {
        "lt": lambda a, b: a < b, "le": lambda a, b: a <= b,
        "gt": lambda a, b: a > b, "ge": lambda a, b: a >= b,
        "eq": lambda a, b: a == b,
    }
    for assertion in scenario.assertions:
        actual = result_metric(result, assertion.path)
        if not ops[assertion.op](actual, assertion.value):
            failures.append(
                f"assert {assertion.path} {assertion.op} {assertion.value} "
                f"violated (actual {actual})")
    return failures


@dataclass(frozen=True)
class ScenarioRun:
    scenario: Scenario
    input: TaxInput
    result: TaxResult
    assertion_failures: tuple[str, ...]
    patch_delta: Money  # net numeric change across patched paths


def _patch_delta(base_raw: dict, scenario: Scenario) -> Money:
    delta = ZERO
    for dotted, value in scenario.patch.items():
        resolved = resolve_patch_value(base_raw, dotted, value)
        old = get_path(base_raw, dotted, 0) or 0
        try:
            delta += Money(str(resolved)) - Money(str(old))
        except Exception:
            pass  # non-numeric patches (state code, filing status) carry no Δ
    return delta


def run_scenario(base_raw: dict, scenario: Scenario, data: DataSource,
                 build_input: Callable[[dict], TaxInput], *,
                 compute_marginals: bool = True) -> ScenarioRun:
    patched = apply_patch(base_raw, scenario.patch)
    inp = build_input(patched)
    result = pipeline.run(inp, resolve_data(data, inp),
                          compute_marginals=compute_marginals)
    return ScenarioRun(
        scenario=scenario, input=inp, result=result,
        assertion_failures=tuple(check_assertions(scenario, result)),
        patch_delta=_patch_delta(base_raw, scenario),
    )


def marginal_cost(baseline: TaxResult, run: ScenarioRun) -> Decimal | None:
    """Δtax ÷ Δinput — the number that answers the user's actual question
    (spec §12.3). None when the patch has no numeric delta."""
    if run.patch_delta == ZERO:
        return None
    dtax = run.result.total_tax_all_jurisdictions - baseline.total_tax_all_jurisdictions
    return dtax.ratio(run.patch_delta).quantize(Decimal("0.0001"))


# ---------------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SweepPoint:
    value: Decimal
    metrics: dict[str, Decimal]
    total_tax: Decimal
    step_marginal: Decimal | None    # Δtax/Δvar vs previous point
    cliff: bool


def sweep(base_raw: dict, var: str, lo: Decimal, hi: Decimal, step: Decimal,
          metrics: list[str], data: DataSource,
          build_input: Callable[[dict], TaxInput], *,
          cliff_threshold: Decimal = DEFAULT_CLIFF_THRESHOLD) -> list[SweepPoint]:
    if step <= 0 or hi < lo:
        raise UsageError("sweep range must be LO:HI:STEP with STEP > 0, HI >= LO")
    n_steps = int((hi - lo) / step)
    if n_steps > 2000:
        raise UsageError(f"sweep would evaluate {n_steps + 1} points; "
                         "use a coarser step")
    need_marginals = any("marginal" in m for m in metrics)

    cache: dict[str, TaxResult] = {}
    points: list[SweepPoint] = []
    prev_tax: Decimal | None = None
    prev_marginal: Decimal | None = None
    value = lo
    while value <= hi:
        patched = apply_patch(base_raw, {var: str(value)})
        inp = build_input(patched)
        fp = inp.fingerprint()
        result = cache.get(fp)
        if result is None:
            result = pipeline.run(inp, resolve_data(data, inp),
                                  compute_marginals=need_marginals)
            cache[fp] = result
        total = result.total_tax_all_jurisdictions.round_cent().amount
        step_marginal: Decimal | None = None
        cliff = False
        if prev_tax is not None:
            step_marginal = ((total - prev_tax) / step).quantize(Decimal("0.0001"))
            if (prev_marginal is not None
                    and step_marginal - prev_marginal > cliff_threshold):
                cliff = True
            prev_marginal = step_marginal
        points.append(SweepPoint(
            value=value,
            metrics={m: result_metric(result, m) for m in metrics},
            total_tax=total, step_marginal=step_marginal, cliff=cliff))
        prev_tax = total
        value += step
    return points
