"""Every shipped tax data file must pass schema validation (spec §16.1)."""

import pytest

from ouch.errors import JurisdictionError, MissingYearError
from ouch.taxdata import loader


def test_all_shipped_files_validate():
    results = loader.validate_all()
    assert results, "no data files discovered"
    failures = [(name, err) for name, err in results if err]
    assert not failures, failures


def test_missing_year_is_hard_error():
    with pytest.raises(MissingYearError):
        loader.load_federal(1999)


def test_unsupported_state_is_specific_error():
    with pytest.raises(JurisdictionError) as e:
        loader.load_state("ZZ", 2025)
    assert "ZZ" in str(e.value)


def test_federal_files_have_all_statuses(federal_2025):
    from ouch.model.enums import FilingStatus
    for status in FilingStatus:
        assert status in federal_2025.ordinary_brackets
        assert status in federal_2025.preferential_brackets
        assert federal_2025.ordinary_brackets[status][-1].up_to is None


def test_unverified_flag_surfaces(federal_2025):
    assert federal_2025.meta.verified is False  # placeholder data must say so
