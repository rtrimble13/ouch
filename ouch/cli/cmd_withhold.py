"""`ouch withhold` — UC-2 (spec §10)."""

from __future__ import annotations

from typing import Optional

import typer

from ouch import DISCLAIMER
from ouch.cli.common import Runtime, load_data, load_input
from ouch.engine import pipeline, solver
from ouch.errors import UsageError
from ouch.model.money import Money, ZERO

app = typer.Typer(no_args_is_help=True)


@app.command("check")
def check(ctx: typer.Context) -> None:
    """Are you on track? Safe-harbor status (spec §10.1)."""
    rt: Runtime = ctx.obj
    inp = load_input(rt)
    data = load_data(inp)
    result = pipeline.run(inp, data, compute_marginals=False)
    console = rt.console()
    sh = result.safe_harbor

    # Every line in this walk is all-jurisdiction, so withheld-to-date +
    # projected withholding + estimated payments = projected total payments
    # (the same composition as engine.payments.project_payments).
    w = inp.payments.withholding
    e = inp.payments.estimated
    per_period = (Money(w.federal_per_period) + Money(w.state_per_period)
                  + Money(w.local_per_period))
    additional = per_period * w.periods_remaining
    estimated = sum((Money(x) for x in (
        e.q1_federal, e.q2_federal, e.q3_federal, e.q4_federal,
        e.state_total, e.local_total)), ZERO)
    multi = w.state_per_period > 0 or w.local_per_period > 0

    console.print(f"Projected total tax                     "
                  f"{result.total_tax_all_jurisdictions.fmt():>12}")
    console.print(f"Withheld to date (all jurisdictions)    "
                  f"{(Money(w.federal_ytd) + Money(w.state_ytd) + Money(w.local_ytd)).fmt():>12}")
    console.print(f"Projected additional withholding        {additional.fmt():>12}"
                  f"     ({w.periods_remaining} periods × "
                  f"$ {per_period.round_dollar().amount:,.0f})")
    if multi:
        console.print("  per period: " + " · ".join(
            f"{name} {Money(v).fmt()}" for name, v in (
                ("federal", w.federal_per_period),
                ("state", w.state_per_period),
                ("local", w.local_per_period)) if v > 0))
    if estimated > ZERO:
        console.print(f"Estimated payments                      "
                      f"{estimated.fmt():>12}")
    console.print(f"Projected total payments                "
                  f"{result.total_payments.fmt():>12}")
    console.print("─" * 60)
    balance = result.balance_due_or_refund
    label = ("Projected balance due" if balance >= ZERO else "Projected refund")
    console.print(f"{label:<40}{abs(balance).fmt():>12}\n")

    if sh is not None:
        console.print("Safe harbor analysis (federal):")
        console.print(f"  90% of current-year tax               "
                      f"{sh.current_year_90pct.fmt():>12}")
        if sh.prior_year_pct is not None:
            console.print(f"  {sh.prior_year_pct_label} of prior-year tax"
                          f"{'':<15}{sh.prior_year_pct.fmt():>12}")
        else:
            console.print("  Prior-year test unavailable (no prior-year figures)")
        console.print(f"  Projected federal payments            "
                      f"{sh.projected_federal_payments.fmt():>12}")
        if sh.met is True:
            console.print("  Status: ✔ safe harbor met")
        elif sh.met is False:
            console.print(f"  Status: ✗ SHORT by {sh.shortfall.fmt()}")
            console.print(f"  Estimated underpayment penalty        "
                          f"{sh.estimated_penalty.fmt():>12}"
                          "   (Form 2210 approximation)")
        else:
            console.print(f"  Status: ? current-year test shortfall "
                          f"{sh.shortfall.fmt()} (prior-year data missing)")
    for warning in result.warnings:
        console.print(f"  ⚠ {warning}")
    console.print(f"\n[dim]{DISCLAIMER.splitlines()[0]}[/dim]")


@app.command("solve")
def solve(
    ctx: typer.Context,
    target: str = typer.Option("zero", "--target",
                               help="zero | refund:AMOUNT | owe:AMOUNT | safe-harbor"),
    periods_remaining: Optional[int] = typer.Option(
        None, "--periods-remaining", help="Override auto-derived count"),
    w4: bool = typer.Option(False, "--w4", help="Also emit W-4 line entries"),
) -> None:
    """Per-paycheck federal withholding to hit a target (spec §10.2)."""
    rt: Runtime = ctx.obj
    inp = load_input(rt)
    data = load_data(inp)

    periods = periods_remaining or inp.payments.withholding.periods_remaining
    if target == "safe-harbor":
        per_period = solver.solve_safe_harbor(inp, data, periods=periods)
        goal_label = "meet the federal safe harbor (penalty avoidance only)"
    else:
        if target == "zero":
            goal = ZERO
            goal_label = "a $0 balance"
        elif target.startswith("refund:"):
            goal = -Money(target.split(":", 1)[1])
            goal_label = f"a refund of $ {(-goal).round_dollar().amount:,.0f}"
        elif target.startswith("owe:"):
            goal = Money(target.split(":", 1)[1])
            goal_label = f"owing $ {goal.round_dollar().amount:,.0f} in April"
        else:
            raise UsageError(
                f"unknown --target '{target}'",
                hint="use zero, refund:AMOUNT, owe:AMOUNT, or safe-harbor")
        per_period = solver.solve_withholding(inp, data, goal, periods=periods)

    current = Money(inp.payments.withholding.federal_per_period)
    extra = per_period - current
    console = rt.console()
    console.print(f"{periods} pay periods remain in {inp.tax_year}.\n")
    console.print(f"To reach {goal_label}:")
    console.print(f"  Federal withholding per period      "
                  f"{per_period.round_cent().fmt(dollars=False):>14}")
    console.print(f"  (currently {current.fmt(dollars=False)}; change of "
                  f"{extra.round_cent().fmt(dollars=False)} per period, "
                  f"{(extra * periods).fmt()} total)")

    solved = pipeline.run(
        solver.with_withholding_per_period(inp, per_period, periods), data,
        compute_marginals=False)
    balance = solved.balance_due_or_refund
    label = "balance due" if balance >= ZERO else "refund"
    console.print(f"  Resulting April {label}: {abs(balance).fmt()}")

    if w4:
        _render_w4(console, inp, extra)
    console.print(f"\n[dim]{DISCLAIMER.splitlines()[0]}[/dim]")


