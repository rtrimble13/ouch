"""Typer root application, global options, exit-code mapping (spec §8)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

try:  # standalone click (older typer)
    from click.exceptions import ClickException, UsageError as ClickUsageError
except ImportError:  # typer >= 0.16 vendors click
    from typer._click.exceptions import (ClickException,
                                         UsageError as ClickUsageError)

import ouch
from ouch.cli import (cmd_config, cmd_data, cmd_estimate, cmd_explain,
                      cmd_import, cmd_init, cmd_profile, cmd_scenario,
                      cmd_withhold)
from ouch.cli.common import build_runtime
from ouch.errors import OuchError

app = typer.Typer(
    name="ouch",
    help="A CPA-grade personal tax estimation CLI. "
         "The name is your reaction to the number.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ouch {ouch.__version__}")
        for extra, module in (("pdf", "pdfplumber"), ("ai", "anthropic"),
                              ("crypto", "cryptography")):
            try:
                mod = __import__(module)
                typer.echo(f"  [{extra}] {module} {getattr(mod, '__version__', '?')}")
            except ImportError:
                typer.echo(f"  [{extra}] not installed")
        raise typer.Exit(0)


@app.callback()
def root(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", envvar="OUCH_PROFILE",
        help="Profile name or path"),
    year: Optional[int] = typer.Option(
        None, "--year", "-y", envvar="OUCH_TAX_YEAR", help="Tax year"),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Alternate config.toml"),
    fmt: Optional[str] = typer.Option(
        None, "--format", "-f", help="table|json|csv|markdown"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Write to file instead of stdout"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Errors only"),
    no_color: bool = typer.Option(False, "--no-color", envvar="OUCH_NO_COLOR"),
    dry_run: bool = typer.Option(False, "--dry-run",
                                 help="Compute but write nothing to disk"),
    no_ai: bool = typer.Option(False, "--no-ai",
                               help="Hard-disable all network/AI paths"),
    explain: bool = typer.Option(False, "--explain",
                                 help="Append computation trace to output"),
    version: bool = typer.Option(False, "--version", callback=_version_callback,
                                 is_eager=True),
) -> None:
    ctx.obj = build_runtime(profile, year, config, fmt, verbose, quiet,
                            no_color, dry_run, explain)
    ctx.obj.output_path = output  # type: ignore[attr-defined]


app.command("init")(cmd_init.init)
app.command("estimate")(cmd_estimate.estimate)
app.command("explain")(cmd_explain.explain)
app.add_typer(cmd_withhold.app, name="withhold",
              help="Withholding: check trajectory, solve for a target, W-4 lines")
app.add_typer(cmd_scenario.app, name="scenario",
              help="What-if analysis: new | list | show | delete | run | "
                   "compare | sweep")
app.add_typer(cmd_import.app, name="import",
              help="PDF ingestion: pdf | status")
app.add_typer(cmd_profile.app, name="profile",
              help="show | validate | new | path")
app.add_typer(cmd_data.app, name="data",
              help="list | validate | show | verify")
app.add_typer(cmd_config.app, name="config", help="show | path")


def main() -> None:
    try:
        app(standalone_mode=False)
    except OuchError as e:
        typer.secho(f"✖ {e.message}", fg="red", err=True)
        if e.hint:
            typer.secho(f"  → {e.hint}", fg="yellow", err=True)
        sys.exit(e.exit_code)
    except typer.Exit as e:
        sys.exit(e.exit_code)
    except typer.Abort:
        sys.exit(1)
    except ClickUsageError as e:
        typer.secho(f"✖ {e.format_message()}", fg="red", err=True)
        sys.exit(2)
    except ClickException as e:
        typer.secho(f"✖ {e.format_message()}", fg="red", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
