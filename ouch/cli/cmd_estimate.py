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
        help="Run all legal statuses side by side"),
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

    inp = load_input(rt, extra_overrides=overrides, state_override=state,
                     locality_override=locality)
    data = load_data(inp, federal_only=federal_only)
    result = pipeline.run(inp, data)
    console = rt.console()

    if rt.output_format == "json":
        text = render_json(result)
        out = getattr(rt, "output_path", None)
        if out:
            out.write_text(text + "\n")
        else:
            print(text)
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