def _render_w4(console, inp, extra_per_period: Money) -> None:
    """Translate the solver output into W-4 levers (spec §10.3)."""
    both_spouses_work = (inp.income.wages.taxpayer_w2 > 0
                        and inp.income.wages.spouse_w2 > 0)
    n_children = len(inp.dependents)
    console.print("\nForm W-4 entries (give to ONE employer — the higher earner):")
    if both_spouses_work:
        console.print("  Step 2:  ☑ check the box (multiple jobs / spouse works)")
        console.print("  ⚠ Dual-earner under-withholding is the most common "
                      "cause of a surprise April bill; claim dependents on "
                      "ONE W-4 only.")
    if n_children:
        console.print(f"  Step 3:  dependents as computed on your return "
                      f"({n_children} dependent(s))")
    if inp.income.business.schedule_c_net > 0:
        console.print(f"  Step 4(a) other income: "
                      f"$ {inp.income.business.schedule_c_net:,.0f} (self-employment)")
    console.print(f"  Step 4(c) extra withholding per pay period: "
                  f"{max(extra_per_period, ZERO).round_dollar().fmt()}")
    console.print("  ouch does not fill out or submit a W-4; enter these with "
                  "your employer.")


@app.command("w4")
def w4(ctx: typer.Context) -> None:
    """Translate the zero-balance solve into W-4 line entries."""
    solve(ctx, target="zero", periods_remaining=None, w4=True)


@app.command("estimates")
def estimates(
    ctx: typer.Context,
    target: str = typer.Option("safe-harbor", "--target",
                               help="safe-harbor (minimum, no penalty) | "
                                    "zero (no April balance)"),
    annualized: bool = typer.Option(False, "--annualized",
                                    help="Use payments.annualized_income_"
                                         "fractions from the profile (lumpy "
                                         "income)"),
) -> None:
    """Quarterly estimated payment schedule with due dates (spec §10.4)."""
    from ouch.engine.payments import project_payments, quarterly_schedule

    rt: Runtime = ctx.obj
    inp = load_input(rt)
    if annualized and inp.payments.annualized_income_fractions is None:
        raise UsageError(
            "--annualized needs payments.annualized_income_fractions in the "
            "profile",
            hint='e.g. annualized_income_fractions = ["0.1","0.2","0.3","0.4"]')
    if not annualized and inp.payments.annualized_income_fractions is not None:
        inp = inp.model_copy(update={
            "payments": inp.payments.model_copy(
                update={"annualized_income_fractions": None})})
    data = load_data(inp)
    result = pipeline.run(inp, data, compute_marginals=False)
    projected_withholding = (result.safe_harbor.projected_federal_payments
                             - sum((Money(q) for q in (
                                 inp.payments.estimated.q1_federal,
                                 inp.payments.estimated.q2_federal,
                                 inp.payments.estimated.q3_federal,
                                 inp.payments.estimated.q4_federal)), ZERO))
    annual, schedule = quarterly_schedule(
        inp, data.federal, result.federal_total_tax, projected_withholding,
        target_zero=(target == "zero"))

    console = rt.console()
    console.print(f"{inp.tax_year} quarterly estimated payments (federal)\n")
    sh = result.safe_harbor
    console.print(f"  90% of current-year tax         "
                  f"{sh.current_year_90pct.fmt():>12}")
    if sh.prior_year_pct is not None:
        console.print(f"  {sh.prior_year_pct_label} of prior-year tax        "
                      f"{sh.prior_year_pct.fmt():>12}")
    console.print(f"  Withholding (counted as even)   "
                  f"{projected_withholding.fmt():>12}")
    console.print(f"  Required via estimates          {annual.fmt():>12}"
                  f"   (target: {target})\n")
    for q in schedule:
        status_mark = ("✔ paid" if q.paid >= q.required and q.required > ZERO
                       else ("—" if q.required == ZERO else "due"))
        console.print(f"  Q{q.quarter}  due {q.due_date}   "
                      f"{q.required.fmt():>12}   {status_mark}"
                      + (f"  (paid {q.paid.fmt()})" if q.paid > ZERO else ""))
    if annualized:
        console.print("\n  ℹ Annualized income installment method: payments "
                      "follow your income fractions (approximate — the "
                      "statutory Schedule AI factors are not applied).")
    else:
        console.print("\n  ℹ Income lumpy? `--annualized` with "
                      "payments.annualized_income_fractions shifts the "
                      "requirement toward the quarters that earn the income.")
    console.print(f"\n[dim]{DISCLAIMER.splitlines()[0]}[/dim]")
