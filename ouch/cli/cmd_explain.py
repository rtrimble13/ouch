"""`ouch explain LINE_ID` — walk the derivation of any line (spec P2)."""

from __future__ import annotations

import typer

from ouch.cli.common import Runtime, load_data, load_input
from ouch.engine import pipeline
from ouch.errors import UsageError
from ouch.render.trace import render_explain


def explain(
    ctx: typer.Context,
    line_id: str = typer.Argument(..., help="Trace line id, e.g. fed.tax.total"),
) -> None:
    rt: Runtime = ctx.obj
    inp = load_input(rt)
    data = load_data(inp)
    result = pipeline.run(inp, data, compute_marginals=False)
    if not result.trace.has(line_id):
        available = ", ".join(sorted(i.id for i in result.trace.items))
        raise UsageError(
            f"no line item '{line_id}' in this computation",
            hint=f"available: {available}")
    render_explain(result.trace, line_id,
                   show_citations=bool(rt.settings.get("output.show_citations",
                                                       True)),
                   console=rt.console())
