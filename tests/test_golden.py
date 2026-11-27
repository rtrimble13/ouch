"""Golden fixtures (spec §16.2): full returns with hand-computed expected
output. A fixture whose expected values were produced by ouch itself is not
a fixture — every directory must carry a SOURCE.md stating the independent
derivation basis.

Money fields must agree to the dollar (spec §19 M1 exit criterion): a filed
return reads tax below $100,000 from the Tax Table and the earned income
credit from the EIC Table, both figured at the midpoint of a $50 row and
rounded to whole dollars, while ouch computes them exactly. Other fields
(deduction_mode) must match exactly.
"""

from __future__ import annotations

import json
import tomllib
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

from ouch.config.profile import build_tax_input
from ouch.engine import pipeline
from ouch.render.json_out import result_to_dict
from ouch.taxdata import loader

GOLDEN_DIR = Path(__file__).parent / "golden"
FIXTURES = sorted(p for p in GOLDEN_DIR.iterdir() if p.is_dir())
TOLERANCE = Decimal(1)


def _agrees(actual, expected) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            _agrees(actual.get(k), v) for k, v in expected.items())
    try:
        return abs(Decimal(actual) - Decimal(expected)) < TOLERANCE
    except (InvalidOperation, TypeError):
        return actual == expected


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.name)
def test_golden_fixture(fixture: Path):
    assert (fixture / "SOURCE.md").is_file(), \
        f"{fixture.name}: golden fixtures must document their derivation basis"
    raw = tomllib.loads((fixture / "profile.toml").read_text())
    expected = json.loads((fixture / "expected.json").read_text())

    inp = build_tax_input(raw, raw["tax_year"])
    state = (loader.load_state(inp.taxpayer.state, inp.tax_year)
             if inp.taxpayer.state else None)
    local = (loader.load_local(inp.taxpayer.locality, inp.tax_year)
             if inp.taxpayer.locality else None)
    data = pipeline.ResolvedData(federal=loader.load_federal(inp.tax_year),
                                 state=state, local=local)
    result = pipeline.run(inp, data, compute_marginals=False)
    actual = result_to_dict(result)

    mismatches = {
        key: (actual.get(key), value)
        for key, value in expected.items()
        if not _agrees(actual.get(key), value)
    }
    assert not mismatches, mismatches
