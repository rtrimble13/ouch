"""`ouch scenario` — what-if analysis (spec §12)."""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

import typer

from ouch import DISCLAIMER
from ouch.cli.common import Runtime, data_resolver, prepare_raw
from ouch.config import profile as profile_mod
from ouch.engine import pipeline
from ouch.errors import ComputationError, UsageError
from ouch.model.money import Money, ZERO
from ouch.scenario import runner as runner_mod
from ouch.scenario.model import (Scenario, load_scenario, scenarios_dir)
from ouch.scenario.templates import TEMPLATES

app = typer.Typer(no_args_is_help=True)


def _base_raw(rt: Runtime, base: str) -> dict:
    raw, _ = profile_mod.load_profile_raw(
        base if base != "default" else rt.profile_name)
    prepare_raw(rt, raw)
    return raw


def _builder(rt: Runtime):
    return lambda raw: profile_mod.build_tax_input(raw, rt.tax_year)


def _baseline_scenario() -> Scenario:
    return Scenario(name="baseline", patch={})


def _load(rt: Runtime, name: str) -> Scenario:
    if name == "baseline":
        return _baseline_scenario()
    return load_scenario(name)


@app.command("new")
def new(ctx: typer.Context,
        name: str = typer.Argument(...),
        set_: List[str] = typer.Option([], "--set",
                                       help="Patch entry PATH=VALUE, repeatable"),
        template: Optional[str] = typer.Option(None, "--template",
                                               help=", ".join(sorted(TEMPLATES))),
        base: str = typer.Option("default", "--base")) -> None:
    """Create a scenario from --set entries or a template."""
    rt: Runtime = ctx.obj
    path = scenarios_dir() / f"{name}.toml"
    if path.exists():
        raise UsageError(f"scenario '{name}' already exists at {path}",
                         hint="delete it first with `ouch scenario delete`")
    if template is not None:
        if template not in TEMPLATES:
            raise UsageError(f"unknown template '{template}'",
                             hint="available: " + ", ".join(sorted(TEMPLATES)))
        content = TEMPLATES[template].format(name=name, base=base)
    else:
        if not set_:
            raise UsageError("provide --set PATH=VALUE entries or --template")
        lines = [f'name = "{name}"', f'base = "{base}"', "", "[patch]"]
        for entry in set_:
            key, _, value = entry.partition("=")
            value = value.strip()
            # Quote anything that is not a bare number so TOML stays valid.
            try:
                float(value)
                rendered = value
            except ValueError:
                rendered = f'"{value}"'
            lines.append(f'"{key.strip()}" = {rendered}')
        content = "\n".join(lines) + "\n"
    if rt.dry_run:
        rt.echo(content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    rt.console().print(f"✔ scenario written to {path}")


@app.command("list")
def list_cmd(ctx: typer.Context) -> None:
    rt: Runtime = ctx.obj
    console = rt.console()
    d = scenarios_dir()
    entries = sorted(d.glob("*.toml")) if d.is_dir() else []
    if not entries:
        console.print("no scenarios — create one with `ouch scenario new`")
        return
    for p in entries:
        s = load_scenario(str(p))
        tags = f"  [{', '.join(s.tags)}]" if s.tags else ""
        console.print(f"  {p.stem:<24} {s.description}{tags}")


@app.command("show")
def show(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    rt: Runtime = ctx.obj
    s = _load(rt, name)
    console = rt.console()
    console.print(f"[bold]{s.name}[/bold] (base: {s.base})")
    if s.description:
        console.print(f"  {s.description}")
    for path, value in s.patch.items():
        console.print(f"  {path} = {value!r}")
    for a in s.assertions:
        console.print(f"  assert {a.path} {a.op} {a.value}")


@app.command("delete")
def delete(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    rt: Runtime = ctx.obj
    path = scenarios_dir() / f"{name}.toml"
    if not path.is_file():
        raise UsageError(f"no scenario '{name}'")
    if not rt.dry_run:
        path.unlink()
    rt.console().print(f"✔ deleted {path}")


@app.command("run")
def run_cmd(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Run one scenario and show the comparison against baseline."""
    compare(ctx, names=["baseline", name])


@app.command("compare")
def compare(ctx: typer.Context,
            names: List[str] = typer.Argument(...,
                                              help="Scenario names; 'baseline' "
                                                   "is the unpatched profile")) -> None:
    """Compare scenarios side by side (spec §12.3)."""
    rt: Runtime = ctx.obj
    console = rt.console()
    scenarios = [_load(rt, n) for n in names]
    base = scenarios[0].base
    raw = _base_raw(rt, base)
    build = _builder(rt)
    # Per-scenario data: a patch to taxpayer.state etc. must load that
    # jurisdiction's rates, not reuse the base profile's.
    data = data_resolver()

    runs = [runner_mod.run_scenario(raw, s, data, build) for s in scenarios]
    baseline = runs[0].result

    rows: list[tuple[str, list[Money | Decimal]]] = [
        ("AGI", [r.result.agi for r in runs]),
        ("Taxable income", [r.result.taxable_income for r in runs]),
        ("Federal total", [r.result.federal_total_tax for r in runs]),
    ]
    if any(r.result.niit > ZERO for r in runs):
        rows.append(("NIIT", [r.result.niit for r in runs]))
    if any(r.result.state is not None for r in runs):
        rows.append(("State tax", [
            r.result.state.tax if r.result.state else ZERO for r in runs]))
    if any(r.result.local is not None for r in runs):
        rows.append(("Local tax", [
            r.result.local.tax if r.result.local else ZERO for r in runs]))
    rows.append(("TOTAL TAX", [r.result.total_tax_all_jurisdictions
                               for r in runs]))

    width = 14
    header = f"{'':28}" + "".join(f"{r.scenario.name[:width - 1]:>{width}}"
                                  for r in runs)
    console.print(header)
    console.print("─" * len(header))
    for label, values in rows:
        line = f"{label:<28}"
        for v in values:
            line += f"{v.fmt():>{width}}"
        console.print(line)
    line = f"{'Effective rate (AGI)':<28}"
    for r in runs:
        line += f"{r.result.effective_rate_agi * 100:>{width - 1}.2f}%"
    console.print(line)
    line = f"{'Marginal rate (next $)':<28}"
    for r in runs:
        line += f"{r.result.marginal_rate_combined * 100:>{width - 1}.2f}%"
    console.print(line)

    for r in runs[1:]:
        dtax = (r.result.total_tax_all_jurisdictions
                - baseline.total_tax_all_jurisdictions)
        console.print(f"\n{r.scenario.name}: Δ tax vs baseline "
                      f"{dtax.fmt()}")
        cost = runner_mod.marginal_cost(baseline, r)
        if cost is not None:
            console.print(f"  Marginal cost of the change: "
                          f"{cost * 100:.2f}% of the changed amount "
                          f"(Δ input {r.patch_delta.fmt()})")
        # Threshold spillover callouts (spec §12.3)
        if baseline.niit == ZERO and r.result.niit > ZERO:
            console.print(f"  ⚠ Crosses the NIIT threshold — "
                          f"{r.result.niit.fmt()} of the increase is NIIT")
        if (baseline.amt_additional == ZERO
                and r.result.amt_additional > ZERO):
            console.print("  ⚠ Triggers the alternative minimum tax")
        for failure in r.assertion_failures:
            console.print(f"  ✖ {failure}")
    if any(r.assertion_failures for r in runs):
        raise ComputationError("scenario assertion violated (see above)")
    console.print(f"\n[dim]{DISCLAIMER.splitlines()[0]}[/dim]")


@app.command("sweep")
def sweep_cmd(
    ctx: typer.Context,
    var: str = typer.Option(..., "--var", help="Dotted profile path to sweep"),
    range_: str = typer.Option(..., "--range", help="LO:HI:STEP"),
    metric: str = typer.Option("total_tax_all_jurisdictions,marginal_rate_combined",
                               "--metric", help="Comma-separated result metrics"),
    cliff_threshold: float = typer.Option(0.03, "--cliff-threshold",
                                          help="Marginal-rate jump that flags "
                                               "a cliff"),
) -> None:
    """Evaluate a variable across a range; reveal cliffs (spec §12.4)."""
    rt: Runtime = ctx.obj
    try:
        lo_s, hi_s, step_s = range_.split(":")
        lo, hi, step = Decimal(lo_s), Decimal(hi_s), Decimal(step_s)
    except (ValueError, ArithmeticError) as e:
        raise UsageError(f"--range must be LO:HI:STEP, got '{range_}'") from e
    metrics = [m.strip() for m in metric.split(",") if m.strip()]

    raw = _base_raw(rt, "default")
    build = _builder(rt)
    data = data_resolver()
    points = runner_mod.sweep(
        raw, var, lo, hi, step, metrics, data, build,
        cliff_threshold=Decimal(str(cliff_threshold)))

    if rt.output_format == "csv":
        header = [var, "total_tax", "step_marginal", "cliff"] + metrics
        rt.echo(",".join(header))
        for p in points:
            row = [str(p.value), str(p.total_tax),
                   "" if p.step_marginal is None else str(p.step_marginal),
                   "1" if p.cliff else ""]
            row += [str(p.metrics[m]) for m in metrics]
            rt.echo(",".join(row))
        return

    console = rt.console()
    console.print(f"{var:>14}{'Total tax':>14}{'Δ tax/Δ var':>14}   " +
                  "".join(f"{m[:18]:>20}" for m in metrics))
    console.print("─" * (42 + 20 * len(metrics)))
    prev_total: Decimal | None = None
    for p in points:
        marginal = ("—" if p.step_marginal is None
                    else f"{p.step_marginal * 100:.2f}%")
        line = (f"{p.value:>14,.0f}{p.total_tax:>14,.0f}{marginal:>14}   "
                + "".join(f"{p.metrics[m]:>20,.4f}" for m in metrics))
        if p.cliff:
            line += "   ⚠ cliff"
        console.print(line)
    cliffs = [p for p in points if p.cliff]
    for p in cliffs:
        console.print(f"\n⚠ Cliff detected at {var} ≈ {p.value:,.0f}: "
                      f"marginal rate jumps to {p.step_marginal * 100:.1f}% — "
                      "a threshold or phase-out sits between the neighboring "
                      "steps")
    console.print(f"\n[dim]{DISCLAIMER.splitlines()[0]}[/dim]")
