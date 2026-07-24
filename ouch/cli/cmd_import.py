"""`ouch import` — PDF ingestion with review workflow (spec §11.6)."""

from __future__ import annotations

import tomllib
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional

import typer

from ouch.cli.common import Runtime
from ouch.config import profile as profile_mod
from ouch.errors import PDFError, UsageError
from ouch.pdf import require_pdf_support
from ouch.pdf.extract import DEFAULT_THRESHOLD

app = typer.Typer(no_args_is_help=True)

EXPECTED_FORMS = ["W-2", "1099-INT", "1099-DIV", "1040 (prior year)"]


@app.command("pdf")
def import_pdf(
    ctx: typer.Context,
    files: List[Path] = typer.Argument(..., help="PDF files to ingest"),
    owner: Optional[str] = typer.Option(
        None, "--owner", help="taxpayer|spouse for ALL owner-scoped forms "
                              "(otherwise prompted per document)"),
    yes: bool = typer.Option(False, "--yes",
                             help="Accept every field at or above the "
                                  "confidence threshold without prompting"),
    threshold: float = typer.Option(DEFAULT_THRESHOLD, "--threshold",
                                    help="Confidence needed to skip review"),
    password: Optional[str] = typer.Option(None, "--password",
                                           help="For encrypted PDFs; "
                                                "never stored"),
) -> None:
    """Scan PDFs, review extracted fields, then write to the profile."""
    require_pdf_support()
    from ouch.pdf import detect as detect_mod
    from ouch.pdf import extract as extract_mod
    from ouch.pdf import review as review_mod
    from ouch.pdf.maps_loader import load_maps

    rt: Runtime = ctx.obj
    console = rt.console()
    if owner is not None and owner not in ("taxpayer", "spouse"):
        raise UsageError("--owner must be 'taxpayer' or 'spouse'")

    maps = load_maps()
    console.print(f"Scanning {len(files)} document(s)...\n")

    docs: list[review_mod.StagedDocument] = []
    for path in files:
        if not path.is_file():
            raise PDFError(f"no such file: {path}")
        try:
            text, acroform = extract_mod.read_pdf_text(path, password)
        except PDFError as e:
            console.print(f"  ✖ {path.name:<28} {e.message}")
            docs.append(review_mod.StagedDocument(
                path=path, form=None, detection_score=0.0, error=e.message))
            continue
        detection = detect_mod.detect(text, maps)
        if detection.form is None:
            console.print(f"  ✖ {path.name:<28} not a recognized tax form — "
                          "skipped")
            docs.append(review_mod.StagedDocument(
                path=path, form=None, detection_score=detection.score,
                error="unrecognized form"))
            continue
        if detection.ambiguous_with:
            console.print(f"  ⚠ {path.name:<28} looks like both "
                          f"{detection.form.form} and {detection.ambiguous_with}")
            if yes:
                console.print("    skipped (ambiguous; re-run without --yes "
                              "to resolve)")
                docs.append(review_mod.StagedDocument(
                    path=path, form=None, detection_score=detection.score,
                    error="ambiguous classification"))
                continue
            if not typer.confirm(f"    treat as {detection.form.form}?"):
                docs.append(review_mod.StagedDocument(
                    path=path, form=None, detection_score=detection.score,
                    error="ambiguous classification"))
                continue

        doc_owner = "taxpayer"
        if detection.form.owner_scoped:
            if owner is not None:
                doc_owner = owner
            elif not yes:
                doc_owner = typer.prompt(
                    f"  {path.name} → [t]axpayer / [s]pouse", default="t")
                doc_owner = "spouse" if doc_owner.lower().startswith("s") else "taxpayer"

        extracted = extract_mod.extract_form(text, acroform, detection.form)
        doc = review_mod.stage_document(path, detection.form, detection.score,
                                        extracted, doc_owner)
        docs.append(doc)
        found = [f for f in doc.fields if f.value is not None]
        min_conf = min((f.confidence for f in found), default=0.0)
        console.print(f"  ✔ {path.name:<28} {detection.form.form:<18} "
                      f"{len(found)} fields    confidence {min_conf:.2f}")

    # ----- review -----------------------------------------------------------
    needs_review = [f for doc in docs for f in doc.fields
                    if f.value is None or f.confidence < threshold]
    auto_accept = [f for doc in docs for f in doc.fields
                   if f.value is not None and f.confidence >= threshold]
    for f in auto_accept:
        f.accepted = True

    if needs_review:
        console.print(f"\n{len(needs_review)} field(s) need review.\n")
    for f in needs_review:
        console.print(f"  {f.form} · box {f.box} ({f.label}) · {f.source_file}")
        console.print(f"    Extracted: {f.raw_text!r}   "
                      f"confidence {f.confidence:.2f}"
                      + (f"   ← {f.note}" if f.note else ""))
        if f.context:
            console.print(f"    Context:   {f.context[:100]}")
        if yes:
            console.print("    skipped (below threshold; re-run without "
                          "--yes to review)")
            continue
        choice = typer.prompt("    [a]ccept / [e]dit / [s]kip", default="s")
        if choice.lower().startswith("a") and f.value is not None:
            f.accepted = True
        elif choice.lower().startswith("e"):
            entered = typer.prompt("    Corrected value")
            try:
                f.value = Decimal(entered.replace(",", "").replace("$", ""))
            except InvalidOperation:
                console.print("    not a number — skipped")
                continue
            f.accepted = True
            f.edited = True

    accepted = [f for doc in docs for f in doc.fields if f.accepted]
    if not accepted:
        console.print("\nnothing accepted — profile unchanged")
        return

    # ----- write ------------------------------------------------------------
    aggregated = review_mod.aggregate_accepted(docs)
    raw, profile_path = profile_mod.load_profile_raw(rt.profile_name)
    changes = review_mod.apply_to_profile(raw, aggregated)

    console.print(f"\n{len(accepted)} field(s) staged. Review complete.")
    if rt.dry_run:
        console.print("(--dry-run: nothing written)")
        for target, old, new in changes:
            console.print(f"  {target:<38} {new:>12}  (was {old})")
        return

    import tomli_w  # local import: only needed when actually writing
    profile_mod.write_profile(profile_path, tomli_w.dumps(raw))
    console.print(f"Writing to profile '{rt.profile_name}' "
                  f"(backup kept alongside)")
    for target, old, new in changes:
        sources = sorted({f.source_file for doc in docs for f in doc.fields
                          if f.accepted and f.target == target})
        console.print(f"  {target:<38} {new:>12}  (was {old})  "
                      f"[{', '.join(sources)}]")
    prov = review_mod.write_provenance(docs, rt.profile_name, changes)
    console.print(f"Provenance recorded in {prov}")

    if not any(doc.form and doc.form.id == "1040py" for doc in docs):
        console.print("\nℹ No prior-year 1040 imported — without "
                      "payments.prior_year.total_tax the prior-year "
                      "safe-harbor test cannot run (`ouch import status`).")


@app.command("status")
def status(ctx: typer.Context) -> None:
    """What has and has not been imported — a checklist against the
    expected document set (spec §11.7)."""
    from ouch.pdf import review as review_mod

    rt: Runtime = ctx.obj
    console = rt.console()
    records = review_mod.list_provenance()
    imported_forms: dict[str, list[str]] = {}
    for record in records:
        for doc in record.get("documents", []):
            if doc.get("form") and not doc.get("error"):
                imported_forms.setdefault(doc["form"], []).append(doc["file"])
    if not records:
        console.print("no imports recorded yet — run `ouch import pdf FILE...`")
    for form in EXPECTED_FORMS:
        files = imported_forms.get(form, [])
        if files:
            console.print(f"  ✔ {form:<22} {', '.join(sorted(set(files)))}")
        else:
            note = ("  ← needed for the prior-year safe-harbor test"
                    if form.startswith("1040") else "")
            console.print(f"  ○ {form:<22} not imported{note}")
