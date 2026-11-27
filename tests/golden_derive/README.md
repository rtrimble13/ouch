# Deriving the 2026 golden fixtures

`derive.py` writes the `tests/golden/2026_*` fixtures (`profile.toml`,
`expected.json`, `SOURCE.md`). It walks the 2026 forms line by line with
figures typed from Rev. Proc. 2025-32 and the 2026 IRS forms, each cited
next to its constant, and **does not import ouch**: a fixture produced by
ouch is not a fixture (spec §16.2).

Tax below $100,000 of taxable income and the earned income credit come from
the printed 2026 Tax Table and EIC Table, not a formula. `parse_tables.py`
extracts their rows from the draft 2026 Form 1040 instructions into
`tables_2026.json`:

```bash
curl -o /tmp/i1040gi.pdf https://www.irs.gov/pub/irs-dft/i1040gi--dft.pdf
python -I tests/golden_derive/parse_tables.py /tmp/i1040gi.pdf tests/golden_derive/tables_2026.json
python -I tests/golden_derive/derive.py --tables tests/golden_derive/tables_2026.json --out tests/golden
```

A filed return reads tax and the EIC from those tables, which are figured
at the midpoint of each $50 row and rounded to the dollar; ouch computes
them exactly. So fixture inputs put taxable income (and the QDCGT line 5
amount) at a row midpoint, where the two agree to within 50 cents, and
`tests/test_golden.py` compares money to the dollar (spec §19).

To add a fixture, add a `Case` to `CASES`, run the script, and read the
generated `SOURCE.md` against the forms before committing. If ouch then
disagrees, find out which is wrong from the form text; don't change the
expected values to match ouch.

When the IRS publishes the final 2026 forms, re-download them, re-run both
scripts and review any change in the diff.
