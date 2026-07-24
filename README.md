# `ouch`

**A CPA-grade personal tax estimation CLI.** The name is your reaction to the
number.

`ouch` is a local-first command-line tool that estimates an individual's total
tax burden across federal, state, and local jurisdictions, and helps you act
on that estimate — primarily by tuning payroll withholding so the April
balance is close to zero.

> **Estimates only. ouch is not tax advice and does not prepare or file
> returns.** Tax data may be projected or outdated — verify against IRS and
> state publications. Consult a licensed tax professional before acting.

## Status

This implements **Milestones 1–2** of the [specification](docs/SPEC.md):

- **M1 — core estimator**: the profile/config system, the pure federal
  calculation engine (preferential rate stacking, SE tax with W-2 wage-base
  coordination, NIIT, Additional Medicare, standard/itemized/QBI, CTC/ODC, a
  simplified AMT), data-driven state and local modules (none/flat/progressive
  regimes), the withholding solver, and full computation traceability.
- **M2 — scenarios and ingestion**: scenario patches (absolute, relative
  `"+10%"`, and computed `"= path * 0.10"` values) with `run`/`compare`/
  `sweep`, marginal-cost-of-change reporting, cliff detection, and `[assert]`
  guardrails; PDF ingestion for W-2 / 1099-INT / 1099-DIV / prior-year 1040
  with signature-based detection, a confidence-scored extraction cascade,
  interactive review (nothing is written unconfirmed), and per-field
  provenance records.

Not yet implemented (later milestones): tax-loss harvesting, the AI CPA
agent, part-year/multi-state, EITC and the remaining credit suite, OCR for
scanned documents, 1099-B lot ingestion, profile encryption.

## Install

Requires Python 3.11+.

```bash
python3 -m venv ~/.venvs/ouch
source ~/.venvs/ouch/bin/activate
pip install --upgrade pip
pip install .              # from a clone; PyPI publication TBD

ouch --version
ouch init                  # interactive first-run setup
```

Development install:

```bash
git clone <this repo> && cd ouch
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                     # full suite incl. golden fixtures
ouch data validate         # schema-check shipped tax data
```

## Quick start

```bash
ouch init                          # build a profile interactively
ouch estimate                      # one-screen summary of your burden
ouch estimate --explain            # append the computation trace
ouch explain fed.tax.preferential  # walk the derivation of any line
ouch withhold check                # are you on track? safe-harbor status
ouch withhold solve --target zero --w4

ouch scenario new roth --set income.retirement.roth_conversion=75000
ouch scenario compare baseline roth
ouch scenario sweep --var income.retirement.roth_conversion \
                    --range 0:200000:10000

ouch import pdf ~/tax-docs/2025/*.pdf   # requires: pip install "ouch[pdf]"
ouch import status                 # checklist of imported documents

ouch data list                     # jurisdictions × years available
ouch config show --origin          # where every setting came from
```

Global options go before the command: `ouch --format json estimate`,
`ouch --year 2026 --profile spouse estimate`.

## Design principles

- **Data is not code.** Every rate, bracket, threshold, and phase-out lives in
  versioned YAML under `ouch/taxdata/data/`, keyed by jurisdiction and year.
  Annual updates are data PRs. User files in `~/.local/share/ouch/taxdata/`
  (or `$OUCH_TAXDATA`) override shipped ones.
- **Every number is traceable.** The engine emits an ordered DAG of line
  items, each with a rule, a citation, and its upstream inputs.
  `ouch explain <line>` walks it. There are no unexplained numbers.
- **Pure functional core, imperative shell.** `TaxInput → TaxResult` with no
  I/O, clock, or mutation; the CLI shell does all file and terminal work.
- **Fail loudly, never silently guess.** Missing data year, unsupported
  state, inconsistent profile — each is a specific, actionable error with a
  documented exit code (see spec §8.4).
- **Money is `Decimal`, never float.** Constructing `Money` from a float
  raises. Rounding is explicit and follows IRS convention.

## Tax data honesty

Shipped data files carry `verified: false` until every figure has been
independently checked against primary sources (IRS Revenue Procedures, state
DOR publications). Every result computed from unverified data carries a
warning, and `ouch data verify` lists the files needing review. See spec
appendix D for the contribution checklist.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 2 | Invalid CLI usage |
| 3 | Configuration or profile error |
| 4 | Input validation error |
| 5 | Tax data missing/malformed for the requested year |
| 7 | Unsupported jurisdiction |
| 9 | Computation guard tripped (never emits a wrong number) |

## License

MIT — see [LICENSE](LICENSE).
