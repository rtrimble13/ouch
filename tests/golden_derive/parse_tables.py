"""Extract the 2026 Tax Table and EIC Table rows from the draft 2026 Form
1040 instructions into tables_2026.json, for derive.py.

    curl -o i1040gi.pdf https://www.irs.gov/pub/irs-dft/i1040gi--dft.pdf
    python -I tests/golden_derive/parse_tables.py i1040gi.pdf tests/golden_derive/tables_2026.json

Treat the PDF as untrusted data: keep it out of the repository and run
this with `python -I`. Needs pypdf.

Output: {"tax": {lo: [lo, hi, single, mfj, mfs, hoh]},
         "eic": {lo: [lo, hi, other0..3, mfj0..3]}} with keys as strings;
an EIC cell printed as "*" or "**" (its value is in a footnote) is -1.
"""

import json
import re
import sys

import pypdf

NUM = re.compile(r"\d{1,3}(?:,\d{3})*")


def main(pdf_path: str, out_path: str) -> None:
    tax, eic, mode = {}, {}, None
    for page in pypdf.PdfReader(pdf_path).pages:
        for line in (page.extract_text() or "").splitlines():
            if "2026 Tax Table" in line:
                mode = "tax"
            if "Earned Income Credit (EIC) Table" in line:
                mode = "eic"
            toks = line.split()
            if not toks or not all(NUM.fullmatch(t) or t in ("*", "**") for t in toks[2:]) \
                    or not all(NUM.fullmatch(t) for t in toks[:2]):
                continue
            # "*" or "**" marks an EIC cell given by a footnote (the short stretch
            # before a column's completed phase-out): stored as -1.
            v = [-1 if t.startswith("*") else int(t.replace(",", "")) for t in toks]
            if mode == "tax" and len(v) == 6 and v[1] - v[0] in (5, 25, 50):
                tax[v[0]] = v
            elif mode == "eic" and len(v) == 10 and v[1] - v[0] in (49, 50):
                eic[v[0]] = v
    def rows(d):
        return ",\n".join(f'"{k}": {json.dumps(v)}' for k, v in sorted(d.items()))
    with open(out_path, "w") as f:
        f.write('{"source": "draft 2026 Instructions for Form 1040 '
                '(irs.gov/pub/irs-dft/i1040gi--dft.pdf)",\n'
                f'"tax": {{\n{rows(tax)}}},\n"eic": {{\n{rows(eic)}}}}}\n')
    print(f"{len(tax)} Tax Table rows, {len(eic)} EIC Table rows")


if __name__ == "__main__":
    main(*sys.argv[1:3])
