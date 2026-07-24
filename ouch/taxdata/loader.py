"""Tax data discovery, schema validation, year resolution (spec §6).

Search order: $OUCH_TAXDATA / configured path → XDG data dir → files packaged
with ouch. First hit wins, so a user-supplied file overrides the shipped one.
YAML numbers are parsed and re-fed to pydantic as strings so every figure
becomes an exact Decimal (floats never reach the engine).
"""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

import yaml
from platformdirs import user_data_dir
from pydantic import ValidationError

from ouch.errors import DataSchemaError, JurisdictionError, MissingYearError
from ouch.taxdata.schema import FederalData, LocalData, StateData


def _stringify_numbers(node):
    """Convert YAML floats/ints to str so pydantic builds exact Decimals."""
    if isinstance(node, dict):
        return {k: _stringify_numbers(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_stringify_numbers(v) for v in node]
    if isinstance(node, bool):
        return node
    if isinstance(node, float):
        return repr(node)  # repr gives the shortest exact representation
    return node


def _packaged_root() -> Path:
    return Path(str(resources.files("ouch.taxdata") / "data"))


def search_paths() -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get("OUCH_TAXDATA")
    if env:
        paths.append(Path(env).expanduser())
    paths.append(Path(user_data_dir("ouch")) / "taxdata")
    paths.append(_packaged_root())
    return paths


def _find(relative: str) -> Path | None:
    for root in search_paths():
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def _load_yaml(path: Path) -> dict:
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise DataSchemaError(f"malformed YAML in {path}: {e}") from e
    if not isinstance(raw, dict):
        raise DataSchemaError(f"tax data file {path} is not a mapping")
    return _stringify_numbers(raw)


def _fmt_validation_error(path: Path, e: ValidationError) -> str:
    lines = [f"tax data file failed schema validation: {path}"]
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"])
        lines.append(f"  {loc}: {err['msg']}")
    return "\n".join(lines)


def load_federal(year: int) -> FederalData:
    rel = f"federal/{year}.yaml"
    path = _find(rel)
    if path is None:
        raise MissingYearError(
            f"no federal tax data for {year}",
            hint=f"expected {rel} under one of: "
                 + ", ".join(str(p) for p in search_paths()),
        )
    try:
        return FederalData.model_validate(_load_yaml(path))
    except ValidationError as e:
        raise DataSchemaError(_fmt_validation_error(path, e)) from e


def load_state(code: str, year: int) -> StateData:
    code = code.upper()
    path = _find(f"state/{code}-{year}.yaml")
    if path is None:
        available = sorted({p.stem.rsplit("-", 1)[0]
                            for p in _glob_all("state/*.yaml")})
        raise JurisdictionError(
            f"no tax data for state '{code}' in {year}",
            hint="available states: " + (", ".join(available) or "none")
                 + f" — contribute a data file (see spec appendix D)",
        )
    try:
        data = StateData.model_validate(_load_yaml(path))
        data.validate_regime()
        return data
    except ValidationError as e:
        raise DataSchemaError(_fmt_validation_error(path, e)) from e
    except ValueError as e:
        raise DataSchemaError(f"{path}: {e}") from e


def load_local(name: str, year: int) -> LocalData:
    name = name.upper()
    path = _find(f"local/{name}-{year}.yaml")
    if path is None:
        available = sorted({p.stem.rsplit("-", 1)[0]
                            for p in _glob_all("local/*.yaml")})
        raise JurisdictionError(
            f"no tax data for locality '{name}' in {year}",
            hint="available localities: " + (", ".join(available) or "none"),
        )
    try:
        data = LocalData.model_validate(_load_yaml(path))
        data.validate_regime()
        return data
    except ValidationError as e:
        raise DataSchemaError(_fmt_validation_error(path, e)) from e
    except ValueError as e:
        raise DataSchemaError(f"{path}: {e}") from e


def _glob_all(pattern: str) -> list[Path]:
    seen: dict[str, Path] = {}
    for root in search_paths():
        if root.is_dir():
            for p in sorted(root.glob(pattern)):
                seen.setdefault(p.name, p)
    return list(seen.values())


def list_available() -> dict[str, list[str]]:
    """jurisdictions × years available, e.g. {'federal': ['2025', '2026'], ...}"""
    out: dict[str, list[str]] = {"federal": [], "state": [], "local": []}
    for p in _glob_all("federal/*.yaml"):
        out["federal"].append(p.stem)
    for p in _glob_all("state/*.yaml"):
        out["state"].append(p.stem)
    for p in _glob_all("local/*.yaml"):
        out["local"].append(p.stem)
    for v in out.values():
        v.sort()
    return out


def validate_all() -> list[tuple[str, str | None]]:
    """Schema-check every discoverable file. Returns [(file, error-or-None)]."""
    results: list[tuple[str, str | None]] = []
    for kind, model in (("federal", FederalData), ("state", StateData),
                        ("local", LocalData)):
        for path in _glob_all(f"{kind}/*.yaml"):
            try:
                data = model.model_validate(_load_yaml(path))
                if hasattr(data, "validate_regime"):
                    data.validate_regime()
                results.append((f"{kind}/{path.name}", None))
            except (ValidationError, ValueError, DataSchemaError) as e:
                results.append((f"{kind}/{path.name}", str(e)))
    return results


def raw_file(kind: str, name: str, year: int) -> dict:
    """Raw parsed YAML for `data show` / `data diff`."""
    rel = f"{kind}/{name}-{year}.yaml" if kind != "federal" else f"federal/{year}.yaml"
    path = _find(rel)
    if path is None:
        raise MissingYearError(f"no data file {rel}")
    return _load_yaml(path)
