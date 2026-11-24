"""Shared CLI runtime: option state, profile→TaxInput assembly, data loading.

This is the impure shell (P3): dates, files, and terminals live here, never
in the engine.
"""

from __future__ import annotations

import datetime as _dt
import io
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, TextIO

from rich.console import Console

from ouch.config import profile as profile_mod
from ouch.config.settings import Settings, load_settings, resolve_tax_year
from ouch.engine.pipeline import ResolvedData
from ouch.errors import ConfigError, UsageError
from ouch.model.input import TaxInput
from ouch.taxdata import loader


@dataclass
class Runtime:
    settings: Settings
    profile_name: str
    tax_year: int
    output_format: str
    verbosity: int
    no_color: bool
    dry_run: bool
    explain: bool
    year_explicit: bool = False
    overrides: list[str] = field(default_factory=list)
    output_path: Optional[Path] = None   # global --output
    no_ai: bool = False
    _buffer: Optional[io.StringIO] = field(default=None, repr=False)

    # --- output sink (global --output) -------------------------------------
    # Every command writes through `out` — via `console()` or `echo()` — so
    # `--output` captures whatever the command would have printed. Output is
    # buffered and written only when the command succeeds (`flush_output`),
    # so a failed run never leaves a partial file behind.

    @property
    def out(self) -> TextIO:
        if self.output_path is None:
            return sys.stdout
        if self._buffer is None:
            self._buffer = io.StringIO()
        return self._buffer

    def _no_color(self) -> bool:
        return self.no_color or self.settings.get("general.color") == "never"

    def console(self) -> Console:
        return Console(file=self.out, no_color=self._no_color())

    def terminal_console(self) -> Console:
        """Always the terminal, even under --output: for text a prompt
        depends on, which the user must see before answering."""
        return Console(no_color=self._no_color())

    def echo(self, text: str) -> None:
        """Plain (non-Rich) output — JSON, CSV, file contents, paths."""
        print(text, file=self.out)

    def require_terminal(self, what: str, hint: str | None = None) -> None:
        """Refuse --output for an interactive command, whose prompts need
        their context on the terminal rather than in a file."""
        if self.output_path is not None:
            raise UsageError(f"--output is not supported for {what}",
                             hint=hint or "run it without --output")

    def flush_output(self) -> None:
        if self.output_path is not None:
            self.output_path.write_text(
                self._buffer.getvalue() if self._buffer else "")


def build_runtime(profile: Optional[str], year: Optional[int],
                  config: Optional[Path], fmt: Optional[str],
                  verbose: int, quiet: bool, no_color: bool,
                  dry_run: bool, explain: bool, *,
                  output: Optional[Path] = None,
                  no_ai: bool = False) -> Runtime:
    if output is not None:
        if dry_run:
            raise UsageError("--output and --dry-run conflict",
                             hint="--dry-run writes nothing to disk; drop one")
        if not output.expanduser().parent.is_dir():
            raise UsageError(
                f"--output directory does not exist: "
                f"{output.expanduser().parent}")
    settings = load_settings(config)
    _configure_taxdata(settings)
    tax_year = resolve_tax_year(settings, year, _dt.date.today().year)
    name = profile or str(settings.get("general.default_profile", "default"))
    output_format = fmt or str(settings.get("output.format", "table"))
    verbosity = 0 if quiet else max(int(settings.get("output.verbosity", 1) or 1),
                                    1 + verbose - 1 if verbose else 1)
    return Runtime(settings=settings, profile_name=name, tax_year=tax_year,
                   output_format=output_format, verbosity=verbosity,
                   no_color=no_color, dry_run=dry_run, explain=explain,
                   year_explicit=year is not None,
                   output_path=output.expanduser() if output else None,
                   no_ai=no_ai)


def _configure_taxdata(settings: Settings) -> None:
    """Point the loader at `taxdata.path`. A configured path that is not a
    directory is an error, not a silent fallback to the shipped data — the
    user's override would otherwise be ignored without a trace."""
    value = str(settings.get("taxdata.path") or "").strip()
    if value and not Path(value).expanduser().is_dir():
        raise ConfigError(
            f"taxdata.path '{value}' is not a directory",
            hint=f"set by {settings.origins.get('taxdata.path', 'config')}; "
                 "point it at a folder containing federal/, state/, local/")
    loader.configure(value or None)


