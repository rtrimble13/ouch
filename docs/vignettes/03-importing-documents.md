# Vignette 3 — Twelve PDFs and a coffee

**Dev, 41, married filing jointly, Pennsylvania.** A folder of tax documents,
a spouse with her own W-2, and no intention of typing any of it in by hand.

**Commands introduced:** `ouch import pdf`, `ouch import status`
**Concepts:** the extraction cascade · confidence and review · owner assignment
· aggregation rules · provenance

---

## Before you start

```bash
pip install "ouch[pdf]"
```

Without the extra, `ouch import pdf` stops immediately and tells you so.

`ouch` reads four form types today: **W-2**, **1099-INT**, **1099-DIV**, and a
**prior-year 1040**. Text-layer PDFs only — the ones your employer and broker
publish. OCR for scanned paper is not implemented, and a scanned document falls
through to manual entry rather than being silently guessed at.

---

## 1. Point it at the folder

```bash
$ ouch import pdf ~/tax-docs/2026/*.pdf
```

```
Scanning 6 document(s)...

  W2_Cardinal.pdf → [t]axpayer / [s]pouse [t]: t
  ✔ W2_Cardinal.pdf              W-2                4 fields    confidence 0.90
  W2_spouse_OSU.pdf → [t]axpayer / [s]pouse [t]: s
  ✔ W2_spouse_OSU.pdf            W-2                3 fields    confidence 0.90
  ✔ 1099-INT_Huntington.pdf      1099-INT           2 fields    confidence 0.50
  ✔ 1099-DIV_Vanguard.pdf        1099-DIV           3 fields    confidence 0.90
  ✔ 1040_2025.pdf                1040 (prior year)  2 fields    confidence 0.90
  ✖ statement_march.pdf          not a recognized tax form — skipped
```

Four things happened in that block.

### Detection is by signature, not by filename

Each form map carries signature strings — a W-2 declares
`"Wage and Tax Statement"` and `"OMB No. 1545-0008"`. `ouch` scores every
document against every map and takes the best, provided it clears a minimum.
`statement_march.pdf` scored below the floor and was **skipped by name**, not
guessed at.

If two forms score close together, `ouch` says so and asks rather than picking:

```
  ⚠ some_doc.pdf              looks like both 1099-INT and 1099-DIV
    treat as 1099-INT? [y/N]
```

Under `--yes` an ambiguous document is skipped instead, because unattended
guessing is exactly the failure mode this design exists to prevent.

### Owner assignment happens per document

W-2s are **owner-scoped**: box 1 belongs to a person, not to a household. `ouch`
prompts once per owner-scoped document. You can answer up front instead:

```bash
ouch import pdf ~/tax-docs/2026/*.pdf --owner taxpayer
```

That assigns *every* owner-scoped document to one person — right for someone
with two jobs, wrong for a couple. **`--yes` with no `--owner` assigns
everything to `taxpayer`.** Get this wrong and two spouses' W-2s sum into one
person's wages, which validates cleanly and is completely incorrect. Assign
deliberately.

### Confidence comes from *how* the value was found

The extraction cascade tries progressively weaker methods and records which one
won:

| Method | Confidence | When |
|---|---|---|
| AcroForm field | 0.98 | The PDF has real form fields |
| Same-line label anchor | 0.90 | `1 Wages, tips, other compensation 118,400.00` |
| Next-line label anchor | 0.72 | The value wraps to the following line |
| Missing | 0.00 | The label never appeared |

The default review threshold is **0.85**, so same-line matches pass and
next-line matches get looked at. Raise it if you want to eyeball more:

```bash
$ ouch import pdf W2_Cardinal.pdf --yes --threshold 0.95
```

```
  W-2 · box 17 (State income tax) · W2_Cardinal.pdf
    Extracted: '4,120.00'   confidence 0.90
    Context:   17 State income tax 4,120.00
    skipped (below threshold; re-run without --yes to review)

nothing accepted — profile unchanged
```

At 0.95 nothing qualifies, and `--yes` skips rather than accepts. **Nothing
unconfirmed is ever written.**

---

## 2. Review what needs reviewing

```
1 field(s) need review.

  1099-INT · box 1 (Interest income) · 1099-INT_Huntington.pdf
    Extracted: '3,4O0.00'   confidence 0.50   ← letter 'O' where a digit is expected — verify
    Context:   1 Interest income 3,4O0.00
    [a]ccept / [e]dit / [s]kip [s]: e
    Corrected value: 3400
```

That is the classic scanned-document failure: a capital **O** where a zero
belongs. `ouch` will not silently coerce it — the money-token pattern
deliberately *matches* the malformed text so it can flag it, drops the
confidence to 0.50, and attaches a note saying exactly what it suspects. You get
the raw text and the surrounding line to judge for yourself.

Three choices: **accept** the parsed value, **edit** to type the correct number,
or **skip** and leave the profile alone. The default is skip — the safe option
is the one you get by pressing Enter.

---

## 3. The write, and the diff

