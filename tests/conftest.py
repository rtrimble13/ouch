from __future__ import annotations

import pytest

from ouch.engine.pipeline import ResolvedData
from ouch.model.input import TaxInput
from ouch.taxdata import loader


def make_input(**overrides) -> TaxInput:
    """Convenience factory: single filer, no state, 2025."""
    base: dict = {
        "tax_year": 2025,
        "taxpayer": {"filing_status": "single", "state": ""},
    }
    base.update(overrides)
    return TaxInput.model_validate(base)


@pytest.fixture(scope="session")
def federal_2025():
    return loader.load_federal(2025)


@pytest.fixture(scope="session")
def data_federal_only(federal_2025):
    return ResolvedData(federal=federal_2025)


@pytest.fixture(scope="session")
def data_ny_nyc(federal_2025):
    return ResolvedData(federal=federal_2025,
                        state=loader.load_state("NY", 2025),
                        local=loader.load_local("NYC", 2025))