def _derive_periods_remaining(raw: dict, today: _dt.date, tax_year: int) -> None:
    """Engine defaults periods_remaining from today's date (spec §5.3) — an
    impure derivation, so it happens here in the shell."""
    payments = raw.setdefault("payments", {})
    withholding = payments.setdefault("withholding", {})
    if withholding.get("periods_remaining") not in (None, 0):
        return
    ppy = int(withholding.get("pay_periods_per_year", 24) or 24)
    if today.year > tax_year:
        withholding["periods_remaining"] = 0
        return
    if today.year < tax_year:
        withholding["periods_remaining"] = ppy
        return
    year_end = _dt.date(tax_year, 12, 31)
    days_left = max((year_end - today).days, 0)
    withholding["periods_remaining"] = round(ppy * days_left / 365)


def effective_tax_year(rt: Runtime, raw: dict) -> int:
    """The year the engine will actually compute for this profile: `--year`
    outranks the profile (§5.1); otherwise the profile's own `tax_year`,
    falling back to the resolved runtime year only when the profile omits it.
    Mirrors `profile.build_tax_input`."""
    if rt.year_explicit:
        return rt.tax_year
    value = raw.get("tax_year")
    return int(value) if value else rt.tax_year


def prepare_raw(rt: Runtime, raw: dict, *,
                today: _dt.date | None = None) -> None:
    """Shell-side normalisation every command applies before building a
    TaxInput: pin the effective tax year, then derive `periods_remaining`
    from *that* year — not the runtime default, which for a past-year
    profile would project paychecks into a year that has already closed."""
    if rt.year_explicit:
        raw["tax_year"] = rt.tax_year  # CLI flag outranks the profile (§5.1)
    _derive_periods_remaining(raw, today or _dt.date.today(),
                              effective_tax_year(rt, raw))


def load_input(rt: Runtime, *, extra_overrides: list[str] | None = None,
               state_override: str | None = None,
               locality_override: str | None = None) -> TaxInput:
    raw, _path = profile_mod.load_profile_raw(rt.profile_name)
    for override in (rt.overrides + (extra_overrides or [])):
        key, _, value = override.partition("=")
        profile_mod.apply_override(raw, key.strip(), value.strip())
    if state_override is not None:
        raw.setdefault("taxpayer", {})["state"] = state_override
    if locality_override is not None:
        raw.setdefault("taxpayer", {})["locality"] = locality_override
    prepare_raw(rt, raw)
    return profile_mod.build_tax_input(raw, rt.tax_year)


def _data_key(inp: TaxInput, federal_only: bool) -> tuple[int, str, str, str]:
    """Everything `load_data` selects files by: (year, state, locality,
    former state). Blank means that file is not loaded."""
    t = inp.taxpayer
    state = t.state.upper() if not federal_only and t.state else ""
    locality = t.locality.upper() if state and t.locality else ""
    former = (t.former_state.upper()
              if not federal_only and t.former_state and t.residency_months < 12
              else "")
    return inp.tax_year, state, locality, former


def load_data(inp: TaxInput, *, federal_only: bool = False) -> ResolvedData:
    year, state_code, locality, former_code = _data_key(inp, federal_only)
    fed = loader.load_federal(year)
    state = loader.load_state(state_code, year) if state_code else None
    local = loader.load_local(locality, year) if locality else None
    former = loader.load_state(former_code, year) if former_code else None
    return ResolvedData(federal=fed, state=state, local=local,
                        former_state=former)


def data_resolver(*, federal_only: bool = False
                  ) -> Callable[[TaxInput], ResolvedData]:
    """Resolve tax data from each input rather than once, so a scenario that
    patches the jurisdiction or year is computed with that jurisdiction's
    rates. Cached by `_data_key`, so a sweep reads each file once."""
    cache: dict[tuple[int, str, str, str], ResolvedData] = {}

    def resolve(inp: TaxInput) -> ResolvedData:
        key = _data_key(inp, federal_only)
        if key not in cache:
            cache[key] = load_data(inp, federal_only=federal_only)
        return cache[key]

    return resolve
