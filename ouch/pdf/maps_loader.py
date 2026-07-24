"""Load and validate the per-form mapping tables (spec §11.5)."""

from __future__ import annotations

from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ouch.errors import DataSchemaError


class FieldMap(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    box: str
    labels: list[str]
    target: str                       # may contain {owner}
    type: str = "money"
    aggregate: str = "assign"         # sum | assign
    required: bool = True
    validation: Optional[dict] = Field(default=None, alias="validate")


class FormMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form: str
    id: str
    owner_scoped: bool = False
    signatures: list[str]
    fields: list[FieldMap]


def load_maps() -> list[FormMap]:
    root = Path(str(resources.files("ouch.pdf") / "maps"))
    maps: list[FormMap] = []
    for path in sorted(root.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text())
            maps.append(FormMap.model_validate(raw))
        except (yaml.YAMLError, ValidationError) as e:
            raise DataSchemaError(f"malformed PDF mapping table {path}: {e}") from e
    return maps
