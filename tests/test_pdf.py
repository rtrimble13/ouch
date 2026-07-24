"""PDF ingestion: detection, extraction cascade, aggregation (spec §11).

Test PDFs are generated with reportlab to mimic the text layout of real
forms; they exercise the label-anchored stages of the cascade.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("pdfplumber")
pytest.importorskip("pypdf")
reportlab = pytest.importorskip("reportlab")

from ouch.pdf import detect as detect_mod
from ouch.pdf import extract as extract_mod
from ouch.pdf import review as review_mod
from ouch.pdf.maps_loader import load_maps


def make_pdf(path: Path, lines: list[str]) -> Path:
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path))
    y = 780
    for line in lines:
        c.drawString(60, y, line)
        y -= 22
    c.save()
    return path


@pytest.fixture(scope="module")
def maps():
    return load_maps()


@pytest.fixture()
def w2_pdf(tmp_path):
    return make_pdf(tmp_path / "w2.pdf", [
        "Form W-2 Wage and Tax Statement 2025",
        "OMB No. 1545-0008",
        "1 Wages, tips, other compensation 185,000.00",
        "2 Federal income tax withheld 31,800.00",
        "3 Social security wages 185,000.00",
        "17 State income tax 12,400.00",
    ])


@pytest.fixture()
def int_pdf(tmp_path):
    return make_pdf(tmp_path / "int.pdf", [
        "Form 1099-INT Interest Income 2025",
        "OMB No. 1545-0112",
        "1 Interest income 3,4O0.00",   # deliberate O-for-0
        "3 Interest on U.S. Savings Bonds and Treasury obligations 500.00",
    ])


def test_maps_load(maps):
    forms = {m.id for m in maps}
    assert {"w2", "1099int", "1099div", "1040py"} <= forms


def test_detect_w2(maps, w2_pdf):
    text, _ = extract_mod.read_pdf_text(w2_pdf)
    detection = detect_mod.detect(text, maps)
    assert detection.form is not None and detection.form.id == "w2"
    assert detection.score >= 0.5
    assert detection.ambiguous_with is None


def test_detect_unknown(maps, tmp_path):
    pdf = make_pdf(tmp_path / "junk.pdf", ["A grocery list", "milk", "eggs"])
    text, _ = extract_mod.read_pdf_text(pdf)
    detection = detect_mod.detect(text, maps)
    assert detection.form is None


def test_extract_w2_fields(maps, w2_pdf):
    text, acro = extract_mod.read_pdf_text(w2_pdf)
    form = next(m for m in maps if m.id == "w2")
    fields = {f.box: f for f in extract_mod.extract_form(text, acro, form)}
    assert fields["1"].value == Decimal("185000.00")
    assert fields["2"].value == Decimal("31800.00")
    assert fields["17"].value == Decimal("12400.00")
    assert all(f.confidence >= 0.85 for f in fields.values()
               if f.value is not None)


def test_ocr_confusable_flagged_not_silently_accepted(maps, int_pdf):
    """'3,4O0.00' parses with the O→0 substitution but must carry a low
    confidence and a note — the review gate, not the extractor, decides."""
    text, acro = extract_mod.read_pdf_text(int_pdf)
    form = next(m for m in maps if m.id == "1099int")
    fields = {f.box: f for f in extract_mod.extract_form(text, acro, form)}
    box1 = fields["1"]
    assert box1.value == Decimal("3400.00")
    assert box1.confidence < extract_mod.DEFAULT_THRESHOLD
    assert "O" in box1.note or "verify" in box1.note
    # The word 'obligations' must never be read as a number:
    assert fields["3"].value == Decimal("500.00")


def test_title_line_not_mistaken_for_box_value(maps, int_pdf):
    """The form title '...Interest Income 2025' must lose to the actual
    '1 Interest income …' line."""
    text, acro = extract_mod.read_pdf_text(int_pdf)
    form = next(m for m in maps if m.id == "1099int")
    box1 = next(f for f in extract_mod.extract_form(text, acro, form)
                if f.box == "1")
    assert box1.value != Decimal("2025")


def test_aggregation_sums_across_documents(maps, tmp_path):
    """Two W-2s for the same owner: wages and withholding sum (spec §11.5)."""
    pdfs = [
        make_pdf(tmp_path / "w2a.pdf", [
            "Form W-2 Wage and Tax Statement", "OMB No. 1545-0008",
            "1 Wages, tips, other compensation 100,000.00",
            "2 Federal income tax withheld 15,000.00",
            "3 Social security wages 100,000.00"]),
        make_pdf(tmp_path / "w2b.pdf", [
            "Form W-2 Wage and Tax Statement", "OMB No. 1545-0008",
            "1 Wages, tips, other compensation 40,000.00",
            "2 Federal income tax withheld 5,000.00",
            "3 Social security wages 40,000.00"]),
    ]
    form = next(m for m in maps if m.id == "w2")
    docs = []
    for pdf in pdfs:
        text, acro = extract_mod.read_pdf_text(pdf)
        extracted = extract_mod.extract_form(text, acro, form)
        doc = review_mod.stage_document(pdf, form, 1.0, extracted, "taxpayer")
        for f in doc.fields:
            f.accepted = f.value is not None
        docs.append(doc)
    agg = review_mod.aggregate_accepted(docs)
    assert agg["income.wages.taxpayer_w2"] == Decimal("140000.00")
    assert agg["payments.withholding.federal_ytd"] == Decimal("20000.00")


def test_owner_substitution(maps, tmp_path):
    pdf = make_pdf(tmp_path / "w2s.pdf", [
        "Form W-2 Wage and Tax Statement", "OMB No. 1545-0008",
        "1 Wages, tips, other compensation 96,000.00",
        "2 Federal income tax withheld 9,000.00",
        "3 Social security wages 96,000.00"])
    form = next(m for m in maps if m.id == "w2")
    text, acro = extract_mod.read_pdf_text(pdf)
    doc = review_mod.stage_document(
        pdf, form, 1.0, extract_mod.extract_form(text, acro, form), "spouse")
    targets = {f.target for f in doc.fields}
    assert "income.wages.spouse_w2" in targets
    assert not any("{owner}" in t for t in targets)


def test_apply_to_profile_writes_ints_for_whole_dollars():
    raw: dict = {}
    changes = review_mod.apply_to_profile(
        raw, {"income.wages.taxpayer_w2": Decimal("185000.00"),
              "income.investment.interest": Decimal("123.45")})
    assert raw["income"]["wages"]["taxpayer_w2"] == 185000
    assert raw["income"]["investment"]["interest"] == "123.45"
    assert len(changes) == 2


def test_missing_pdf_support_message(monkeypatch):
    import builtins
    from ouch.errors import PDFError
    from ouch import pdf as pdf_pkg
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("pdfplumber", "pypdf"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(PDFError) as e:
        pdf_pkg.require_pdf_support()
    assert 'ouch[pdf]' in (e.value.hint or "")
