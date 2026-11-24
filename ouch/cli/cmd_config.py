"""`ouch config` — show | path (spec §5.1)."""

from __future__ import annotations

import typer

from ouch.cli.common import Runtime
from ouch.config.settings import default_config_path

app = typer.Typer(no_args_is_help=True)


@app.command("show")
def show(ctx: typer.Context,
         origin: bool = typer.Option(False, "--origin",
                                     help="Show where each value came from")) -> None:
    """Print every resolved setting (optionally with its origin)."""
    rt: Runtime = ctx.obj
    console = rt.console()
    for key in sorted(rt.settings.values):
        value = rt.settings.values[key]
        line = f"{key} = {value!r}"
        if origin:
            line += f"    [dim]({rt.settings.origins[key]})[/dim]"
        console.print(line)


@app.command("path")
def path_cmd(ctx: typer.Context) -> None:
    """Print the config file path."""
    ctx.obj.echo(str(default_config_path()))
