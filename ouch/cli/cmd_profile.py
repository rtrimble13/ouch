"""`ouch profile` — show | validate | new | path."""

from __future__ import annotations

import typer

from ouch.cli.common import Runtime, load_input
from ouch.config import profile as profile_mod

app = typer.Typer(no_args_is_help=True)


@app.command("show")
def show(ctx: typer.Context) -> None:
    """Print the resolved profile as validated input."""
    rt: Runtime = ctx.obj
    inp = load_input(rt)
    print(inp.model_dump_json(indent=2))


@app.command("validate")
def validate(ctx: typer.Context) -> None:
    """Validate the profile; exit 0 when clean."""
    rt: Runtime = ctx.obj
    inp = load_input(rt)  # raises SchemaError (exit 3) on failure
    rt.console().print(
        f"✔ profile '{rt.profile_name}' is valid "
        f"(tax year {inp.tax_year}, {inp.taxpayer.filing_status})")


@app.command("new")
def new(ctx: typer.Context,
        name: str = typer.Argument("default")) -> None:
    """Write a template profile."""
    rt: Runtime = ctx.obj
    path = profile_mod.resolve_profile_path(name)
    if path.exists():
        typer.confirm(f"{path} exists — overwrite (a backup is kept)?",
                      abort=True)
    content = profile_mod.PROFILE_TEMPLATE.format(year=rt.tax_year)
    if rt.dry_run:
        print(content)
        return
    profile_mod.write_profile(path, content)
    rt.console().print(f"✔ profile written to {path}")


@app.command("path")
def path_cmd(ctx: typer.Context) -> None:
    """Print the profile path in use."""
    rt: Runtime = ctx.obj
    print(profile_mod.resolve_profile_path(rt.profile_name))
