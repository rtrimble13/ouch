"""CLI end-to-end for M2: scenario and import commands, XDG-isolated."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("reportlab")

PROFILE = """\
schema_version = 2
tax_year = 2025

[taxpayer]
filing_status = "single"
state = "TX"

[income.wages]
taxpayer_w2 = 100000

[payments.withholding]
federal_ytd = 15000
"""


@pytest.fixture()
def home(tmp_path: Path) -> dict:
    """Isolated XDG environment with a default profile installed."""
    config = tmp_path / "config"
    data = tmp_path / "data"
    profiles = config / "ouch" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "default.toml").write_text(PROFILE)
    env = dict(os.environ)
    env.update({"XDG_CONFIG_HOME": str(config), "XDG_DATA_HOME": str(data),
                "XDG_CACHE_HOME": str(tmp_path / "cache")})
    return env


def run_cli(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "ouch", *args],
                          capture_output=True, text=True, timeout=180, env=env)


def _make_pdf(path: Path, lines: list[str]) -> Path:
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path))
    y = 780
    for line in lines:
        c.drawString(60, y, line)
        y -= 22
    c.save()
    return path


def test_scenario_new_run_compare(home):
    r = run_cli(home, "scenario", "new", "roth",
                "--set", "income.retirement.roth_conversion=20000")
    assert r.returncode == 0, r.stderr
    r = run_cli(home, "scenario", "list")
    assert "roth" in r.stdout
    r = run_cli(home, "scenario", "compare", "baseline", "roth")
    assert r.returncode == 0, r.stderr
    assert "Marginal cost of the change" in r.stdout
    assert "TOTAL TAX" in r.stdout


def test_scenario_duplicate_refused(home):
    assert run_cli(home, "scenario", "new", "x", "--set", "adjustments.hsa=1000"
                   ).returncode == 0
    r = run_cli(home, "scenario", "new", "x", "--set", "adjustments.hsa=2000")
    assert r.returncode == 2
    assert "already exists" in r.stderr


def test_scenario_template(home):
    r = run_cli(home, "scenario", "new", "myroth", "--template",
                "roth-conversion")
    assert r.returncode == 0, r.stderr
    r = run_cli(home, "scenario", "show", "myroth")
    assert "roth_conversion" in r.stdout


def test_scenario_assertion_failure_exit_9(home):
    (Path(home["XDG_CONFIG_HOME"]) / "ouch" / "scenarios").mkdir(
        parents=True, exist_ok=True)
    (Path(home["XDG_CONFIG_HOME"]) / "ouch" / "scenarios" / "big.toml").write_text(
        'name = "big"\nbase = "default"\n\n[patch]\n'
        '"income.retirement.roth_conversion" = 900000\n\n[assert]\n'
        '"result.marginal_rate_federal" = {lt = 0.30}\n')
    r = run_cli(home, "scenario", "run", "big")
    assert r.returncode == 9
    assert "assert" in r.stdout or "assert" in r.stderr


def test_sweep_csv(home):
    r = run_cli(home, "--format", "csv", "scenario", "sweep",
                "--var", "income.wages.taxpayer_w2",
                "--range", "100000:120000:10000",
                "--metric", "total_tax_all_jurisdictions")
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0].startswith("income.wages.taxpayer_w2,total_tax")
    assert len(lines) == 4  # header + 3 points


def test_import_pdf_end_to_end(home, tmp_path):
    pdf = _make_pdf(tmp_path / "w2.pdf", [
        "Form W-2 Wage and Tax Statement", "OMB No. 1545-0008",
        "1 Wages, tips, other compensation 142,000.00",
        "2 Federal income tax withheld 21,400.00",
        "3 Social security wages 142,000.00"])
    r = run_cli(home, "import", "pdf", "--yes", "--owner", "taxpayer", str(pdf))
    assert r.returncode == 0, r.stderr
    assert "Provenance recorded" in r.stdout
    # The profile now carries the imported wages:
    profile = (Path(home["XDG_CONFIG_HOME"]) / "ouch" / "profiles"
               / "default.toml").read_text()
    assert "142000" in profile
    # And the estimate reflects them:
    r = run_cli(home, "--format", "json", "estimate")
    doc = json.loads(r.stdout)
    assert doc["result"]["total_income"] == "142000.00"
    # Status checklist shows the W-2 and flags the missing prior-year 1040:
    r = run_cli(home, "import", "status")
    assert "✔ W-2" in r.stdout
    assert "1040 (prior year)" in r.stdout and "not imported" in r.stdout


def test_import_dry_run_writes_nothing(home, tmp_path):
    pdf = _make_pdf(tmp_path / "w2.pdf", [
        "Form W-2 Wage and Tax Statement", "OMB No. 1545-0008",
        "1 Wages, tips, other compensation 142,000.00",
        "2 Federal income tax withheld 21,400.00",
        "3 Social security wages 142,000.00"])
    before = (Path(home["XDG_CONFIG_HOME"]) / "ouch" / "profiles"
              / "default.toml").read_text()
    r = run_cli(home, "--dry-run", "import", "pdf", "--yes",
                "--owner", "taxpayer", str(pdf))
    assert r.returncode == 0, r.stderr
    after = (Path(home["XDG_CONFIG_HOME"]) / "ouch" / "profiles"
             / "default.toml").read_text()
    assert before == after


def test_import_unrecognized_form(home, tmp_path):
    pdf = _make_pdf(tmp_path / "junk.pdf", ["A grocery list", "milk"])
    r = run_cli(home, "import", "pdf", "--yes", str(pdf))
    assert "not a recognized tax form" in r.stdout


CO_PROFILE = """\
schema_version = 2
tax_year = 2025

