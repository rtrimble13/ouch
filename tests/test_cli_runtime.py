"""Shell-side runtime normalisation: effective tax year and the
periods_remaining derivation (issue #5)."""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ouch.cli.common import Runtime, effective_tax_year, prepare_raw
from ouch.config.settings import Settings


def _rt(tax_year: int, *, explicit: bool = False) -> Runtime:
    return Runtime(settings=Settings(), profile_name="t", tax_year=tax_year,
                   output_format="table", verbosity=1, no_color=True,
                   dry_run=False, explain=False, year_explicit=explicit)


def _raw(tax_year: int | None) -> dict:
    raw: dict = {"payments": {"withholding": {"pay_periods_per_year": 24}}}
    if tax_year is not None:
        raw["tax_year"] = tax_year
    return raw


def _periods(raw: dict) -> int:
    return raw["payments"]["withholding"]["periods_remaining"]


def test_effective_year_prefers_profile_over_runtime_default():
    assert effective_tax_year(_rt(2026), _raw(2025)) == 2025


def test_effective_year_cli_flag_outranks_profile():
    assert effective_tax_year(_rt(2026, explicit=True), _raw(2025)) == 2026


def test_effective_year_falls_back_when_profile_omits_it():
    assert effective_tax_year(_rt(2026), _raw(None)) == 2026


def test_past_year_profile_projects_no_periods():
    """today.year > profile year: the year has closed — 0 periods, even
    though the runtime default year (today's) is 2026."""
    raw = _raw(2025)
    prepare_raw(_rt(2026), raw, today=_dt.date(2026, 7, 1))
    assert _periods(raw) == 0


def test_future_year_profile_projects_full_year():
    raw = _raw(2027)
    prepare_raw(_rt(2026), raw, today=_dt.date(2026, 7, 1))
    assert _periods(raw) == 24


def test_current_year_profile_prorates_by_date():
    """2026-07-01 → 183 days left of 365 → round(24 × 183/365) = 12."""
    raw = _raw(2026)
    prepare_raw(_rt(2026), raw, today=_dt.date(2026, 7, 1))
    assert _periods(raw) == 12


def test_explicit_periods_remaining_is_kept():
    raw = _raw(2025)
    raw["payments"]["withholding"]["periods_remaining"] = 5
    prepare_raw(_rt(2026), raw, today=_dt.date(2026, 7, 1))
    assert _periods(raw) == 5


PAST_YEAR_PROFILE = """\
schema_version = 2
tax_year       = 2025

[taxpayer]
filing_status = "single"
state         = "TX"

[income.wages]
taxpayer_w2 = 100000

[payments.withholding]
federal_ytd          = 13000
federal_per_period   = 550
pay_periods_per_year = 24
"""


@pytest.mark.skipif(_dt.date.today().year <= 2025,
                    reason="needs the 2025 tax year to have closed")
def test_cli_past_year_profile_without_year_flag(tmp_path: Path):
    """Issue #5 reproduction: with and without --year the same past-year
    profile must project the same payments — the YTD figure only."""
    profile = tmp_path / "py2025.toml"
    profile.write_text(PAST_YEAR_PROFILE)

    def payments(*extra: str) -> str:
        r = subprocess.run(
            [sys.executable, "-m", "ouch", "--profile", str(profile),
             "--format", "json", *extra, "estimate"],
            capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)["result"]["total_payments"]

    assert payments() == payments("--year", "2025") == "13000.00"


# --- issue #7: taxdata.path in config.toml is honoured ----------------------

import os  # noqa: E402

OR_PROFILE = """\
schema_version = 2
tax_year = 2025

[taxpayer]
filing_status = "single"
state = "OR"

[income.wages]
taxpayer_w2 = 100000
"""


def _taxdata_dir(root: Path, rate: str) -> Path:
    """A user data dir holding a fictional flat-rate OR file."""
    src = Path(__file__).parent.parent / "ouch/taxdata/data/state/CO-2025.yaml"
    text = (src.read_text().replace("jurisdiction: CO", "jurisdiction: OR")
            .replace("rate: 0.044", f"rate: {rate}"))
    (root / "state").mkdir(parents=True)
    (root / "state" / "OR-2025.yaml").write_text(text)
    return root


def _run(tmp_path: Path, config_body: str | None, extra_env: dict | None = None,
         *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "OUCH_TAXDATA"}
    env.update({"XDG_CONFIG_HOME": str(tmp_path / "xdg-config"),
                "XDG_DATA_HOME": str(tmp_path / "xdg-data")})
    env.update(extra_env or {})
    profile = tmp_path / "or.toml"
    profile.write_text(OR_PROFILE)
    cmd = [sys.executable, "-m", "ouch", "--profile", str(profile)]
    if config_body is not None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(config_body)
        cmd += ["--config", str(cfg)]
    return subprocess.run(cmd + ["--format", "json", *args, "estimate"],
                          capture_output=True, text=True, timeout=120, env=env)


def _state_tax(r: subprocess.CompletedProcess) -> str:
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["result"]["state"]["tax"]


def test_config_taxdata_path_is_searched(tmp_path: Path):
    """CO's 2025 file applies its flat rate to federal taxable income
    (100,000 − 15,750 = 84,250): at 5%, OR tax = 4,212.50."""
    data = _taxdata_dir(tmp_path / "alt", "0.05")
    r = _run(tmp_path, f'[taxdata]\npath = "{data}"\n')
    assert _state_tax(r) == "4212.50"


def test_env_taxdata_outranks_config(tmp_path: Path):
    cfg_dir = _taxdata_dir(tmp_path / "from-config", "0.05")
    env_dir = _taxdata_dir(tmp_path / "from-env", "0.10")
    r = _run(tmp_path, f'[taxdata]\npath = "{cfg_dir}"\n',
             {"OUCH_TAXDATA": str(env_dir)})
    assert _state_tax(r) == "8425.00"  # 10% × 84,250


def test_missing_taxdata_path_fails_loudly(tmp_path: Path):
    r = _run(tmp_path, f'[taxdata]\npath = "{tmp_path / "nope"}"\n')
    assert r.returncode == 3
    assert "taxdata.path" in r.stderr and "not a directory" in r.stderr
