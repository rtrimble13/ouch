"""Shared CLI runtime: option state, profile→TaxInput assembly, data loading.

This is the impure shell (P3): dates, files, and terminals live here, never
in the engine.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console

from ouch.config import profile as profile_mod
from ouch.config.settings import Settings, load_settings, resolve_tax_year
from ouch.engine.pipeline import ResolvedData
from ouch.errors import JurisdictionError
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

    def console(self) -> Console:
        return Console(no_color=self.no_color or
                       self.settings.get("general.color") == "never")


def build_runtime(profile: Optional[str], year: Optional[int],
                  config: Optional[Path], fmt: Optional[str],
                  verbose: int, quiet: bool, no_color: bool,
                  dry_run: bool, explain: bool) -> Runtime:
    settings = load_settings(config)
    tax_year = resolve_tax_year(settings, year, _dt.date.today().year)
    name = profile or str(settings.get("general.default_profile", "default"))
    output_format = fmt or str(settings.get("output.format", "table"))
    verbosity = 0 if quiet else max(int(settings.get("output.verbosity", 1) or 1),
                                    1 + verbose - 1 if verbose else 1)
    return Runtime(settings=settings, profile_name=name, tax_year=tax_year,
                   output_format=output_format, verbosity=verbosity,
                   no_color=no_color, dry_run=dry_run, explain=explain,
                   year_explicit=year is not None)


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


def load_data(inp: TaxInput, *, federal_only: bool = False) -> ResolvedData:
    fed = loader.load_federal(inp.tax_year)
    state = None
    local = None
    former = None
    if not federal_only and inp.taxpayer.state:
        state = loader.load_state(inp.taxpayer.state, inp.tax_year)
        if inp.taxpayer.locality:
            local = loader.load_local(inp.taxpayer.locality, inp.tax_year)
    if (not federal_only and inp.taxpayer.former_state
            and inp.taxpayer.residency_months < 12):
        former = loader.load_state(inp.taxpayer.former_state, inp.tax_year)
    return ResolvedData(federal=fed, state=state, local=local,
                        former_state=former)
