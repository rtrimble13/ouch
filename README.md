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

This implements **Milestones 1–5** of the [specification](docs/SPEC.md):

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

- **M3 — tax-loss harvesting** (analysis, not execution — ouch never
  connects to a brokerage): canonical lot-CSV ingestion with IRA exclusion,
  §1091 wash-sale window analysis (DRIP conflicts pro-rata, IRA purchases
  flagged as *permanent* disallowance), benefit quantification by re-running
  the full pipeline (never `loss × marginal_rate`), deferred-cost/NPV
  honesty, gain-harvesting room in the 0% band, and holding-period alerts.

- **M4 — AI CPA agent** (`ouch ask`, `ouch agent [--review]`): a narrator
  and advisor over deterministic output, never a calculator. The model
  reaches profile data only through logged tools over the real engine and
  trace; guardrails verify every dollar figure against tool results
  (retry once, then refuse), screen out evasion requests, and flag uncited
  claims. Off by default, explicit consent before the first transmission,
  names redacted, `--no-ai` hard-disables all network paths. Requires
  `pip install "ouch[ai]"` and an API key in the environment.

- **M5 — depth**: the full credit suite with an ordered nonrefundable
  cascade — EITC (plateau trapezoid, investment-income limit, MFS
  exclusion), child & dependent care, AOTC (60/40 split) and LLC with
  MAGI phaseouts, saver's credit tiers; part-year/multi-state allocation
  by residency-month ratio (`taxpayer.former_state`); AMT credit
  carryforward (Form 8801 headroom against TMT); `ouch withhold
  estimates` with due dates and the `--annualized` income-installment
  method; CA/CO/MA/FL/WA state data files.

Still deferred: OCR for scanned documents, 1099-B lot ingestion, K-1/
REIT-PTP QBI components, cross-issuer substantially-identical analysis,
statutory Schedule AI annualization factors, per-state part-year
schedules, profile encryption, transcript logging, keyring key storage,
on-device model endpoints, the TUI.

## Documentation

- **[User manual](docs/MANUAL.md)** — complete reference: every command and
  option, the profile and config schemas, tax data files, output formats, exit
  codes, privacy controls, and known limits.
- **[Vignettes](docs/vignettes/README.md)** — ten tutorials that teach the whole
  tool through realistic situations, in order. Start at
  [vignette 1](docs/vignettes/01-first-estimate.md).
- **[Specification](docs/SPEC.md)** — the design document the implementation
  follows.

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
ouch --explain estimate            # append the computation trace
ouch explain fed.tax.preferential  # walk the derivation of any line
ouch withhold check                # are you on track? safe-harbor status
ouch withhold solve --target zero --w4
ouch withhold estimates --annualized    # quarterly schedule, lumpy income

ouch scenario new roth --set income.retirement.roth_conversion=75000
ouch scenario compare baseline roth
ouch scenario sweep --var income.retirement.roth_conversion \
                    --range 0:200000:10000

ouch import pdf ~/tax-docs/2025/*.pdf   # requires: pip install "ouch[pdf]"
ouch import status                 # checklist of imported documents

ouch harvest import lots.csv       # canonical lot schema (see --help)
ouch harvest scan --as-of 2025-12-12
ouch harvest simulate --sell L-0217 --sell L-0388
ouch harvest washsale-check

OUCH_AI_ENABLED=1 ouch ask "why did my effective rate jump?"
ouch agent --review                # requires: pip install "ouch[ai]"

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
