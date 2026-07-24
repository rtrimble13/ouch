"""Error taxonomy and exit codes (spec §8.4, §15.2)."""

from __future__ import annotations


class OuchError(Exception):
    """Base for all ouch errors. `exit_code` maps to the CLI contract."""

    exit_code: int = 1

    def __init__(self, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class ConfigError(OuchError):
    exit_code = 3


class ProfileError(OuchError):
    exit_code = 3


class SchemaError(ProfileError):
    pass


class ConsistencyError(ProfileError):
    pass


class ValidationInputError(OuchError):
    """Validation error in input data (exit 4)."""

    exit_code = 4


class TaxDataError(OuchError):
    exit_code = 5


class MissingYearError(TaxDataError):
    pass


class DataSchemaError(TaxDataError):
    pass


class UnverifiedDataError(TaxDataError):
    pass


class JurisdictionError(OuchError):
    exit_code = 7


class PDFError(OuchError):
    exit_code = 6


class ComputationError(OuchError):
    exit_code = 9


class ConvergenceError(ComputationError):
    pass


class InvariantError(ComputationError):
    pass


class AgentError(OuchError):
    exit_code = 8


class UsageError(OuchError):
    exit_code = 2