[taxpayer]
filing_status = "married_filing_jointly"
state = "CO"

[income.wages]
taxpayer_w2 = 310000
"""


def test_relocate_state_template_reports_real_difference(home):
    """Issue #6 reproduction: CO → TX via the template must show Colorado's
    whole income tax as the Δ, matching `estimate --state TX`."""
    profiles = Path(home["XDG_CONFIG_HOME"]) / "ouch" / "profiles"
    (profiles / "default.toml").write_text(CO_PROFILE)
    assert run_cli(home, "scenario", "new", "tx-move",
                   "--template", "relocate-state").returncode == 0

    def total(*args):
        r = run_cli(home, "--format", "json", "estimate", *args)
        assert r.returncode == 0, r.stderr
        return Decimal(json.loads(r.stdout)["result"]
                       ["total_tax_all_jurisdictions"])

    expected = total("--state", "TX") - total()
    assert expected < 0
    r = run_cli(home, "scenario", "compare", "baseline", "tx-move")
    assert r.returncode == 0, r.stderr
    delta_line = next(l for l in r.stdout.splitlines() if "Δ tax" in l)
    shown_delta = -Decimal(re.search(r"\(([\d,]+)\)", delta_line)
                           .group(1).replace(",", ""))
    assert abs(shown_delta - expected) <= 1, delta_line

    shown = run_cli(home, "scenario", "show", "tx-move")
    assert "cost of living are outside ouch's scope)" in shown.stdout


def test_import_output_requires_yes(home, tmp_path):
    """Issue #13: non-interactive import is captured by --output; the
    interactive review refuses it rather than prompting blind."""
    pdf = _make_pdf(tmp_path / "w2.pdf", [
        "Form W-2 Wage and Tax Statement", "OMB No. 1545-0008",
        "1 Wages, tips, other compensation 142,000.00",
        "2 Federal income tax withheld 21,400.00",
        "3 Social security wages 142,000.00"])
    out = tmp_path / "import.log"
    r = run_cli(home, "--output", str(out), "import", "pdf", str(pdf))
    assert r.returncode == 2 and "--yes" in r.stderr
    assert not out.exists()
    r = run_cli(home, "--output", str(out), "import", "pdf", "--yes",
                "--owner", "taxpayer", str(pdf))
    assert r.returncode == 0, r.stderr
    assert "Provenance recorded" in out.read_text()


TAGGED = """\
name = "tagged"
base = "default"
description = "bunch charitable [2 years]"
tags = ["retirement", "timing"]

[patch]
"adjustments.hsa" = 1000
"""


def test_scenario_tags_and_bracketed_descriptions_render(home):
    """Issue #14: Rich must not swallow '[retirement, timing]' or a
    bracketed description as console markup."""
    d = Path(home["XDG_CONFIG_HOME"]) / "ouch" / "scenarios"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tagged.toml").write_text(TAGGED)

    r = run_cli(home, "scenario", "list")
    assert r.returncode == 0, r.stderr
    assert "bunch charitable [2 years]  [retirement, timing]" in r.stdout

    r = run_cli(home, "scenario", "show", "tagged")
    assert r.returncode == 0, r.stderr
    assert "bunch charitable [2 years]" in r.stdout
    assert "tags: retirement, timing" in r.stdout
