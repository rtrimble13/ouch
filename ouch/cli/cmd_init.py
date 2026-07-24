"""`ouch init` — interactive first-run setup (spec vignette 1)."""

from __future__ import annotations

import typer

from ouch.cli.common import Runtime
from ouch.config import profile as profile_mod
from ouch.model.enums import FilingStatus

_STATUSES = list(FilingStatus)


def init(ctx: typer.Context) -> None:
    rt: Runtime = ctx.obj
    console = rt.console()
    console.print("Welcome to ouch. Let's set up your tax profile.\n")

    year = typer.prompt("Tax year", default=rt.tax_year, type=int)
    console.print("Filing status:")
    for i, status in enumerate(_STATUSES, 1):
        console.print(f"  {i}) {status.value.replace('_', ' ').title()}")
    choice = typer.prompt("Choose", default=1, type=int)
    status = _STATUSES[min(max(choice, 1), len(_STATUSES)) - 1]
    birth = typer.prompt("Date of birth [YYYY-MM-DD]", default="", show_default=False)
    state = typer.prompt("State of residence [two-letter]", default="").upper()
    if state in ("TX", "FL", "WA", "NV", "TN", "SD", "WY", "AK", "NH"):
        console.print(f"  ℹ {state} has no state income tax.")
    dependents = typer.prompt("Dependents", default=0, type=int)

    console.print("\nIncome — you can add more later by editing the profile.")
    wages = typer.prompt("  W-2 wages (box 1)", default="0")
    withheld = typer.prompt("  Federal income tax withheld (box 2)", default="0")
    interest = typer.prompt("  Interest income", default="0")
    ord_div = typer.prompt("  Ordinary dividends", default="0")
    qual_div = typer.prompt("  Qualified dividends (box 1b, subset of the above)",
                            default="0")
    ltcg = typer.prompt("  Long-term capital gains", default="0")

    lines = [
        f"schema_version = {profile_mod.PROFILE_SCHEMA_VERSION}",
        f"tax_year       = {year}",
        "",
        "[taxpayer]",
        f'filing_status  = "{status.value}"',
    ]
    if birth:
        lines.append(f'birth_date     = "{birth}"')
    lines += [
        f'state          = "{state}"',
        "",
    ]
    for i in range(dependents):
        lines += ["[[dependents]]", f'name = "dependent {i + 1}"',
                  'relationship = "child"', ""]
    lines += [
        "[income.wages]",
        f"taxpayer_w2 = {wages}",
        "",
        "[income.investment]",
        f"interest            = {interest}",
        f"ordinary_dividends  = {ord_div}",
        f"qualified_dividends = {qual_div}",
        f"long_term_gains     = {ltcg}",
        "",
        "[payments.withholding]",
        f"federal_ytd = {withheld}",
        "",
    ]
    content = "\n".join(lines)

    path = profile_mod.resolve_profile_path(rt.profile_name)
    if rt.dry_run:
        print(content)
        return
    profile_mod.write_profile(path, content)
    console.print(f"\n✔ Profile written to {path}")
    console.print("  Run `ouch estimate` to see where you stand.")
