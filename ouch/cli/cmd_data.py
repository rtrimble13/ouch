"""`ouch data` — list | validate | show | verify (spec §6.5)."""

from __future__ import annotations

import json
from typing import Optional

import typer

from ouch.cli.common import Runtime
from ouch.errors import TaxDataError
from ouch.taxdata import loader

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_cmd(ctx: typer.Context) -> None:
    """Jurisdictions × years available."""
    rt: Runtime = ctx.obj
    console = rt.console()
    for kind, names in loader.list_available().items():
        console.print(f"[bold]{kind}[/bold]: " + (", ".join(names) or "(none)"))


@app.command("validate")
def validate(ctx: typer.Context) -> None:
    """Schema-check every file; exit 1 on any error."""
    rt: Runtime = ctx.obj
    console = rt.console()
    results = loader.validate_all()
    failed = False
    for name, error in results:
        if error is None:
            console.print(f"  ✔ {name}")
        else:
            failed = True
            console.print(f"  ✖ {name}")
            for line in error.splitlines():
                console.print(f"      {line}")
    if failed:
        raise TaxDataError("one or more tax data files failed validation")
    console.print(f"✔ {len(results)} data files valid")


@app.command("show")
def show(ctx: typer.Context,
         kind: str = typer.Argument(..., help="federal | state | local"),
         name: str = typer.Argument(..., help="year (federal) or CODE for "
                                              "state/local"),
         year: Optional[int] = typer.Argument(None),
         key: Optional[str] = typer.Option(None, "--key",
                                           help="Dotted key, e.g. qbi")) -> None:
    """Show a data file (optionally one key)."""
    rt: Runtime = ctx.obj
    if kind == "federal":
        doc = loader.raw_file("federal", "", int(name))
    else:
        if year is None:
            raise TaxDataError(f"usage: ouch data show {kind} CODE YEAR")
        doc = loader.raw_file(kind, name.upper(), year)
    if key:
        for part in key.split("."):
            if not isinstance(doc, dict) or part not in doc:
                raise TaxDataError(f"key '{key}' not found in data file")
            doc = doc[part]
    rt.echo(json.dumps(doc, indent=2, default=str))


@app.command("verify")
def verify(ctx: typer.Context) -> None:
    """List unverified/projected files."""
    rt: Runtime = ctx.obj
    console = rt.console()
    unverified = []
    available = loader.list_available()
    for stem in available["federal"]:
        doc = loader.raw_file("federal", "", int(stem))
        if not doc.get("meta", {}).get("verified", False):
            unverified.append(f"federal/{stem}")
    for kind in ("state", "local"):
        for stem in available[kind]:
            name, y = stem.rsplit("-", 1)
            doc = loader.raw_file(kind, name, int(y))
            if not doc.get("meta", {}).get("verified", False):
                unverified.append(f"{kind}/{stem}")
    if unverified:
        console.print("Unverified / projected data files "
                      "(results carry a warning):")
        for name in unverified:
            console.print(f"  ⚠ {name}")
    else:
        console.print("✔ all data files are verified against primary sources")
