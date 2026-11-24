"""CLI end-to-end: command invocation, exit codes, output formats (§16.1)."""

from __future__ import annotations

import json
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

[payments.withholding]
federal_ytd = 15000
"""

BAD_PROFILE = """\
schema_version = 2
tax_year = 2025

[taxpayer]
filing_status = "married"

[income.investment]
ordinary_dividends = 1000
qualified_dividends = 2000
"""


@pytest.fixture()
def profile_path(tmp_path: Path) -> Path:
    p = tmp_path / "test-profile.toml"
    p.write_text(PROFILE)
    return p


def run_cli(*args: str, profile: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "ouch"]
    if profile is not None:
        cmd += ["--profile", str(profile)]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def test_version():
    r = run_cli("--version")
    assert r.returncode == 0
    assert "ouch 0." in r.stdout


def test_estimate_table(profile_path):
    r = run_cli("estimate", profile=profile_path)
    assert r.returncode == 0
    assert "TOTAL TAX BURDEN" in r.stdout
    assert "Estimates only" in r.stdout  # disclaimer is not suppressible


def test_estimate_json_schema(profile_path):
    r = run_cli("--format", "json", "estimate", profile=profile_path)
    assert r.returncode == 0
    doc = json.loads(r.stdout)
    assert doc["schema_version"] == 1
    assert doc["result"]["taxable_income"] == "85000.00"
    assert doc["result"]["federal_total_tax"] == "13614.00"
    assert doc["disclaimer"].startswith("Estimates only")
    assert any(item["id"] == "fed.tax.total" for item in doc["trace"])


def test_estimate_set_override(profile_path):
    r = run_cli("--format", "json", "estimate", "--set",
                "income.wages.taxpayer_w2=200000", profile=profile_path)
    doc = json.loads(r.stdout)
    assert doc["result"]["taxable_income"] == "185000.00"


def test_explain(profile_path):
    r = run_cli("explain", "fed.agi", profile=profile_path)
    assert r.returncode == 0
    assert "fed.agi" in r.stdout


def test_explain_unknown_line_exit_2(profile_path):
    r = run_cli("explain", "no.such.line", profile=profile_path)
    assert r.returncode == 2


def test_missing_profile_exit_3(tmp_path):
    r = run_cli("estimate", profile=tmp_path / "nope.toml")
    assert r.returncode == 3
    assert "profile not found" in r.stderr


def test_invalid_profile_collected_errors_exit_3(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text(BAD_PROFILE)
    r = run_cli("estimate", profile=p)
    assert r.returncode == 3
    # Errors are collected and reported together (spec §15.2)
    assert "filing status" in r.stderr or "filing_status" in r.stderr
    assert "qualified dividends" in r.stderr


def test_unsupported_state_exit_7(tmp_path):
    p = tmp_path / "zz.toml"
    p.write_text(PROFILE.replace('state = "TX"', 'state = "ZZ"'))
    r = run_cli("estimate", profile=p)
    assert r.returncode == 7


def test_missing_year_exit_5(profile_path):
    r = run_cli("--year", "2001", "estimate", profile=profile_path)
    assert r.returncode == 5


def test_withhold_check(profile_path):
    r = run_cli("withhold", "check", profile=profile_path)
    assert r.returncode == 0
    assert "Safe harbor analysis" in r.stdout


def test_withhold_solve(profile_path):
    r = run_cli("withhold", "solve", "--target", "zero",
                "--periods-remaining", "5", profile=profile_path)
    assert r.returncode == 0
    assert "Federal withholding per period" in r.stdout


def test_data_validate():
    r = run_cli("data", "validate")
    assert r.returncode == 0
    assert "valid" in r.stdout


def test_data_list():
    r = run_cli("data", "list")
    assert r.returncode == 0
    assert "federal" in r.stdout


def test_profile_validate(profile_path):
    r = run_cli("profile", "validate", profile=profile_path)
    assert r.returncode == 0


def _suggested_commands(text: str) -> list[list[str]]:
    import re
    return [" ".join(m.split()).split()[1:]          # drop the leading "ouch"
            for m in re.findall(r"`(ouch [^`]+)`", text, re.S)]


def test_estimate_footer_suggestion_parses(profile_path):
    """Issue #9: the footer under every estimate must suggest a command
    that actually runs (global options precede the subcommand)."""
    r = run_cli("estimate", profile=profile_path)
    suggestions = _suggested_commands(r.stdout)
    assert suggestions, r.stdout
    for args in suggestions:
        follow = run_cli(*args, profile=profile_path)
        assert follow.returncode == 0, (args, follow.stderr)


def test_guardrail_suggestions_parse(profile_path):
    from decimal import Decimal
    from ouch.agent import guardrails
    _, warnings = guardrails.annotate("Your tax is $12,345.", {Decimal(1)})
    text = guardrails.REFUSAL_TEXT + " " + " ".join(warnings)
    suggestions = _suggested_commands(text)
    assert len(suggestions) == 2
    for args in suggestions:
        follow = run_cli(*args, profile=profile_path)
        assert follow.returncode == 0, (args, follow.stderr)


WALK_PROFILE = """\
schema_version = 2
tax_year = 2025

