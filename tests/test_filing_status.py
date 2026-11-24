"""`estimate --compare-filing-status` (issue #12)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ouch.engine import pipeline
from ouch.engine.filing_status import status_alternatives, with_status
from ouch.model.enums import FilingStatus as FS
from ouch.model.money import Money
from tests.conftest import make_input

CHILD = {"birth_date": "2018-04-01", "relationship": "child"}


def test_single_without_dependents_compares_only_single():
    opts = status_alternatives(make_input())
    assert opts.statuses == (FS.SINGLE,)
    assert {s for s, _ in opts.omitted} == {FS.HEAD_OF_HOUSEHOLD,
                                            FS.QUALIFYING_SURVIVING_SPOUSE}


def test_qualifying_child_offers_head_of_household():
    opts = status_alternatives(make_input(dependents=[CHILD]))
    assert opts.statuses == (FS.SINGLE, FS.HEAD_OF_HOUSEHOLD)


def test_child_living_away_does_not_qualify_but_parent_does():
    away = dict(CHILD, months_in_home=4)
    assert FS.HEAD_OF_HOUSEHOLD not in status_alternatives(
        make_input(dependents=[away])).statuses
    parent = {"birth_date": "1950-01-01", "relationship": "parent",
              "months_in_home": 0}
    assert FS.HEAD_OF_HOUSEHOLD in status_alternatives(
        make_input(dependents=[parent])).statuses


def test_qss_only_when_claimed():
    inp = make_input(taxpayer={"filing_status": "qualifying_surviving_spouse",
                               "state": ""}, dependents=[CHILD])
    assert status_alternatives(inp).statuses == (
        FS.SINGLE, FS.HEAD_OF_HOUSEHOLD, FS.QUALIFYING_SURVIVING_SPOUSE)


def test_married_profiles_are_refused():
    inp = make_input(taxpayer={"filing_status": "married_filing_jointly",
                               "state": ""})
    with pytest.raises(ValueError):
        status_alternatives(inp)


def test_hoh_beats_single_hand_computed(data_federal_only):
    """2025, wages 85,000, one child:
    single: taxable 70,000 → 1,192.50 + 4,386 + 22%×21,525 = 10,314 − 2,000
            CTC = 8,314
    HoH:    taxable 62,500 → 10%×17,000 + 12%×45,500 = 7,160 − 2,000 = 5,160"""
    inp = make_input(dependents=[CHILD],
                     income={"wages": {"taxpayer_w2": "85000"}})
    single = pipeline.run(with_status(inp, FS.SINGLE), data_federal_only,
                          compute_marginals=False)
    hoh = pipeline.run(with_status(inp, FS.HEAD_OF_HOUSEHOLD),
                       data_federal_only, compute_marginals=False)
    assert single.federal_total_tax.round_cent() == Money("8314.00")
    assert hoh.federal_total_tax.round_cent() == Money("5160.00")


PROFILE = """\
schema_version = 2
tax_year = 2025

[taxpayer]
filing_status = "{status}"
state = "TX"

[[dependents]]
birth_date = "2018-04-01"
relationship = "child"

[income.wages]
taxpayer_w2 = 85000
"""


def _cli(tmp_path: Path, status: str, *args: str):
    p = tmp_path / "p.toml"
    p.write_text(PROFILE.format(status=status))
    return subprocess.run([sys.executable, "-m", "ouch", "--profile", str(p),
                           *args], capture_output=True, text=True, timeout=120)


def test_cli_compare_table(tmp_path):
    r = _cli(tmp_path, "single", "estimate", "--compare-filing-status")
    assert r.returncode == 0, r.stderr
    assert "Head of household" in r.stdout and "(current)" in r.stdout
    assert "Lowest total tax: Head of household — $ 3,154 less" in r.stdout
    assert "Surviving spouse not computed" in r.stdout
    # The output is not a plain estimate (the original bug).
    plain = _cli(tmp_path, "single", "estimate")
    assert plain.stdout != r.stdout


def test_cli_compare_json(tmp_path):
    r = _cli(tmp_path, "single", "--format", "json", "estimate",
             "--compare-filing-status")
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["current_filing_status"] == "single"
    assert [c["filing_status"] for c in doc["comparison"]] == [
        "single", "head_of_household"]
    assert doc["comparison"][1]["result"]["federal_total_tax"] == "5160.00"
    assert doc["omitted"][0]["filing_status"] == "qualifying_surviving_spouse"


def test_cli_compare_married_exit_2(tmp_path):
    r = _cli(tmp_path, "married_filing_jointly", "estimate",
             "--compare-filing-status")
    assert r.returncode == 2
    assert "married_filing_separately" in r.stderr


def test_cli_compare_rejects_breakdown(tmp_path):
    r = _cli(tmp_path, "single", "estimate", "--compare-filing-status",
             "--breakdown")
    assert r.returncode == 2