```
11 field(s) staged. Review complete.
Writing to profile 'dev' (backup kept alongside)
  income.investment.interest                     3400  (was 0)  [1099-INT_Huntington.pdf]
  income.investment.tax_exempt_interest           250  (was 0)  [1099-INT_Huntington.pdf]
  income.wages.spouse_ss_wages                  74200  (was 0)  [W2_spouse_OSU.pdf]
  income.wages.spouse_w2                        74200  (was 71000)  [W2_spouse_OSU.pdf]
  income.wages.taxpayer_ss_wages               118400  (was 0)  [W2_Cardinal.pdf]
  income.wages.taxpayer_w2                     118400  (was 96000)  [W2_Cardinal.pdf]
  payments.prior_year.agi                      201340  (was 0)  [1040_2025.pdf]
  payments.prior_year.total_tax                 38720  (was 0)  [1040_2025.pdf]
  payments.withholding.federal_ytd              23880  (was 0)  [W2_Cardinal.pdf, W2_spouse_OSU.pdf]
  payments.withholding.state_ytd                 4120  (was 0)  [W2_Cardinal.pdf]
Provenance recorded in ~/.local/share/ouch/imports/2026-07-24T09-11-02.json
```

Every line shows the new value, the old value, and which document(s) it came
from. The previous profile is preserved as
`default.toml.2026-07-24T09-11-02.bak` next to the original.

### Aggregation rules matter

Look at `payments.withholding.federal_ytd`: **23880**, sourced from *both*
W-2s. Box 2 withholding **sums** across every document, because it is household
withholding. Meanwhile box 1 wages sum **per owner**, which is why Dev's
$118,400 and his spouse's $74,200 stayed separate. Prior-year 1040 lines
**assign** rather than sum — importing the same 1040 twice cannot double your
prior-year AGI.

This is also the mechanism behind the owner-assignment warning above: two W-2s
assigned to the same owner will correctly sum to one number.

### Preview first if you like

```bash
$ ouch --dry-run import pdf ~/tax-docs/2026/*.pdf
```

Same scan, same review, same diff — nothing written.

---

## 4. What's still missing?

```bash
$ ouch import status
```

```
  ✔ W-2                    W2_Cardinal.pdf, W2_spouse_OSU.pdf
  ✔ 1099-INT               1099-INT_Huntington.pdf
  ○ 1099-DIV               not imported
  ✔ 1040 (prior year)      1040_2025.pdf
```

A checklist against the expected document set, built from the provenance
records rather than from the profile — so it reflects what you *imported*, not
what happens to be non-zero.

The prior-year 1040 is singled out. Import a batch without one and `ouch` says
why it cares:

```
ℹ No prior-year 1040 imported — without payments.prior_year.total_tax the
  prior-year safe-harbor test cannot run (`ouch import status`).
```

Vignette 2 showed the consequence: no prior-year figures means `withhold check`
degrades to `Status: ?` instead of a pass/fail.

---

## 5. Provenance: where every number came from

Each import writes one JSON record under
`~/.local/share/ouch/imports/`:

```json
{
  "timestamp": "2026-07-24T09-11-02",
  "profile": "dev",
  "documents": [
    {
      "file": "W2_Cardinal.pdf",
      "form": "W-2",
      "detection_score": 1.0,
      "owner": "taxpayer",
      "error": "",
      "fields": [
        {
          "box": "1",
          "label": "Wages, tips, other compensation",
          "target": "income.wages.taxpayer_w2",
          "value": "118400.00",
          "raw_text": "118,400.00",
          "method": "text-line",
          "confidence": 0.9,
          "accepted": true,
          "edited": false,
          "note": ""
        }
      ]
    }
  ]
}
```

Six months later, when a figure looks wrong, this tells you which document it
came from, which box, how it was extracted, how confident the extractor was,
and whether a human touched it. `raw_text` preserves what was literally on the
page, so an edited value can always be checked against the original.

---

## 6. Then check the result

```bash
$ ouch estimate
```

Imported numbers are ordinary profile values from here on — nothing about them
is special. Which means the usual advice applies: read the warnings.

```
⚠ PA has local income taxes but no locality is set — local tax computed as
  zero, which is probably wrong
```

`ouch` knows which states levy municipal income tax and will not let a
silently-zero local line pass without comment. Vignette 10 shows how to add a
locality that doesn't ship.

---

## What Dev learned

- Detection is by document signature; unrecognised files are **skipped by
  name**, and ambiguous ones are **asked about**, never guessed.
- Confidence reflects *how* a value was found. Below the threshold it goes to
  review, and nothing unconfirmed is written.
- **Owner assignment is the one thing to get right by hand** — `--yes` alone
  assigns everything to `taxpayer`.
- Fields aggregate by rule: wages sum per owner, withholding sums across
  documents, prior-year lines assign.
- Every import leaves a backup and a provenance record.

## Try it yourself

```bash
ouch --dry-run import pdf ~/tax-docs/*.pdf          # preview
ouch import pdf w2.pdf --owner spouse               # skip the prompt
ouch import pdf secured.pdf --password "$PDF_PASSWORD"  # never stored, and
                                                        # kept out of shell history
ouch import pdf *.pdf --threshold 0.99              # review nearly everything
ouch import status
```

---

**Previous:** [Vignette 2 — The April surprise, fixed in July](02-the-april-surprise.md) ·
**Next:** [Vignette 4 — Freelancer, four payments a year](04-freelancer-quarterly.md)