[taxpayer]
filing_status = "married_filing_jointly"
state = "NY"
locality = "NYC"

[income.wages]
taxpayer_w2 = 185000
spouse_w2 = 96000

[payments.withholding]
federal_ytd = 34800
state_ytd = 11500
local_ytd = 4200
federal_per_period = 1450
state_per_period = 500
local_per_period = 200
periods_remaining = 11

[payments.estimated]
q1_federal = 1000
"""


def test_withhold_check_walk_adds_up(tmp_path):
    """Issue #10: withheld-to-date + projected withholding (+ estimates)
    must equal projected total payments: 50,500 + 11 × 2,150 + 1,000."""
    import re
    p = tmp_path / "walk.toml"
    p.write_text(WALK_PROFILE)
    r = run_cli("withhold", "check", profile=p)
    assert r.returncode == 0, r.stderr

    def amount(label: str) -> int:
        line = next(l for l in r.stdout.splitlines() if l.startswith(label))
        return int(re.search(r"\$ ([\d,]+)", line).group(1).replace(",", ""))

    ytd = amount("Withheld to date")
    additional = amount("Projected additional withholding")
    estimated = amount("Estimated payments")
    total = amount("Projected total payments")
    assert (ytd, additional, estimated) == (50_500, 23_650, 1_000)
    assert ytd + additional + estimated == total
    assert "(11 periods × $ 2,150)" in r.stdout
    assert "per period: federal $ 1,450 · state $ 500 · local $ 200" in r.stdout


# --- issue #13: --output is honoured by every command and format ------------


@pytest.mark.parametrize("args, expect", [
    (("estimate",), "TOTAL TAX BURDEN"),
    (("--format", "json", "estimate"), '"total_tax_all_jurisdictions"'),
    (("--format", "markdown", "estimate"), "TOTAL TAX BURDEN"),
    (("withhold", "check"), "Projected total payments"),
    (("profile", "show"), '"filing_status": "single"'),
    (("--explain", "estimate"), "fed.tax.total"),
])
def test_output_captures_command_output(profile_path, tmp_path, args, expect):
    out = tmp_path / "out.txt"
    r = run_cli("--output", str(out), *args, profile=profile_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == ""
    assert expect in out.read_text()


def test_output_captures_sweep_csv(tmp_path):
    import os
    profiles = tmp_path / "cfg" / "ouch" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "default.toml").write_text(PROFILE)
    env = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path / "cfg"),
               XDG_DATA_HOME=str(tmp_path / "data"))
    out = tmp_path / "sweep.csv"
    r = subprocess.run(
        [sys.executable, "-m", "ouch", "--format", "csv", "--output", str(out),
         "scenario", "sweep", "--var", "adjustments.hsa",
         "--range", "0:2000:1000"],
        capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 0, r.stderr
    lines = out.read_text().splitlines()
    assert lines[0].startswith("adjustments.hsa,total_tax") and len(lines) == 4


def test_output_not_written_when_command_fails(tmp_path):
    out = tmp_path / "out.txt"
    r = run_cli("--output", str(out), "estimate",
                profile=tmp_path / "missing.toml")
    assert r.returncode == 3
    assert not out.exists()


def test_output_missing_directory_exit_2(profile_path, tmp_path):
    r = run_cli("--output", str(tmp_path / "nope" / "x.txt"), "estimate",
                profile=profile_path)
    assert r.returncode == 2 and "does not exist" in r.stderr


def test_output_conflicts_with_dry_run(profile_path, tmp_path):
    r = run_cli("--output", str(tmp_path / "x"), "--dry-run", "estimate",
                profile=profile_path)
    assert r.returncode == 2 and "--dry-run" in r.stderr


def test_output_refused_for_interactive_init(profile_path, tmp_path):
    r = run_cli("--output", str(tmp_path / "x"), "init", profile=profile_path)
    assert r.returncode == 2 and "interactive" in r.stderr
