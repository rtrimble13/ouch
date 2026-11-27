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


class OccupationCheck(BaseModel):
    """A companion box that says whether a coded amount fully qualifies.
    W-2 box 14b lists Treasury Tipped Occupation Codes for code TP; "000"
    means some tips came from a nonqualifying occupation."""
    model_config = ConfigDict(extra="forbid")
    box: str                          # e.g. "14b"
    label: str
    nonqualifying_code: str           # e.g. "000"


class CodedFieldMap(BaseModel):
    """A value identified by a code letter inside a multi-entry box, such as
    W-2 box 12 (12a–12d each hold a code and an amount). Always optional:
    a code that isn't on the form simply isn't imported."""
    model_config = ConfigDict(extra="forbid")
    box: str                          # e.g. "12"
    slots: list[str]                  # e.g. ["a", "b", "c", "d"]
    code: str                         # e.g. "TP"
    description: str
    target: str                       # may contain {owner}
    aggregate: str = "sum"
    occupation_check: Optional[OccupationCheck] = None

    @property
    def key(self) -> str:
        """The staged field's box label, e.g. "12 TP"."""
        return f"{self.box} {self.code}"


class FormMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form: str
    id: str
    owner_scoped: bool = False
    signatures: list[str]
    fields: list[FieldMap]
    coded_fields: list[CodedFieldMap] = []


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
