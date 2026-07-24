"""Staging, aggregation, and provenance for imported fields (spec §11.6–11.7).

Nothing is written until review completes; every imported value records its
source file, extraction method, confidence, and timestamp.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from platformdirs import user_data_dir

from ouch.errors import PDFError
from ouch.pdf.extract import ExtractedField
from ouch.pdf.maps_loader import FormMap
from ouch.scenario.model import get_path, set_path


@dataclass
class StagedField:
    source_file: str
    form: str
    box: str
    label: str
    target: str            # fully resolved (owner substituted)
    value: Decimal | None
    raw_text: str | None
    method: str
    confidence: float
    aggregate: str         # sum | assign
    note: str = ""
    context: str = ""
    accepted: bool = False
    edited: bool = False


@dataclass
class StagedDocument:
    path: Path
    form: FormMap | None
    detection_score: float
    owner: str = "taxpayer"        # taxpayer | spouse, for owner-scoped forms
    fields: list[StagedField] = field(default_factory=list)
    error: str = ""


def stage_document(path: Path, form_map: FormMap, score: float,
                   extracted: list[ExtractedField],
                   owner: str) -> StagedDocument:
    doc = StagedDocument(path=path, form=form_map, detection_score=score,
                         owner=owner)
    for ef in extracted:
        aggregate = "assign"
        for fm in form_map.fields:
            if fm.box == ef.box:
                aggregate = fm.aggregate
                break
        doc.fields.append(StagedField(
            source_file=path.name, form=form_map.form, box=ef.box,
            label=ef.label, target=ef.target.format(owner=owner),
            value=ef.value, raw_text=ef.raw_text, method=ef.method,
            confidence=ef.confidence, aggregate=aggregate,
            note=ef.note, context=ef.context))
    return doc


def aggregate_accepted(docs: list[StagedDocument]) -> dict[str, Decimal]:
    """Fold accepted fields into target→value. `sum` targets add across
    documents; `assign` targets take the last value (conflicts noted by the
    caller via provenance)."""
    out: dict[str, Decimal] = {}
    for doc in docs:
        for f in doc.fields:
            if not f.accepted or f.value is None:
                continue
            if f.aggregate == "sum":
                out[f.target] = out.get(f.target, Decimal(0)) + f.value
            else:
                out[f.target] = f.value
    return out


def apply_to_profile(raw: dict, aggregated: dict[str, Decimal]) -> list[tuple[str, str, str]]:
    """Apply aggregated values onto the raw profile dict. Returns
    [(target, old, new)] for display."""
    changes = []
    for target, value in sorted(aggregated.items()):
        old = get_path(raw, target, 0) or 0
        # Whole-dollar values are written as TOML integers so the profile
        # stays hand-editable; anything with cents stays a string (never a
        # TOML float — floats don't survive the no-float rule).
        rendered = int(value) if value == value.to_integral_value() else str(value)
        set_path(raw, target, rendered)
        changes.append((target, str(old), str(rendered)))
    return changes


def imports_dir() -> Path:
    return Path(user_data_dir("ouch")) / "imports"


def write_provenance(docs: list[StagedDocument], profile_name: str,
                     changes: list[tuple[str, str, str]]) -> Path:
    """Record source file, method, confidence, timestamp for every field."""
    stamp = _dt.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    record = {
        "timestamp": stamp,
        "profile": profile_name,
        "documents": [
            {
                "file": doc.path.name,
                "form": doc.form.form if doc.form else None,
                "detection_score": doc.detection_score,
                "owner": doc.owner,
                "error": doc.error,
                "fields": [
                    {
                        "box": f.box, "label": f.label, "target": f.target,
                        "value": str(f.value) if f.value is not None else None,
                        "raw_text": f.raw_text, "method": f.method,
                        "confidence": f.confidence, "accepted": f.accepted,
                        "edited": f.edited, "note": f.note,
                    }
                    for f in doc.fields
                ],
            }
            for doc in docs
        ],
        "changes": [{"target": t, "was": old, "now": new}
                    for t, old, new in changes],
    }
    d = imports_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{stamp}.json"
    path.write_text(json.dumps(record, indent=2))
    return path


def list_provenance() -> list[dict]:
    d = imports_dir()
    if not d.is_dir():
        return []
    records = []
    for p in sorted(d.glob("*.json")):
        try:
            records.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            continue
    return records
