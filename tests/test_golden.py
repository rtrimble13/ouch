"""Golden fixtures (spec §16.2): full returns with hand-computed expected
output, to the cent. A fixture whose expected values were produced by ouch
itself is not a fixture — every directory must carry a SOURCE.md stating the
independent derivation basis.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from ouch.config.profile import build_tax_input
from ouch.engine import pipeline
from ouch.render.json_out import result_to_dict
from ouch.taxdata import loader

GOLDEN_DIR = Path(__file__).parent / "golden"
FIXTURES = sorted(p for p in GOLDEN_DIR.iterdir() if p.is_dir())


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
        if actual.get(key) != value
    }
    assert not mismatches, mismatches
