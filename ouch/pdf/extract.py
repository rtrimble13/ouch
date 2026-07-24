"""Extraction cascade (spec §11.3): AcroForm → positional/label-anchored text.

Each stage yields a confidence score; the cascade stops at the first stage
producing a value above the threshold. OCR (stage 5) is an optional extra and
not wired in v1 of the importer; scanned documents fall through to manual
entry in review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ouch.errors import PDFError
from ouch.pdf.maps_loader import FieldMap, FormMap

CONFIDENCE_ACROFORM = 0.98
CONFIDENCE_SAME_LINE = 0.90
CONFIDENCE_NEXT_LINE = 0.72
DEFAULT_THRESHOLD = 0.85

# A money-ish token: optional $, digits/commas, optional cents — tolerating
# the classic OCR confusion of 'O' for '0' (flagged, never silently accepted).
# Must contain at least one real digit and sit on word boundaries, so the
# 'o' in a word like "obligations" can never match.
_MONEY = re.compile(r"(?<![\w.])\$?\s*((?=[\dOo,.]*\d)[\dOo][\d,Oo]*"
                    r"(?:\.\d{0,2})?)(?![\w])")


@dataclass(frozen=True)
class ExtractedField:
    box: str
    label: str
    target: str            # still may contain {owner}
    raw_text: str | None   # exactly as it appeared in the document
    value: Decimal | None  # parsed value, None when unparseable/missing
    method: str            # acroform | text-line | text-next-line | missing
    confidence: float
    context: str = ""      # surrounding text for the review prompt
    note: str = ""


def read_pdf_text(path: Path, password: str | None = None) -> tuple[str, dict]:
    """Return (full text, acroform fields dict). Impure; shell-side only."""
    import pdfplumber
    import pypdf

    try:
        reader = pypdf.PdfReader(str(path))
        if reader.is_encrypted:
            if password is None:
                raise PDFError(
                    f"{path.name} is encrypted",
                    hint="re-run with --password (ouch never stores it)")
            if not reader.decrypt(password):
                raise PDFError(f"wrong password for {path.name}")
        acro = reader.get_fields() or {}
        acroform = {}
        for name, f in acro.items():
            value = f.get("/V")
            if value not in (None, ""):
                acroform[str(name)] = str(value)
    except PDFError:
        raise
    except Exception as e:
        raise PDFError(f"cannot read {path.name}: {e}") from e

    try:
        with pdfplumber.open(str(path), password=password) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception as e:
        raise PDFError(f"cannot extract text from {path.name}: {e}") from e
    return text, acroform


def _parse_money(token: str) -> tuple[Decimal | None, str]:
    """Parse a money token. Returns (value, note); an O-for-0 confusion
    parses with the substitution but carries a note and lower confidence."""
    cleaned = token.replace(",", "").replace("$", "").strip()
    note = ""
    if re.search(r"[Oo]", cleaned):
        note = "letter 'O' where a digit is expected — verify"
        cleaned = cleaned.replace("O", "0").replace("o", "0")
    try:
        return Decimal(cleaned), note
    except InvalidOperation:
        return None, f"unparseable number '{token}'"


def _candidate_lines(lines: list[str], label: str, box: str) -> list[int]:
    """Indexes of lines containing the label, best candidates first: a line
    that starts with the box number (`1 Wages...`, `Box 1 ...`) outranks a
    title or header line that merely mentions the label."""
    lowered = label.lower()
    box_lower = box.lower()
    matches = [i for i, line in enumerate(lines) if lowered in line.lower()]

    def rank(i: int) -> tuple[int, int]:
        stripped = lines[i].strip().lower()
        starts_with_box = (stripped.startswith(f"{box_lower} ")
                           or stripped.startswith(f"box {box_lower}"))
        return (0 if starts_with_box else 1, i)

    return sorted(matches, key=rank)


def extract_field(text: str, acroform: dict, field: FieldMap) -> ExtractedField:
    lines = text.splitlines()

    # Stage 1: AcroForm — match a field whose name mentions the box's label.
    for name, raw in acroform.items():
        for label in field.labels:
            if label.lower() in name.lower():
                value, note = _parse_money(raw)
                return ExtractedField(
                    box=field.box, label=label, target=field.target,
                    raw_text=raw, value=value, method="acroform",
                    confidence=CONFIDENCE_ACROFORM if not note else 0.5,
                    context=f"AcroForm field '{name}'", note=note)

    # Stages 2–3: label-anchored text — value to the right, else next line.
    for label in field.labels:
        for idx in _candidate_lines(lines, label, field.box):
            line = lines[idx]
            after = line[line.lower().index(label.lower()) + len(label):]
            m = _MONEY.search(after)
            if m:
                value, note = _parse_money(m.group(1))
                conf = CONFIDENCE_SAME_LINE if not note else 0.5
                return ExtractedField(
                    box=field.box, label=label, target=field.target,
                    raw_text=m.group(1), value=value, method="text-line",
                    confidence=conf, context=line.strip(), note=note)
            if idx + 1 < len(lines):
                m = _MONEY.search(lines[idx + 1])
                if m:
                    value, note = _parse_money(m.group(1))
                    conf = CONFIDENCE_NEXT_LINE if not note else 0.5
                    return ExtractedField(
                        box=field.box, label=label, target=field.target,
                        raw_text=m.group(1), value=value,
                        method="text-next-line", confidence=conf,
                        context=(line.strip() + " ⏎ " + lines[idx + 1].strip()),
                        note=note)

    return ExtractedField(
        box=field.box, label=field.labels[0], target=field.target,
        raw_text=None, value=None, method="missing", confidence=0.0,
        note="not found in document")


def extract_form(text: str, acroform: dict,
                 form_map: FormMap) -> list[ExtractedField]:
    out = []
    for field in form_map.fields:
        extracted = extract_field(text, acroform, field)
        if extracted.method == "missing" and not field.required:
            continue
        if extracted.value is not None and field.validation:
            lo = field.validation.get("min")
            hi = field.validation.get("max")
            if ((lo is not None and extracted.value < Decimal(str(lo)))
                    or (hi is not None and extracted.value > Decimal(str(hi)))):
                extracted = replace(
                    extracted, confidence=0.3,
                    note=f"value outside plausible range [{lo}, {hi}] — verify")
        out.append(extracted)
    return out
