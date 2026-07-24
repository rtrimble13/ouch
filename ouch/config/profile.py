"""TaxProfile load/save/merge (spec §5.3).

The profile is a hand-editable TOML file; validation errors are collected and
reported together, never one at a time (§15.2), following the pattern
what / where / why / fix.
"""

from __future__ import annotations

import datetime as _dt
import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ouch.config.settings import profiles_dir
from ouch.errors import ProfileError, SchemaError, UsageError
from ouch.model.input import TaxInput

PROFILE_SCHEMA_VERSION = 2

_HINTS = {
    "filing_status": ('did you mean "married_filing_jointly" or '
                      '"married_filing_separately"?'),
    "qualified_dividends": "box 1b of Form 1099-DIV is a subset of box 1a",
}


def resolve_profile_path(name_or_path: str) -> Path:
    p = Path(name_or_path).expanduser()
    if p.suffix == ".toml" or os.sep in name_or_path:
        return p
    return profiles_dir() / f"{name_or_path}.toml"


def load_profile_raw(name_or_path: str) -> tuple[dict[str, Any], Path]:
    path = resolve_profile_path(name_or_path)
    if not path.is_file():
        raise ProfileError(
            f"profile not found: {path}",
            hint="run `ouch init` to create one, or `ouch profile new NAME`")
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ProfileError(f"malformed profile {path}: {e}") from e
    return raw, path


def apply_override(raw: dict[str, Any], dotted: str, value: str) -> None:
    """Apply a --set PATH=VALUE override onto the raw profile dict."""
    parts = dotted.split(".")
    node = raw
    for part in parts[:-1]:
        nxt = node.get(part)
        if nxt is None:
            nxt = {}
            node[part] = nxt
        if not isinstance(nxt, dict):
            raise UsageError(f"--set path '{dotted}': '{part}' is not a table")
        node = nxt
    leaf: Any = value
    lowered = value.lower()
    if lowered in ("true", "false"):
        leaf = lowered == "true"
    else:
        try:
            leaf = int(value)
        except ValueError:
            try:
                float(value)  # detect numeric-ness only
                leaf = value  # keep as string → Decimal via pydantic
            except ValueError:
                leaf = value
    node[parts[-1]] = leaf


def build_tax_input(raw: dict[str, Any], tax_year: int) -> TaxInput:
    data = dict(raw)
    schema_version = data.pop("schema_version", PROFILE_SCHEMA_VERSION)
    if schema_version > PROFILE_SCHEMA_VERSION:
        raise SchemaError(
            f"profile schema_version {schema_version} is newer than this ouch "
            f"supports ({PROFILE_SCHEMA_VERSION})",
            hint="upgrade ouch, or run `ouch profile migrate`")
    data.setdefault("tax_year", tax_year)
    data["tax_year"] = int(data["tax_year"]) if data["tax_year"] else tax_year
    # Numbers in TOML may be int/float; stringify so pydantic yields Decimals.
    data = _stringify(data)
    try:
        return TaxInput.model_validate(data)
    except ValidationError as e:
        raise SchemaError(_format_errors(e)) from e


def _stringify(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _stringify(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_stringify(v) for v in node]
    if isinstance(node, bool):
        return node
    if isinstance(node, float):
        return repr(node)
    if isinstance(node, (_dt.date, _dt.datetime)):
        return node.isoformat()
    return node


def _format_errors(e: ValidationError) -> str:
    errors = e.errors()
    lines = [f"Profile validation failed ({len(errors)} "
             f"error{'s' if len(errors) != 1 else ''})"]
    for err in errors:
        loc = ".".join(str(x) for x in err["loc"]) or "(root)"
        lines.append(f"  [{loc}]")
        lines.append(f"    ✖ {err['msg']}")
        for key, hint in _HINTS.items():
            if key in loc or key in err["msg"]:
                lines.append(f"    → {hint}")
                break
    return "\n".join(lines)


PROFILE_TEMPLATE = f'''schema_version = {PROFILE_SCHEMA_VERSION}
tax_year       = {{year}}

[taxpayer]
name           = ""
filing_status  = "single"   # single | married_filing_jointly |
                            # married_filing_separately | head_of_household |
                            # qualifying_surviving_spouse
# birth_date   = "1990-01-01"
state          = ""
locality       = ""
residency_months = 12

[income.wages]
taxpayer_w2 = 0
spouse_w2   = 0

[income.investment]
interest            = 0
qualified_dividends = 0
ordinary_dividends  = 0
short_term_gains    = 0
long_term_gains     = 0

[payments.withholding]
federal_ytd          = 0
federal_per_period   = 0
pay_periods_per_year = 24
periods_remaining    = 0

[payments.prior_year]
agi       = 0
total_tax = 0
'''


def write_profile(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(
            path.suffix + "." + _dt.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            + ".bak")
        backup.write_text(path.read_text())
        os.chmod(backup, 0o600)
    path.write_text(content)
    os.chmod(path, 0o600)  # profiles are a financial portrait (§17.2)
    os.chmod(path.parent, 0o700)
