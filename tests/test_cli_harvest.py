"""CLI end-to-end for `ouch harvest`, XDG-isolated."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROFILE = """\
schema_version = 2
tax_year = 2025

[taxpayer]
filing_status = "single"
state = "TX"

[income.wages]
taxpayer_w2 = 100000

[income.investment]
short_term_gains = 10000
"""

LOTS = """\
account,symbol,lot_id,quantity,acquired_date,cost_basis,current_price,as_of,asset_class,is_ira
Brokerage,ARKG,L-1,100,2025-05-12,20000,150.00,2025-12-12,equity,false
Brokerage,ARKG,L-2,5,2025-11-28,760,150.00,2025-12-12,equity,false
IRA,IEFA,L-3,20,2025-03-01,3000,140.00,2025-12-12,equity,true
"""


@pytest.fixture()
def home(tmp_path: Path) -> dict:
    config = tmp_path / "config"
    profiles = config / "ouch" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "default.toml").write_text(PROFILE)
    env = dict(os.environ)
    env.update({"XDG_CONFIG_HOME": str(config),
                "XDG_DATA_HOME": str(tmp_path / "data"),
                "XDG_CACHE_HOME": str(tmp_path / "cache")})
    return env


def run_cli(env, *args):
    return subprocess.run([sys.executable, "-m", "ouch", *args],
                          capture_output=True, text=True, timeout=180, env=env)


def test_harvest_import_scan_simulate(home, tmp_path):
    lots_file = tmp_path / "lots.csv"
    lots_file.write_text(LOTS)

    r = run_cli(home, "harvest", "import", str(lots_file))
    assert r.returncode == 0, r.stderr
    assert "3 lots imported" in r.stdout
    assert "1 IRA lot(s)" in r.stdout

    r = run_cli(home, "harvest", "scan", "--as-of", "2025-12-12")
    assert r.returncode == 0, r.stderr
    assert "L-1" in r.stdout                       # −5,000 ST loss candidate
    assert "repurchased" in r.stdout               # L-2 DRIP conflict
    assert "excluded" in r.stdout                  # the IRA lot

    r = run_cli(home, "harvest", "simulate", "--sell", "L-1",
                "--as-of", "2025-12-12")
    assert r.returncode == 0, r.stderr
    assert "Deferred cost" in r.stdout
    assert "Do not repurchase" in r.stdout

    r = run_cli(home, "harvest", "washsale-check", "--as-of", "2025-12-12")
    assert r.returncode == 0, r.stderr
    assert "L-1" in r.stdout


def test_harvest_scan_without_portfolio(home):
    r = run_cli(home, "harvest", "scan")
    assert r.returncode == 4
    assert "no portfolio" in r.stderr


def test_harvest_import_invalid_csv_exit_4(home, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("account,symbol\nB,VTI\n")
    r = run_cli(home, "harvest", "import", str(bad))
    assert r.returncode == 4
    assert "missing columns" in r.stderr
