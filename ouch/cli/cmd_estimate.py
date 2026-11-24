"""`ouch estimate` — UC-1: total burden + effective rate (spec §8.3)."""

from __future__ import annotations

from typing import List, Optional

import typer

from ouch.cli.common import Runtime, load_data, load_input
from ouch.engine import pipeline
from ouch.model.enums import FilingStatus
from ouch.render.json_out import render_json
from ouch.render.table import render_summary
from ouch.render.trace import render_explain, render_full_trace


def estimate(
    ctx: typer.Context,
    federal_only: bool = typer.Option(False, "--federal-only",
                                      help="Skip state and local"),
    state: Optional[str] = typer.Option(None, "--state",
                                        help="Override profile state"),
    locality: Optional[str] = typer.Option(None, "--locality",
                                           help="Override profile locality"),
    compare_filing_status: bool = typer.Option(
        False, "--compare-filing-status",
        help="Compare the filing statuses this profile can claim "
             "(single, head of household, surviving spouse) side by side. "
             "Married profiles: model each spouse's separate return as its "
             "own profile."),
    itemize: bool = typer.Option(False, "--itemize",
                                 help="Force itemized deduction"),
    standard: bool = typer.Option(False, "--standard",
                                  help="Force standard deduction"),
    marginal: bool = typer.Option(False, "--marginal",
                                  help="Show marginal rate detail"),
    breakdown: bool = typer.Option(False, "--breakdown",
                                   help="Full line-item table"),
    set_: List[str] = typer.Option([], "--set",
                                   help="Ad-hoc override PATH=VALUE, repeatable"),
) -> None:
    rt: Runtime = ctx.obj
    overrides = list(set_)
    if itemize and standard:
        from ouch.errors import UsageError
        raise UsageError("--itemize and --standard are mutually exclusive")
    if itemize:
        overrides.append("deductions.mode=itemized")
    if standard:
        overrides.append("deductions.mode=standard")

    if compare_filing_status and (marginal or breakdown or rt.explain):
        from ouch.errors import UsageError
        raise UsageError("--compare-filing-status cannot be combined with "
                         "--marginal, --breakdown or --explain",
                         hint="run the comparison, then estimate the chosen "
                              "status with --set taxpayer.filing_status=…")

    inp = load_input(rt, extra_overrides=overrides, state_override=state,
                     locality_override=locality)
    data = load_data(inp, federal_only=federal_only)
    if compare_filing_status:
        _compare_statuses(rt, inp, data)
        return
    result = pipeline.run(inp, data)
    console = rt.console()

    if rt.output_format == "json":
        rt.echo(render_json(result))
        return

    render_summary(result, inp.taxpayer.filing_status,
                   inp.taxpayer.state.upper(), inp.taxpayer.locality.upper(),
                   verbosity=rt.verbosity, console=console)

    if marginal:
        console.print(
            f"  Marginal (federal, next $1,000): "
            f"{result.marginal_rate_federal * 100:.2f}%   "
            f"Marginal (combined): {result.marginal_rate_combined * 100:.2f}%")
    if breakdown or rt.verbosity >= 3:
        render_full_trace(result.trace, console=console)
    if rt.explain:
        render_explain(result.trace, "fed.tax.total", console=console)


_SHORT_LABEL = {
    FilingStatus.SINGLE: "Single",
    FilingStatus.HEAD_OF_HOUSEHOLD: "Head of household",
    FilingStatus.QUALIFYING_SURVIVING_SPOUSE: "Surviving spouse",
}


def _compare_statuses(rt: Runtime, inp, data) -> None:
    """`--compare-filing-status`: the pipeline once per computable status."""
    from ouch import DISCLAIMER
    from ouch.engine.filing_status import (MARRIED, status_alternatives,
                                           with_status)
    from ouch.errors import UsageError
    from ouch.model.money import ZERO
    from ouch.render.json_out import result_to_dict

    current = inp.taxpayer.filing_status
    if current in MARRIED:
        raise UsageError(
            "--compare-filing-status cannot split a joint profile into two "
            "separate returns — investment income, deductions and payments "
            "are not attributed per spouse",
            hint="create one profile per spouse with filing_status = "
                 "\"married_filing_separately\", then compare the sum of "
                 "their `ouch --profile NAME estimate` totals with the joint "
                 "total")
    options = status_alternatives(inp)
    runs = [(s, pipeline.run(with_status(inp, s), data))
            for s in options.statuses]

    if rt.output_format == "json":
        import json
        import ouch
        rt.echo(json.dumps({
            "ouch_version": ouch.__version__,
            "tax_year": inp.tax_year,
            "current_filing_status": str(current),
            "comparison": [{"filing_status": str(s),
                            "result": result_to_dict(r)} for s, r in runs],
            "omitted": [{"filing_status": str(s), "reason": why}
                        for s, why in options.omitted],
        }, indent=2))
        return

    console = rt.console()
    label_w, width = 22, 19      # three statuses fit in 79 columns
    place = inp.taxpayer.state.upper() or "no state"
    console.print(f"Filing status comparison · Tax Year {inp.tax_year} · "
                  f"{place}\n")
    console.print(f"{'':{label_w}}" + "".join(
        f"{_SHORT_LABEL[s]:>{width}}" for s, _ in runs), markup=False)
    console.print(f"{'':{label_w}}" + "".join(
        f"{'(current)' if s == current else '':>{width}}" for s, _ in runs),
        markup=False)
    console.print("─" * (label_w + width * len(runs)))

    def row(label: str, values) -> None:
        console.print(f"{label:<{label_w}}" + "".join(
            f"{v.fmt():>{width}}" for v in values), markup=False)

    results = [r for _, r in runs]
    row("AGI", [r.agi for r in results])
    row("Deduction", [r.deduction_taken for r in results])
    row("Taxable income", [r.taxable_income for r in results])
    row("Credits", [r.credits_nonrefundable + r.credits_refundable
                    for r in results])
    row("Federal total", [r.federal_total_tax for r in results])
    if any(r.state is not None for r in results):
        row("State tax", [r.state.tax if r.state else ZERO for r in results])
    if any(r.local is not None for r in results):
        row("Local tax", [r.local.tax if r.local else ZERO for r in results])
    row("TOTAL TAX", [r.total_tax_all_jurisdictions for r in results])
    row("Balance / (refund)", [r.balance_due_or_refund for r in results])
    console.print(f"{'Effective rate (AGI)':<{label_w}}" + "".join(
        f"{r.effective_rate_agi * 100:>{width - 1}.2f}%" for r in results))

    baseline = dict(runs)[current].total_tax_all_jurisdictions
    best_status, best = min(runs, key=lambda sr:
                            sr[1].total_tax_all_jurisdictions.cents)
    saving = baseline - best.total_tax_all_jurisdictions
    if best_status != current and saving > ZERO:
        console.print(f"\nLowest total tax: {_SHORT_LABEL[best_status]} — "
                      f"{saving.fmt()} less than "
                      f"{_SHORT_LABEL[current].lower()} (current).")
    else:
        console.print(f"\nYour current status ({_SHORT_LABEL[current].lower()}) "
                      "already has the lowest total tax of those compared.")
    for s, why in options.omitted:
        console.print(f"  · {_SHORT_LABEL[s]} not computed: {why}",
                      markup=False)
    console.print("\n  ⚠ Eligibility is checked only against the profile — "
                  "confirm the marital-status, household-cost and "
                  "dependency tests yourself (IRS Pub. 501).", markup=False)
    console.print(f"\n[dim]{DISCLAIMER.splitlines()[0]}[/dim]")
