# `ouch` — User Manual

Complete reference documentation for `ouch`, a local-first, CPA-grade personal
tax estimation CLI.

> **Estimates only. `ouch` is not tax advice and does not prepare or file
> returns.** Shipped tax data may be projected or outdated — verify against IRS
> and state publications before acting. Consult a licensed tax professional.

If you are new to the tool, work through the
[vignettes](vignettes/README.md) first — they teach the same material as a
sequence of realistic tasks. This manual is the reference you come back to.

---

## Table of contents

1. [What ouch does](#1-what-ouch-does)
2. [Installation](#2-installation)
3. [First run](#3-first-run)
4. [Core concepts](#4-core-concepts)
5. [Global options](#5-global-options)
6. [Command reference](#6-command-reference)
7. [Profile reference](#7-profile-reference)
8. [Configuration reference](#8-configuration-reference)
9. [Tax data reference](#9-tax-data-reference)
10. [Scenario reference](#10-scenario-reference)
11. [Portfolio (lot CSV) reference](#11-portfolio-lot-csv-reference)
12. [Output formats](#12-output-formats)
13. [Exit codes and errors](#13-exit-codes-and-errors)
14. [Files on disk](#14-files-on-disk)
15. [Privacy and security](#15-privacy-and-security)
16. [Accuracy, fidelity, and known limits](#16-accuracy-fidelity-and-known-limits)
17. [Troubleshooting](#17-troubleshooting)
18. [Glossary](#18-glossary)

---

## 1. What ouch does

`ouch` estimates an individual's **total** tax burden — federal, state, and
local, income and payroll — for a given tax year, and helps you act on the
estimate. The three things it is built to answer:

| Question | Command family |
|---|---|
| What do I actually owe, and why? | `estimate`, `explain` |
| Am I paying enough, and how do I fix it? | `withhold` |
| What happens if I do *X*? | `scenario`, `harvest` |

Supporting commands handle input (`init`, `profile`, `import`), reference data
(`data`, `config`), and narration (`ask`, `agent`).

### What it is not

`ouch` does not prepare or file returns, does not connect to a brokerage or
payroll system, does not fill out or submit a W-4, and does not transmit
anything anywhere unless you explicitly turn on the optional AI feature. It is
a calculator with an audit trail.

---

## 2. Installation

Requires **Python 3.11+**.

```bash
python3 -m venv ~/.venvs/ouch
source ~/.venvs/ouch/bin/activate
pip install --upgrade pip
pip install .              # from a clone; PyPI publication TBD

ouch --version
```

`--version` also reports which optional extras are present:

```
ouch 0.1.0
  [pdf] pdfplumber 0.11.10
  [ai] not installed
  [crypto] cryptography 49.0.0
```

### Optional extras

| Extra | Install | Enables |
|---|---|---|
| `pdf` | `pip install "ouch[pdf]"` | `ouch import pdf` |
| `ai` | `pip install "ouch[ai]"` | `ouch ask`, `ouch agent` |
| `crypto` | `pip install "ouch[crypto]"` | reserved for profile encryption (not yet wired) |
| `dev` | `pip install -e ".[dev]"` | test suite, linting |

### Development install

```bash
git clone <this repo> && cd ouch
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                     # full suite incl. golden fixtures
ouch data validate         # schema-check shipped tax data
```

---

## 3. First run

```bash
ouch init          # interactive profile setup
ouch estimate      # one-screen summary
```

`ouch init` asks for tax year, filing status, date of birth, state, dependent
count, and a handful of income figures, then writes a TOML profile. Everything
it collects can be edited afterwards by hand — the profile is a plain text file
you own.

`ouch init` writes only the fields it asked about. Anything else (business
income, itemized deductions, prior-year figures, estimated payments) you add by
editing the profile. See [§7](#7-profile-reference) for every available field.

---

## 4. Core concepts

### 4.1 The profile

A **profile** is a TOML file describing one taxpayer's year:
`~/.config/ouch/profiles/<name>.toml`. The default profile is named `default`.
Select another with `--profile NAME` (or `OUCH_PROFILE`). A name containing a
path separator or ending in `.toml` is treated as a literal path, so you can
keep profiles anywhere:

```bash
ouch --profile ~/finances/2026/me.toml estimate
```

Profiles are written mode `0600` inside a `0700` directory, and every write
keeps a timestamped `.bak` alongside.

### 4.2 Tax data is data, not code

Every rate, bracket, threshold, and phase-out lives in versioned YAML under
`ouch/taxdata/data/`, keyed by jurisdiction and year. You can override any
shipped file, or add a jurisdiction that does not ship, by dropping a file into
your own data directory. See [§9](#9-tax-data-reference).

### 4.3 The computation trace

Every number `ouch` prints comes from a **line item** in an ordered DAG. Each
line carries an id (`fed.tax.preferential`), a label, an amount, a rule, an
authority (IRC section / form line), and the ids of its upstream inputs.

- `ouch explain <line-id>` walks one line's derivation.
- `ouch estimate --breakdown` (or `-vvv`) prints every line.
- `ouch --format json estimate` emits the whole trace as JSON.

The engine verifies the graph is acyclic and that every declared input exists
before returning a result; a violation is a hard error, not a warning.

### 4.4 Fidelity

Each line carries a fidelity level, and the result reports the **worst** one in
the header (`fidelity: exact` / `approximate` / `heuristic`). `approximate`
means the module deliberately simplifies (QBI, AMT, state part-year
allocation, wash-sale identity matching); `heuristic` means a figure is an
estimate of an estimate (the underpayment penalty). Fidelity is displayed, never
hidden.

### 4.5 Marginal rates are computed, not looked up

`ouch` never reads a marginal rate off a bracket table. It re-runs the entire
pipeline with an extra $1,000 of income and measures the difference. That is
why the reported marginal rate captures NIIT, phase-outs, credit cliffs, and
state/local spillover that a bracket table cannot show.

### 4.6 Money is exact

All amounts are `Decimal`, never float. Constructing money from a float raises.
Rounding is explicit.

### 4.7 Fail loudly

A missing data year, an unsupported state, an inconsistent profile, or a
tripped computation invariant each produce a specific, actionable error with a
documented exit code. `ouch` never guesses silently to keep going.

---

## 5. Global options

Global options go **before** the command:

```bash
ouch --format json --year 2026 estimate      # correct
ouch estimate --format json                  # wrong — not an estimate option
```

| Option | Env var | Meaning |
|---|---|---|
| `--profile`, `-p NAME\|PATH` | `OUCH_PROFILE` | Profile to load |
| `--year`, `-y YEAR` | `OUCH_TAX_YEAR` | Tax year; outranks the profile's `tax_year` |
| `--config`, `-c PATH` | `OUCH_CONFIG` | Alternate `config.toml` |
| `--format`, `-f FMT` | — | `table` \| `json` \| `csv` \| `markdown` — see [§12](#12-output-formats) |
| `--output`, `-o PATH` | — | Write the command's output to a file instead of stdout — see [§12](#12-output-formats) |
| `--verbose`, `-v` | — | Repeatable. `-vvv` prints the full trace from `estimate` |
| `--quiet`, `-q` | — | Verbosity 0 |
| `--no-color` | `OUCH_NO_COLOR`, `NO_COLOR` | Disable colour |
| `--dry-run` | — | Compute, print, write nothing to disk |
| `--no-ai` | — | Hard-disable every network/AI path for this run |
| `--explain` | — | Append the `fed.tax.total` derivation to `estimate` |
| `--version` | — | Version plus optional-extra status |
| `--help` | — | Help for the app or any subcommand |

**Year resolution order:** `--year` / `OUCH_TAX_YEAR` → the profile's
`tax_year` → `general.tax_year` in `config.toml` → the current calendar year.
When `--year` is given explicitly it overwrites the profile's `tax_year` for
the run.

> **Order matters.** Global options go before the subcommand:
> `ouch --explain estimate` and `ouch -vvv estimate`, not
> `ouch estimate --explain` (which exits 2 with "No such option"). The
> `estimate` footer suggests the correct form.

---

## 6. Command reference

### 6.1 `ouch init`

Interactive first-run setup. Prompts for tax year, filing status, date of
birth, state, dependent count, W-2 wages, federal withholding, interest,
ordinary and qualified dividends, and long-term gains; writes the profile named
by `--profile` (default `default`).

- Recognises the nine states with no income tax and says so.
- With `--dry-run`, prints the generated TOML instead of writing it.
- Overwrites without asking — but keeps a timestamped backup. Use
  `ouch profile new` if you want a confirmation prompt.

### 6.2 `ouch estimate`

The headline command: total burden, effective and marginal rates, and the
projected April balance.

| Option | Effect |
|---|---|
| `--federal-only` | Skip state and local entirely |
| `--state CODE` | Override the profile's state for this run |
| `--locality CODE` | Override the profile's locality for this run |
| `--itemize` | Force itemized deductions (mutually exclusive with `--standard`) |
| `--standard` | Force the standard deduction |
| `--marginal` | Append federal and combined marginal rates on the next $1,000 |
| `--breakdown` | Print every trace line after the summary |
| `--set PATH=VALUE` | Ad-hoc profile override; repeatable, never written to disk |
| `--compare-filing-status` | Run every filing status this profile can claim side by side — see below |

`--set` takes the same dotted paths as the profile schema:

```bash
ouch estimate --set income.wages.taxpayer_w2=150000 \
              --set adjustments.hsa=8300
```

Values parse as `true`/`false` → bool, integers → int, everything else stays a
string and becomes a `Decimal` during validation. Overrides apply to the
in-memory profile only.

`--set` addresses **tables**, not array elements: `--set dependents.0.name=x`
fails with `'dependents' is not a table`. Edit the profile to change a
dependent. The same restriction applies to scenario patch paths.

Output anatomy:

```
╭───────── ouch · Tax Year 2026 · Single · TX · fidelity: exact ─────────╮
│ Total income                                       $ 148,350           │
│ Adjusted gross income                              $ 148,350           │
│ Deduction (standard)                              $ (15,000)           │
│ Taxable income                                     $ 133,350           │
│                                                                        │
│ Federal income tax                                  $ 24,370           │
│   ordinary                                            $ 23,567         │
│   preferential (QD + LTCG)                               $ 803         │
│   ──────────────────────────────────────────────────────────           │
│ Federal total                                       $ 24,370           │
│   ══════════════════════════════════════════════════════════           │
│ TOTAL TAX BURDEN                                    $ 24,370           │
│                                                                        │
│   Effective rate (of AGI)                               16.43%         │
│   Effective rate (of gross income)                      16.43%         │
│   Marginal rate on next dollar (combined)               24.00%         │
│                                                                        │
│ Withheld + paid (projected through year end)        $ 21,400           │
│ ▸ PROJECTED BALANCE DUE                              $ 2,970           │
│                                                                        │
│   ⚠  Tax data for 2026 is unverified (projected)                       │
│   ⚠  Prior-year figures missing — prior-year safe-harbor test disabled │
╰────────────────────────────────────────────────────────────────────────╯
```

Lines appear only when non-zero: AMT, self-employment tax, Additional Medicare,
NIIT, credits, state, local, and part-year former-state tax are each suppressed
at zero. Warnings collect at the bottom.

#### Comparing filing statuses

`ouch estimate --compare-filing-status` runs the full pipeline once per filing
status the profile can claim and prints them side by side, calling out the
lowest total tax:

```
Filing status comparison · Tax Year 2025 · TX

                                   Single  Head of household
                                (current)
────────────────────────────────────────────────────────────
AGI                              $ 85,000           $ 85,000
Deduction                        $ 15,000           $ 22,500
Taxable income                   $ 70,000           $ 62,500
Credits                           $ 2,000            $ 2,000
Federal total                     $ 8,314            $ 5,160
State tax                             $ 0                $ 0
TOTAL TAX                         $ 8,314            $ 5,160
Balance / (refund)                $ (686)          $ (3,840)
Effective rate (AGI)                9.78%              6.07%

Lowest total tax: Head of household — $ 3,154 less than single (current).
```

Which statuses are compared:

| Status | Compared when |
|---|---|
| Single | Always (for an unmarried profile) |
| Head of household | A dependent lived in your home more than six months, or is a `parent`; or the profile already claims it |
| Qualifying surviving spouse | The profile already claims it — eligibility depends on a spouse's date of death, which the profile does not record |

Statuses not compared are listed with the reason. Eligibility is checked only
against what the profile records — confirm the marital-status, household-cost,
and dependency tests yourself (IRS Pub. 501).

**Married profiles are refused (exit 2).** A joint profile cannot be split
into two separate returns: investment income, deductions, and payments are not
attributed per spouse. To compare MFJ with MFS, create one profile per spouse
with `filing_status = "married_filing_separately"` and compare the sum of their
`ouch --profile NAME estimate` totals with the joint total.

`--format json` emits every status's full result plus the omitted list. The
flag cannot be combined with `--marginal`, `--breakdown`, or `--explain`.

### 6.3 `ouch explain LINE_ID`

Walks the derivation of one trace line as a tree, with authority, rule, and
every upstream input recursively. Passing an unknown id lists every available
id:

```
✖ no line item 'fed.nope' in this computation
  → available: fed.adjustments, fed.agi, fed.deduction, fed.income.capital,
    fed.income.total, fed.income.wages, fed.setax, fed.tax.ordinary,
    fed.tax.preferential, fed.tax.total, fed.taxable, total.balance,
    total.payments, total.tax, tx.tax
```

Which ids exist depends on your profile — SE tax, AMT, credits, and state
lines appear only when they apply. Citations can be suppressed with
`output.show_citations = false` in `config.toml`.

### 6.4 `ouch withhold`

#### `ouch withhold check`

Are you on track? Prints projected tax, payments to date, projected additional
withholding, projected total payments, the April balance, and the federal
safe-harbor analysis.

```
Projected total tax                         $ 86,511
Withheld to date (all jurisdictions)        $ 50,500
Projected additional withholding            $ 15,950     (11 periods × $ 1,450)
Projected total payments                    $ 66,450
────────────────────────────────────────────────────────────
Projected balance due                       $ 20,061

Safe harbor analysis (federal):
  90% of current-year tax                   $ 51,033
  110% of prior-year tax                   $ 64,790
  Projected federal payments                $ 50,750
  Status: ✗ SHORT by $ 283
  Estimated underpayment penalty                $ 11   (Form 2210 approximation)
```

The prior-year test uses 110% when prior-year AGI exceeds the high-income
threshold, 100% otherwise. Without `payments.prior_year.total_tax` the
prior-year test cannot run and the status becomes `?` rather than a
false negative.

> **Reading the columns.** The money lines are an addition: withheld to date
> plus projected additional withholding (plus any estimated payments) equals
> projected total payments, all jurisdictions. When `state_per_period` or
> `local_per_period` is set, the per-period figure is their sum with the
> federal amount, and an indented line shows the split:
>
> ```
> Projected additional withholding            $ 23,650     (11 periods × $ 2,150)
>   per period: federal $ 1,450 · state $ 500 · local $ 200
> Estimated payments                           $ 1,000
> ```
>
> The safe-harbor block below is federal-only, and labelled as such.

#### `ouch withhold solve`

Solves for the per-paycheck **federal** withholding that hits a target, by
bisection over the full pipeline.

| Option | Values |
|---|---|
| `--target` | `zero` (default), `refund:AMOUNT`, `owe:AMOUNT`, `safe-harbor` |
| `--periods-remaining N` | Override the auto-derived remaining pay-period count |
| `--w4` | Also print Form W-4 line entries |

```
11 pay periods remain in 2026.

To reach a $0 balance:
  Federal withholding per period          $ 3,273.69
  (currently $ 1,450.00; change of $ 1,823.69 per period, $ 20,061 total)
  Resulting April balance due: $ 0
```

`--target safe-harbor` finds the minimum that avoids the underpayment penalty —
usually far less cash now, at the cost of a balance in April.

The solver adjusts federal withholding only. State and local withholding are
read from the profile and projected forward unchanged.

#### `ouch withhold w4`

Shorthand for `withhold solve --target zero --w4`.

The W-4 block reacts to your profile: the Step 2 multiple-jobs box and the
dual-earner warning appear when both spouses have W-2 wages; Step 3 mentions
your dependent count; Step 4(a) appears when you have Schedule C income; Step
4(c) carries the extra per-period amount.

```
Form W-4 entries (give to ONE employer — the higher earner):
  Step 2:  ☑ check the box (multiple jobs / spouse works)
  ⚠ Dual-earner under-withholding is the most common cause of a surprise April
    bill; claim dependents on ONE W-4 only.
  Step 3:  dependents as computed on your return (1 dependent(s))
  Step 4(a) other income: $ 28,000 (self-employment)
  Step 4(c) extra withholding per pay period: $ 1,824
```

#### `ouch withhold estimates`

Quarterly estimated-payment schedule with statutory due dates.

| Option | Values |
|---|---|
| `--target` | `safe-harbor` (default, penalty-avoidance minimum) or `zero` (no April balance) |
| `--annualized` | Use `payments.annualized_income_fractions` so the requirement follows when income is actually earned |

```
  Q1  due 2026-04-15        $ 2,393   ✔ paid  (paid $ 5,000)
  Q2  due 2026-06-15        $ 3,590   ✔ paid  (paid $ 5,000)
  Q3  due 2026-09-15        $ 5,983   due
  Q4  due 2027-01-15       $ 11,966   due
```

Withholding is treated as paid evenly across the year regardless of when it
happened — which is exactly why a late-year withholding increase can cure an
earlier quarter's shortfall while a late estimated payment cannot.

`--annualized` without `payments.annualized_income_fractions` in the profile is
a usage error. When the fractions *are* present but `--annualized` is not
passed, they are ignored for that run.

### 6.5 `ouch scenario`

See [§10](#10-scenario-reference) for the file format.

| Subcommand | Purpose |
|---|---|
| `new NAME [--set PATH=VALUE]... [--template T] [--base P]` | Create a scenario |
| `list` | List scenarios with their descriptions and tags |
| `show NAME` | Print a scenario's description, tags, patch, and assertions |
| `delete NAME` | Delete a scenario file |
| `run NAME` | Compare `baseline` against one scenario |
| `compare NAME...` | Compare any number side by side |
| `sweep --var PATH --range LO:HI:STEP` | Evaluate one variable across a range |

`new` requires either `--set` entries or `--template`; it refuses to overwrite
an existing scenario. Available templates: `bonus-deferral`,
`bunch-charitable`, `hsa-max`, `relocate-state`, `roth-conversion`,
`solo401k`.

`compare` accepts the pseudo-name **`baseline`**, meaning the unpatched
profile. The base profile for the whole comparison comes from the *first*
scenario named; a `base` of `default` resolves to whatever `--profile` is
active.

```
                                  baseline     roth-140k      roth-max
──────────────────────────────────────────────────────────────────────
AGI                              $ 310,000     $ 450,000     $ 385,000
Taxable income                   $ 280,000     $ 420,000     $ 355,000
Federal total                     $ 51,534      $ 85,134      $ 69,534
NIIT                               $ 1,520       $ 1,520       $ 1,520
State tax                         $ 12,320      $ 18,480      $ 15,620
TOTAL TAX                         $ 63,854     $ 103,614      $ 85,154
Effective rate (AGI)                20.60%        23.03%        22.12%
Marginal rate (next $)              29.30%        29.30%        29.30%

roth-140k: Δ tax vs baseline $ 39,760
  Marginal cost of the change: 28.40% of the changed amount (Δ input $ 140,000)
```

`compare` also calls out threshold spillover — crossing into NIIT, or
triggering AMT — and reports any `[assert]` violations, exiting **9** if one
fires.

`sweep` options:

| Option | Meaning |
|---|---|
| `--var PATH` | Dotted profile path to vary (required) |
| `--range LO:HI:STEP` | Inclusive range (required) |
| `--metric A,B` | Result metrics to show (default `total_tax_all_jurisdictions,marginal_rate_combined`) |
| `--cliff-threshold F` | Marginal-rate jump that flags a cliff (default `0.03`) |

```
income.retirement.roth_conversion     Total tax   Δ tax/Δ var     marginal_rate_comb
──────────────────────────────────────────────────────────────
       140,000       103,614        28.40%                 0.2930
       150,000       106,566        29.52%                 0.3730
       160,000       110,206        36.40%                 0.3730   ⚠ cliff
```

With `--format csv`, `sweep` emits machine-readable rows instead:

```
income.retirement.roth_conversion,total_tax,step_marginal,cliff,total_tax_all_jurisdictions
0,63854,,,63854
25000,70954,0.2840,,70954
50000,78054,0.2840,,78054
```

### 6.6 `ouch import`

Requires `pip install "ouch[pdf]"`.

#### `ouch import pdf FILE...`

Detects the form type by signature scoring, extracts fields through a
confidence-scored cascade (AcroForm → same-line label anchor → next-line label
anchor), lets you review anything below the threshold, and only then writes to
the profile.

| Option | Meaning |
|---|---|
| `--owner taxpayer\|spouse` | Assign every owner-scoped document (W-2s) to one person instead of prompting |
| `--yes` | Accept everything at or above the threshold; skip review and skip sub-threshold fields |
| `--threshold F` | Confidence required to skip review (default `0.85`) |
| `--password P` | For encrypted PDFs; used and discarded, never written to disk. Pass it via a variable (`--password "$PDF_PASSWORD"`) to keep it out of shell history |

Supported forms: **W-2**, **1099-INT**, **1099-DIV**, and a **prior-year
1040**. Unrecognised documents are skipped by name, not guessed at. A document
that scores close to two forms is reported as ambiguous and you are asked to
resolve it (or it is skipped under `--yes`).

```
Scanning 6 document(s)...

  ✔ 1040_2025.pdf                1040 (prior year)  2 fields    confidence 0.90
  ✔ 1099-DIV_Vanguard.pdf        1099-DIV           3 fields    confidence 0.90
  ✔ 1099-INT_Huntington.pdf      1099-INT           2 fields    confidence 0.50
  ✔ W2_Cardinal.pdf              W-2                4 fields    confidence 0.90
  ✔ W2_spouse_OSU.pdf            W-2                3 fields    confidence 0.90
  ✖ statement_march.pdf          not a recognized tax form — skipped
```

Fields below the threshold go to review, with the raw text, the surrounding
context, and a note when something looks suspicious:

```
  1099-INT · box 1 (Interest income) · 1099-INT_Huntington.pdf
    Extracted: '3,4O0.00'   confidence 0.50   ← letter 'O' where a digit is expected — verify
    Context:   1 Interest income 3,4O0.00
    [a]ccept / [e]dit / [s]kip [s]:
```

Aggregation across documents follows each field's rule: W-2 box 1 **sums** per
owner, box 2 withholding **sums** across every document, prior-year 1040 lines
**assign**. Two W-2s assigned to the same owner therefore add together — which
is correct for one person with two jobs and wrong for a couple, so assign
owners deliberately.

Writing shows a diff and records provenance:

```
Writing to profile 'dev' (backup kept alongside)
  income.wages.spouse_w2                        74200  (was 71000)  [W2_spouse_OSU.pdf]
  income.wages.taxpayer_w2                     118400  (was 96000)  [W2_Cardinal.pdf]
  payments.withholding.federal_ytd              23880  (was 0)  [W2_Cardinal.pdf, W2_spouse_OSU.pdf]
Provenance recorded in ~/.local/share/ouch/imports/<timestamp>.json
```

With `--dry-run` the same diff prints and nothing is written.

#### `ouch import status`

A checklist against the expected document set, flagging the prior-year 1040
because it is what unlocks the prior-year safe-harbor test.

```
  ✔ W-2                    W2_Cardinal.pdf, W2_spouse_OSU.pdf
  ✔ 1099-INT               1099-INT_Huntington.pdf
  ○ 1099-DIV               not imported
  ✔ 1040 (prior year)      1040_2025.pdf
```

### 6.7 `ouch harvest`

Tax-loss harvesting **analysis**. `ouch` never connects to a brokerage and
never places a trade.

#### `ouch harvest import FILE.csv`

Validates a lot CSV ([§11](#11-portfolio-lot-csv-reference)) and installs it as
your portfolio. Every malformed row is reported together, not one at a time.
`--dry-run` validates without installing.

#### `ouch harvest scan`

Ranks loss positions by the tax benefit of realizing them — computed by
**re-running the whole pipeline**, not by multiplying loss by a rate.

| Option | Meaning |
|---|---|
| `--as-of YYYY-MM-DD` | Hypothetical sale date (default: today) |
| `--min-benefit N` | Hide candidates below this benefit |

```
Portfolio: 9 lots · 2 account(s) · as of 2026-12-12
Harvest candidates · marginal ST 32.80% / LT 23.80% (combined, computed numerically)

    # Symbol  Lot        Char     Unrealized   Tax benefit  Wash risk
    1 ARKG    L-0217     short    $ (14,200)       $ 4,658  ✔ clear
    2 VXUS    L-0431     short     $ (8,241)       $ 2,703  ⚠ 3.114 sh repurchased in window — $63 disallowed
    3 IEFA    L-0155     long      $ (6,100)       $ 1,722  ✖ IRA purchase in window — loss PERMANENTLY disallowed
    4 BND     L-0388     short     $ (2,955)         $ 969  ✔ clear
      ARKG L-9002: excluded — IRA lot — a loss there has no tax value
  ⚠ VTI L-0102: gain lot crosses the long-term boundary in 40 days — waiting
    changes the rate from short-term to long-term.
```

`scan` also reports remaining room in the 0% preferential band (gain
harvesting) when any exists.

#### `ouch harvest simulate --sell LOT_ID [--sell LOT_ID]...`

Runs the specified sale through the full pipeline and shows before/after by
jurisdiction, plus the deferred cost.

| Option | Default | Meaning |
|---|---|---|
| `--sell ID` | required, repeatable | Lot to sell (whole lot) |
| `--as-of DATE` | today | Sale date |
| `--future-rate F` | current marginal LTCG rate | Assumed rate when the deferred gain is realized |
| `--discount-rate F` | `0.05` | NPV discount rate |
| `--horizon N` | `10` | Years until the deferred gain is realized |

```
  Tax effect:
                                  Before       After           Δ
    Federal                     $ 68,532    $ 63,763   $ (4,769)
    State (MA)                  $ 18,490    $ 17,632     $ (858)
    Total tax                   $ 87,022    $ 81,396   $ (5,627)

  Deferred cost (harvesting is largely a deferral):
    Basis reduction                           $ 17,155
    Future tax at assumed 23.80%               $ 4,083
    Net present benefit @ 5% / 10 yr             $ 3,120
```

Above the tax effect, a netting walk shows the short- and long-term amounts
realized, any loss applied against ordinary income, and any carryforward. The
ordinary-income line is marked `(capped at $ 3,000)` — `$ 1,500` for MFS —
only when the §1211(b) cap actually bound; an unmarked amount was absorbed in
full.

Selling an IRA lot is refused outright. Wash-sale conflicts are reported after
the numbers, with an explicit note that the pipeline figures assume the **full**
loss.

#### `ouch harvest washsale-check`

Wash-sale exposure for every loss lot in the portfolio, at `--as-of` (default
today).

```
  ⚠ VXUS L-0431: 3.114 sh purchased 2026-11-28 in Taxable-Brokerage — $63 of the
    loss disallowed if sold 2026-12-12
  ⚠ IEFA L-0155: 500 sh purchased 2026-12-01 in Rollover-IRA (IRA — permanent) —
    $6,100 of the loss disallowed if sold 2026-12-12
```

### 6.8 `ouch ask` / `ouch agent`

The optional AI CPA. Requires `pip install "ouch[ai]"` and an API key in the
environment variable named by `ai.api_key_env` (default `ANTHROPIC_API_KEY`).

```bash
ouch ask "why did my effective rate jump?"     # one-shot
ouch agent                                     # interactive session
ouch agent --review                            # proactive whole-profile review
```

Both accept `--yes` to skip the transmission confirmation.

The model is a **narrator over deterministic output, never a calculator**. It
cannot see your profile directly; it reaches data only through ten logged tools
that call the real engine:

| Tool | Returns |
|---|---|
| `get_result_summary` | Top-level `TaxResult` fields |
| `get_line_item` | One trace line with authority and rule |
| `get_trace_subtree` | A line plus every upstream line |
| `run_scenario` | A patched run through the real engine, with the delta |
| `sweep` | One variable across a range (max 30 points) |
| `check_safe_harbor` | Requirement, payments, shortfall, penalty |
| `solve_withholding` | The bisection solver's per-period answer |
| `list_harvest_candidates` | Harvest candidates with wash-sale risk |
| `get_taxdata` | A threshold/rate from the loaded federal file, with citation |
| `get_profile_field` | One redaction-aware profile field by dotted path |

**Guardrails run on every response:**

- *Numeric grounding* — every dollar figure above $100 must match a
  tool-returned number within $1. If not, the model is told exactly which
  figures failed and asked to re-answer; a second failure produces a refusal
  rather than a wrong number.
- *Citation presence* — a response with dollar figures and no `[line.id]`
  citations is flagged.
- *Scope* — requests to hide income or evade tax are refused before anything
  is transmitted.
- *Disclaimer* — appended unconditionally.

**Privacy:** off by default; nothing is transmitted until you both enable AI
and confirm the transmission notice; names are stripped from the profile before
the session is built and identity fields are never returned by any tool;
`--no-ai` hard-disables every network path for a run. See
[§15](#15-privacy-and-security).

The session tail reports how many tool calls were logged:

```
(7 tool call(s) logged this session)
```

Type `/quit`, `/exit`, `quit`, or `exit` to leave the interactive session.

### 6.9 `ouch profile`

| Subcommand | Purpose |
|---|---|
| `show` | Print the resolved, validated profile as JSON |
| `validate` | Validate; exit 0 when clean, exit 3 with a collected error report otherwise |
| `new [NAME]` | Write a commented template profile (prompts before overwriting) |
| `path` | Print the path of the profile in use |

`profile show` prints the *post-validation* view — defaults filled in, types
coerced — which is the surest way to see what the engine actually received.

### 6.10 `ouch data`

| Subcommand | Purpose |
|---|---|
| `list` | Jurisdictions × years discoverable, from every search path |
| `validate` | Schema-check every discoverable file; exit 5 on any failure |
| `show KIND NAME [YEAR] [--key K]` | Print a data file, or one dotted key, as JSON |
| `verify` | List files still marked `verified: false` |

```bash
ouch data show federal 2026 --key niit
ouch data show state MA 2026 --key meta
ouch data show local NYC 2026 --key brackets
```

For `federal`, `NAME` is the year and `YEAR` is omitted.

### 6.11 `ouch config`

| Subcommand | Purpose |
|---|---|
| `show [--origin]` | Every resolved setting, optionally with where it came from |
| `path` | Print the `config.toml` path |

```
ai.enabled = False    (default)
general.default_profile = 'default'    (default)
output.format = 'table'    (default)
```

---

## 7. Profile reference

A profile is TOML. Every section and key is optional; omitted values default to
zero, empty, or the documented default. Money values may be written as numbers
or quoted strings — both become exact `Decimal`s.

```toml
schema_version = 2      # current version; a newer version is a hard error
tax_year       = 2026
```

### `[taxpayer]`

| Key | Type | Default | Notes |
|---|---|---|---|
| `name` | string | `""` | Never transmitted to the AI; strip it if you like |
| `birth_date` | date | — | Drives the age-65 additional standard deduction, the 2025–2028 enhanced deduction for seniors, and dependent-care tests |
| `blind` | bool | `false` | Additional standard deduction |
| `filing_status` | enum | `single` | `single`, `married_filing_jointly`, `married_filing_separately`, `head_of_household`, `qualifying_surviving_spouse` |
| `state` | string | `""` | Two-letter code; empty means federal only |
| `locality` | string | `""` | e.g. `NYC` |
| `residency_months` | int 0–12 | `12` | Months resident in `state` |
| `former_state` | string | `""` | Where the remaining months were spent |

### `[spouse]`

| Key | Type | Notes |
|---|---|---|
| `name` | string | |
| `birth_date` | date | |
| `blind` | bool | |

Present only for married statuses — a `[spouse]` section with data alongside a
single/HoH status is a validation error.

### `[[dependents]]`

Repeat the table for each dependent.

| Key | Type | Default | Notes |
|---|---|---|---|
| `name` | string | `""` | |
| `birth_date` | date | — | Required for the engine to test CTC/EITC/care eligibility |
| `relationship` | string | `"child"` | Non-`child` relationships fall to the other-dependent credit |
| `months_in_home` | int 0–12 | `12` | Must exceed 6 to qualify |
| `student` | bool | `false` | Extends the EITC child test to under 24 |
| `disabled` | bool | `false` | |
| `qualifies_ctc` | bool | — | Explicit override of the engine's CTC test |

### `[income.wages]`

| Key | Notes |
|---|---|
| `taxpayer_w2` | W-2 box 1 |
| `spouse_w2` | Requires `married_filing_jointly` |
| `taxpayer_ss_wages` | W-2 box 3 (capped at the Social Security wage base). Defaults to box 1 when absent. Only the business owner's figure reduces the wage base left for SE tax — see `income.business.owner` |
| `spouse_ss_wages` | |
| `taxpayer_medicare_wages` | W-2 box 5 — the uncapped Additional Medicare (Form 8959) base. Defaults to box 1 when absent; box 5 usually exceeds box 1 by 401(k)/403(b) deferrals, so supply it if you are near the threshold |
| `spouse_medicare_wages` | |

### `[income.investment]`

| Key | Notes |
|---|---|
| `interest` | Taxable interest |
| `tax_exempt_interest` | Excluded federally; may still feed state additions |
| `in_state_muni_interest` | Subset of the above; cannot exceed it |
| `treasury_interest` | Federally taxable, state-exempt |
| `ordinary_dividends` | 1099-DIV box 1a — **inclusive** of qualified |
| `qualified_dividends` | box 1b — cannot exceed box 1a |
| `short_term_gains` | May be negative |
| `long_term_gains` | May be negative |
| `capital_loss_carryforward` | Positive number = loss carried in |
| `section_1250_gain` | 25% rate group |
| `collectibles_gain` | 28% rate group |

### `[income.business]`

| Key | Notes |
|---|---|
| `owner` | `"taxpayer"` (default) or `"spouse"` — whose business it is. The Social Security wage base is per person, so SE tax is coordinated against the owner's own W-2 box 3 only; the other spouse's wages never use it up. `"spouse"` requires `married_filing_jointly` |
| `schedule_c_net` | Net self-employment income. A loss (negative) reduces total income and AGI; at-risk, passive-activity, hobby-loss, and excess-business-loss limits are not modeled, and a warning says so |
| `se_health_premiums` | Self-employed health insurance deduction |
| `qbi_eligible_income` | §199A qualified business income |
| `qbi_w2_wages_paid` | For the wage limitation above the threshold |
| `qbi_ubia` | Unadjusted basis immediately after acquisition |
| `sstb` | Specified service trade or business |

### `[income.retirement]`

`pension`, `ira_distributions`, `taxable_social_security`,
`social_security_gross`, `roth_conversion`.

Provide `social_security_gross` and the engine computes the taxable portion
iteratively; provide `taxable_social_security` to state it directly.

### `[income.other]`

`rental_net`, `k1_ordinary`, `unemployment`, `other_income`.

### `[adjustments]`

Above-the-line: `traditional_ira`, `hsa`, `student_loan_interest`,
`educator_expenses`, `sep_solo401k`, `alimony_paid` (pre-2019 decrees only),
`early_withdrawal_penalty`.

### `[deductions]`

| Key | Values | Notes |
|---|---|---|
| `mode` | `auto` (default), `standard`, `itemized` | `auto` takes the larger |

### `[deductions.itemized]`

`mortgage_interest`, `mortgage_balance`, `mortgage_grandfathered`,
`state_local_income_tax` (the engine computes it when left at zero),
`real_estate_tax`, `personal_property_tax`, `charitable_cash`,
`charitable_noncash`, `medical_expenses`, `investment_interest`, `other`.

### `[expenses]`

Credit-qualifying expenses: `dependent_care`, `education_aotc`,
`education_llc`.

### `[carryovers]`

`amt_credit` — the Form 8801 minimum tax credit carried in. It is recoverable
only up to the excess of regular tax over tentative minimum tax in a year with
no new AMT; any remainder is reported as carrying forward.

### `[payments.withholding]`

| Key | Default | Notes |
|---|---|---|
| `federal_ytd`, `state_ytd`, `local_ytd` | `0` | Withheld so far |
| `federal_per_period`, `state_per_period`, `local_per_period` | `0` | Per paycheck going forward |
| `pay_periods_per_year` | `24` | 1–53 |
| `periods_remaining` | derived | Left at 0, the CLI derives it from today's date |

The derivation uses the year being computed — `--year` if given, otherwise the
profile's `tax_year`. A year that has already closed projects no further
paychecks (0), a future year projects all of them, and the current year
prorates by the days left. Set `periods_remaining` yourself to override it.

### `[payments.estimated]`

`q1_federal`, `q2_federal`, `q3_federal`, `q4_federal`, `state_total`,
`local_total`.

### `[payments.prior_year]`

`agi` and `total_tax` — required for the prior-year safe-harbor test. Without
them, `withhold check` reports status `?` instead of pass/fail.

### `[payments]`

`annualized_income_fractions` — a four-element array of the fraction of the
year's income earned by each estimated-payment period. Must sum to 1.00 ± 0.01.
Only consulted when `withhold estimates --annualized` is passed.

```toml
[payments]
annualized_income_fractions = ["0.10", "0.15", "0.25", "0.50"]
```

### Cross-field validation

Validation errors are collected and reported **together**:

```
✖ Profile validation failed (2 errors)
  [taxpayer.filing_status]
    ✖ Input should be 'single', 'married_filing_jointly', ...
    → did you mean "married_filing_jointly" or "married_filing_separately"?
  [income.investment]
    ✖ Value error, qualified dividends cannot exceed ordinary dividends
      (box 1b of Form 1099-DIV is a subset of box 1a)
```

Enforced rules: qualified ≤ ordinary dividends; in-state muni ≤ total
tax-exempt interest; spouse data only with a married status; spouse W-2 wages
only with `married_filing_jointly`; unknown keys rejected (`extra=forbid`).

---

## 8. Configuration reference

`config.toml` lives at `~/.config/ouch/config.toml` (see `ouch config path`).
Override its location with `--config PATH` or `OUCH_CONFIG`.

### Precedence (highest wins)

1. Command-line flags
2. Environment variables (`OUCH_*`)
3. Scenario patch
4. Profile file
5. `config.toml`
6. Built-in defaults

`ouch config show --origin` reports where each resolved value came from.

### Keys

| Key | Default | Status |
|---|---|---|
| `general.default_profile` | `"default"` | Active |
| `general.tax_year` | `"current"` | Active — a year or the string `current` |
| `general.color` | `"auto"` | Active — `never` disables colour |
| `general.currency` | `"USD"` | Reserved, not yet consumed |
| `general.confirm_destructive` | `true` | Reserved, not yet consumed |
| `output.format` | `"table"` | Active — default for `--format` |
| `output.verbosity` | `1` | Active — floor for `-v` |
| `output.show_citations` | `true` | Active — `explain` shows authorities |
| `output.round_display` | `"dollar"` | Reserved, not yet consumed |
| `taxdata.path` | `""` | Active — your tax data directory, searched first (`OUCH_TAXDATA` overrides it). Must exist if set |
| `taxdata.strict_year` | `true` | Reserved, not yet consumed |
| `taxdata.allow_projected` | `false` | Reserved, not yet consumed |
| `privacy.encrypt_profiles` | `false` | Reserved — profile encryption is deferred |
| `privacy.redact_in_logs` | `true` | Reserved, not yet consumed |
| `ai.enabled` | `false` | Active — must be true (or `OUCH_AI_ENABLED=1`) |
| `ai.provider` | `"anthropic"` | Active — only `anthropic` is implemented |
| `ai.model` | `"claude-opus-5"` | Active |
| `ai.api_key_env` | `"ANTHROPIC_API_KEY"` | Active — the *name* of the env var; keys are never written to disk |
| `ai.require_confirmation` | `true` | Active |
| `ai.transcript_log` | `false` | Reserved — transcript logging is deferred |

Example:

```toml
[general]
default_profile = "me"
tax_year        = 2026

[output]
format    = "table"
verbosity = 2

[ai]
enabled = false
model   = "claude-opus-5"
```

### Environment variables

| Variable | Effect |
|---|---|
| `OUCH_PROFILE` | Default profile name |
| `OUCH_TAX_YEAR` | Default tax year |
| `OUCH_CONFIG` | Alternate `config.toml` path |
| `OUCH_TAXDATA` | Tax data directory — overrides `taxdata.path` |
| `OUCH_AI_ENABLED` | Enable the AI feature (`1` to turn on) |
| `OUCH_NO_COLOR` / `NO_COLOR` | Disable colour |

---

## 9. Tax data reference

### 9.1 Search order

Files are looked up in this order; the **first hit wins**, so your own file
shadows the shipped one:

1. `taxdata.path` from `config.toml`, or `$OUCH_TAXDATA`, which overrides it
2. `~/.local/share/ouch/taxdata/`
3. the files packaged with `ouch`

Layout under each root:

```
federal/<YEAR>.yaml
state/<CODE>-<YEAR>.yaml
local/<NAME>-<YEAR>.yaml
```

### 9.2 What ships

| Kind | Available |
|---|---|
| federal | 2025, 2026 |
| state | CA, CO, FL, MA, NY, PA, TX, WA (2025 and 2026) |
| local | NYC (2025 and 2026) |

Everything currently ships with `verified: false`, so every result carries a
warning. `ouch data verify` lists what still needs review.

### 9.3 Adding a jurisdiction

Drop a file into `~/.local/share/ouch/taxdata/` (or `$OUCH_TAXDATA`) and it is
discovered immediately. A minimal flat-rate locality:

```yaml
# ~/.local/share/ouch/taxdata/local/PHL-2026.yaml
meta:
  jurisdiction: PHL
  parent: PA
  year: 2026
  schema_version: 3
  verified: false
  source: ["City of Philadelphia — Dept. of Revenue, wage/NPT rates"]
  notes: "Modeled as a flat resident rate on the PA base."

regime: flat
applies_to: residents
starting_point: state_taxable
rate: 0.0375
```

```bash
ouch data list                  # PHL-2026 now appears
ouch data validate              # schema-check it
ouch estimate --locality PHL
```

### 9.4 State and local file schema

| Key | Applies to | Notes |
|---|---|---|
| `meta` | both | `jurisdiction`, `year`, `schema_version` (1–3), `verified`, `parent`, `source`, `notes`, `effective` |
| `regime` | both | `none` \| `flat` \| `progressive` |
| `rate` | flat | Required when `regime: flat` |
| `brackets` | progressive | Required when `regime: progressive`; per filing status, ascending `up_to`, last may omit `up_to` |
| `starting_point` | both | e.g. `federal_agi`, `federal_taxable`, `state_taxable` |
| `applies_to` | local | `residents` \| `workers` \| `both` |
| `modifications` | state | `additions` / `subtractions`, each with `id`, `label`, `source_field`, optional `cap`, `min_age` |
| `standard_deduction` | state | Per filing status |
| `personal_exemption` | state | `per_filer`, `per_dependent` |
| `itemized` | state | `allowed`, `decouple_from_federal`, `salt_deductible` |
| `credits` | both | `id`, `type`, `amount` or `pct_of_federal` or `table` |
| `capital_gains_treatment` | state | `ordinary` \| `preferential` \| `exempt_pct` |
| `reciprocity_states`, `credit_for_taxes_paid_other_states` | state | |

The federal file is much larger (brackets, standard deduction, itemized limits,
QBI, payroll, NIIT, AMT, capital-loss limits, the full credit suite, estimated
payment rules, Social Security taxability, special rate groups). Read the
shipped `ouch/taxdata/data/federal/2026.yaml` as the worked example, and
`ouch/taxdata/schema.py` for the authoritative field list.

A malformed data file is a hard error, never a warning. Numbers are re-parsed
as strings on load so no float ever reaches the engine.

---

## 10. Scenario reference

A scenario is a **named patch** against a base profile — never a copy — so it
stays valid as the base profile changes through the year. Scenarios live in
`~/.config/ouch/scenarios/<name>.toml`.

```toml
name        = "roth-140k"
base        = "default"
description = "Convert $140k before year end"
tags        = ["retirement"]

[patch]
"income.retirement.roth_conversion" = 140_000

[assert]
"result.marginal_rate_federal" = {lt = 0.35}
```

### Patch values

| Form | Example | Meaning |
|---|---|---|
| absolute | `75000`, `true`, `"TX"` | Set the value |
| relative | `"+10%"`, `"-5000"`, `"+2500"` | Adjust relative to the base value |
| computed | `"= income.wages.taxpayer_w2 * 0.10"` | Arithmetic over numbers and dotted paths |

Computed expressions support `+ - * /` and parentheses, and are evaluated by a
small recursive-descent parser — never `eval`. **All patch values resolve
against the *base* profile, not against each other**, so in

```toml
[patch]
"income.wages.taxpayer_w2" = "+10%"
"adjustments.sep_solo401k" = "= income.wages.taxpayer_w2 * 0.10"
```

the contribution is 10% of the *original* wages, not the raised wages.

### Assertions

`[assert]` entries are guardrails. Each is a single-op table with `lt`, `le`,
`gt`, `ge`, or `eq`. Paths address the result, e.g.
`result.marginal_rate_federal`, `result.total_tax_all_jurisdictions`. A
violation prints and exits **9**:

```
  ✖ assert result.marginal_rate_federal lt 0.3 violated (actual 0.3290)
✖ scenario assertion violated (see above)
```

### Templates

`ouch scenario new NAME --template T` scaffolds a scenario you then edit:

| Template | Patches |
|---|---|
| `roth-conversion` | `income.retirement.roth_conversion`, with a marginal-rate assertion |
| `bonus-deferral` | `income.wages.taxpayer_w2` down by $25k |
| `hsa-max` | `adjustments.hsa` |
| `bunch-charitable` | `deductions.itemized.charitable_cash` at `+100%` |
| `relocate-state` | `taxpayer.state`, `taxpayer.locality` |
| `solo401k` | `adjustments.sep_solo401k` |

Each scenario loads the tax data its *patched* profile needs, so a patch to
`taxpayer.state`, `taxpayer.locality`, `taxpayer.former_state`,
`taxpayer.residency_months`, or `tax_year` is computed with that jurisdiction's
and year's rates. `relocate-state` compares income tax only: property, sales,
insurance, and cost of living are outside `ouch`'s scope, and the template's
description says so.

---

## 11. Portfolio (lot CSV) reference

`ouch harvest import` accepts one canonical CSV. Export from your broker and
map the columns yourself — `ouch` deliberately does not integrate with
brokerages.

**Header:**

```
account,symbol,lot_id,quantity,acquired_date,cost_basis,current_price,as_of,asset_class,is_ira
```

| Column | Required | Notes |
|---|---|---|
| `account` | ✔ | Free text; used for the account count and IRA reporting |
| `symbol` | ✔ | Upper-cased on load; wash-sale matching is exact-symbol |
| `lot_id` | ✔ | Must be unique across the file |
| `quantity` | ✔ | Must be positive; fractional shares allowed |
| `acquired_date` | ✔ | `YYYY-MM-DD`; must not be after `as_of` |
| `cost_basis` | ✔ | Total basis for the lot (not per share); `$` and `,` tolerated |
| `current_price` | ✔ | Price **per share** |
| `as_of` | ✔ | Valuation date |
| `asset_class` | — | Free text |
| `is_ira` | — | `true/yes/y/1` or `false/no/n/0`/empty |

Example:

```csv
account,symbol,lot_id,quantity,acquired_date,cost_basis,current_price,as_of,asset_class,is_ira
Taxable-Brokerage,ARKG,L-0217,400,2026-05-14,32800,46.50,2026-12-12,equity,false
Taxable-Brokerage,VXUS,L-0431,410,2026-08-02,24600,39.90,2026-12-12,equity,false
Rollover-IRA,IEFA,L-9001,500,2026-12-01,24000,49.20,2026-12-12,equity,true
```

Validation is total — every bad row is reported at once, with the line number:

```
✖ lot file failed validation (2 errors) — bad.csv
  line 2: quantity must be positive
  line 3: quantity 'x' is not a number
```

The imported portfolio is stored at
`~/.local/share/ouch/portfolio/lots.csv`. Re-importing replaces it.

---

## 12. Output formats

`--format` accepts `table`, `json`, `csv`, and `markdown`, but only some
commands vary their output:

| Command | `table` / `markdown` | `json` | `csv` |
|---|---|---|---|
| `estimate` | Rich panel | Full JSON document | falls back to the panel |
| `scenario sweep` | Aligned table | falls back to the table | Machine-readable rows |
| everything else | Text | (unchanged) | (unchanged) |

`markdown` currently renders identically to `table`.

`--output PATH` writes whatever the command would have printed to `PATH`
instead of stdout, for every command and format: the `estimate` panel, JSON,
`scenario sweep --format csv`, `profile show`, `withhold check`, and the rest.
Errors still go to stderr. The file is written only when the command
succeeds, so a failed run leaves no partial file (and the exit code says why).

`--output` is refused (exit 2) when its parent directory does not exist, when
combined with `--dry-run` (which promises no disk writes), and for interactive
commands whose prompts need their context on the terminal: `init`, `agent`,
and `import pdf` without `--yes`. `ask` keeps its consent notice on the
terminal and writes the answer to the file.

### JSON document shape

```json
{
  "ouch_version": "0.1.0",
  "schema_version": 1,
  "tax_year": 2026,
  "input_fingerprint": "sha256:3c0ddc8ff2678cbf...",
  "fidelity": "exact",
  "result": { "...": "every TaxResult field, amounts as decimal strings" },
  "trace":  [ { "id": "fed.income.wages", "label": "Wages", "amount": "142000.00",
                "jurisdiction": "federal", "form_ref": "1040 line 1a",
                "authority": null, "rule": "sum of W-2 box 1 wages",
                "inputs": [], "fidelity": "exact", "warnings": [] } ],
  "warnings": [],
  "disclaimer": "Estimates only. ouch is not tax advice ..."
}
```

`input_fingerprint` is a SHA-256 of the canonicalised input, so a result can be
tied back to exactly the profile that produced it.

---

## 13. Exit codes and errors

| Code | Class | Meaning |
|---|---|---|
| 0 | — | Success |
| 1 | — | Generic failure / aborted prompt |
| 2 | `UsageError` | Invalid CLI usage |
| 3 | `ConfigError`, `ProfileError`, `SchemaError`, `ConsistencyError` | Configuration or profile problem |
| 4 | `ValidationInputError` | Input data failed validation (e.g. a lot CSV) |
| 5 | `TaxDataError`, `MissingYearError`, `DataSchemaError` | Tax data missing or malformed for the requested year |
| 6 | `PDFError` | PDF could not be read |
| 7 | `JurisdictionError` | Unsupported state or locality |
| 8 | `AgentError` | AI disabled, not installed, no key, or a provider failure |
| 9 | `ComputationError`, `ConvergenceError`, `InvariantError` | Computation guard tripped or a scenario assertion failed |

Errors print to **stderr** as `✖ message`, followed by `→ hint` when one
exists. Examples:

```
✖ no tax data for state 'OR' in 2026
  → available states: CA, CO, FL, MA, NY, PA, TX, WA — contribute a data file
```

```
✖ AI is off by default and not enabled
  → set [ai] enabled = true in config.toml, or OUCH_AI_ENABLED=1 — nothing is
    transmitted until you opt in
```

Exit code 9 is the important one: it means `ouch` detected that it was about to
emit a number it could not stand behind, and refused. It never returns a wrong
answer in its place.

---

## 14. Files on disk

On Linux (paths follow `platformdirs`, so macOS and Windows differ):

| Path | Contents |
|---|---|
| `~/.config/ouch/config.toml` | Global settings |
| `~/.config/ouch/profiles/*.toml` | Profiles (mode `0600`, dir `0700`) |
| `~/.config/ouch/profiles/*.toml.<timestamp>.bak` | Automatic backups on every write |
| `~/.config/ouch/scenarios/*.toml` | Scenarios |
| `~/.local/share/ouch/taxdata/` | Your tax data overrides |
| `~/.local/share/ouch/portfolio/lots.csv` | Imported portfolio |
| `~/.local/share/ouch/imports/<timestamp>.json` | Per-import provenance records |

Nothing else is written. There is no telemetry, no cache directory, and no
network access outside the optional AI feature.

### Provenance records

Each `import pdf` run writes one JSON file recording, per document: the file
name, detected form, detection score, owner assignment, and for every field the
box, label, target path, extracted value, raw text, extraction method,
confidence, and whether it was accepted or edited.

```json
{
  "box": "1",
  "label": "Wages, tips, other compensation",
  "target": "income.wages.taxpayer_w2",
  "value": "118400.00",
  "raw_text": "118,400.00",
  "method": "text-line",
  "confidence": 0.9,
  "accepted": true,
  "edited": false
}
```

---

## 15. Privacy and security

- **Local by default.** No network access at all unless you enable the AI
  feature. `--no-ai` guarantees it for a run.
- **Profiles are a financial portrait.** Written mode `0600` inside a `0700`
  directory.
- **No secrets on disk.** API keys are read from an environment variable whose
  *name* is configurable; `ouch` never writes a key anywhere. PDF passwords are
  used and discarded.
- **AI is opt-in twice.** It must be enabled (`ai.enabled` /
  `OUCH_AI_ENABLED=1`) *and* you must confirm the transmission notice, which
  spells out exactly what will be sent:

  ```
  ⚠ AI analysis will transmit the following to anthropic (model: claude-opus-5):
      • Your question and the computed tax result / line-item trace (amounts only)
      • Profile field values the model requests through logged tools, REDACTED as follows:
          names → removed · SSNs → never stored
          state/locality → retained (NY / NYC) (needed for analysis)
    Nothing is sent until you confirm.  Proceed? [y/N]
  ```

  Set `ai.require_confirmation = false` (or pass `--yes`) only if you have
  accepted that trade-off.
- **Redaction.** Names are stripped from the profile before an AI session is
  built, and `get_profile_field` refuses to return any identity field.
- **Auditable.** Every tool call the model makes is appended to an access log
  and the count is shown after each answer.

Not yet implemented: profile encryption at rest, transcript logging, and
keyring-based key storage. Their config keys exist but are inert — do not rely
on them.

---

## 16. Accuracy, fidelity, and known limits

### What is modeled

Federal ordinary and preferential rate stacking (including the 25% unrecaptured
§1250 and 28% collectibles groups), self-employment tax with W-2 wage-base
coordination, the SE and SE-health above-the-line deductions, iterative taxable
Social Security, standard vs itemized with SALT-cap convergence and the
high-income SALT cap phase-down (wherever the year's data file defines one), the
Schedule 1-A enhanced deduction for seniors (2025–2028), QBI (§199A)
with the wage/UBIA limitation, a simplified AMT plus the Form 8801 credit
carryforward, Additional Medicare, NIIT, the statutory capital-loss netting
order with carryforward, and the ordered credit cascade: child and dependent
care → AOTC (60/40) → LLC → saver's → CTC/ODC, then refundable AOTC, ACTC, and
EITC.

State and local jurisdictions are data-driven across `none`, `flat`, and
`progressive` regimes, with additions/subtractions, exemptions, decoupled
itemization, and part-year allocation by residency-month ratio.

### Where fidelity drops

| Area | Level | Why |
|---|---|---|
| QBI | approximate | Aggregation, REIT/PTP components, and multi-business netting are simplified |
| AMT | approximate | Only the standard-deduction and SALT addbacks are modeled; ISO bargain elements and other preferences are not |
| Part-year state | approximate | A residency-month ratio, not each state's own allocation schedule |
| Wash sales | approximate | Exact-symbol matches only; cross-issuer "substantially identical" is a legal judgment the tool will not make |
| SALT cap phase-down | exact, except | MAGI is taken as AGI: income excluded under §§911/931/933 (foreign earned income, possessions, Puerto Rico) has no profile input |
| Underpayment penalty | heuristic | A Form 2210 approximation |
| EITC | approximate | Residency/SSN/age-25-65 tests for childless claimants are not modeled |
| Saver's credit | approximate | Student and dependent exclusions, and recent-distribution offsets, are not modeled |
| Annualized installments | approximate | Your income fractions, not the statutory Schedule AI factors |
| PA state | approximate | Eight income classes modeled as a flat rate on federal AGI |
| Schedule C loss | approximate | Reduces income in full; at-risk, passive-activity, hobby-loss, and §461(l) excess-business-loss limits are not modeled |

The worst fidelity across all lines appears in the `estimate` header.

### Known defects

None known at this version. The defects listed here in earlier versions
(rtrimble13/ouch#2, #3 and #5–#14) are fixed. Report anything that is wrong
rather than merely simplified as an issue, with the profile and command that
reproduce it.

### Not implemented

OCR for scanned documents; 1099-B lot ingestion (import lots as CSV instead);
K-1 and REIT/PTP QBI components; cross-issuer substantially-identical analysis;
statutory Schedule AI annualization factors; per-state part-year schedules;
the credit for taxes paid to another state in the part-year path; profile
encryption; transcript logging; keyring key storage; on-device model endpoints;
the TUI.

### Tax data honesty

Every shipped file carries `verified: false` until each figure has been checked
against primary sources (IRS Revenue Procedures, state DOR publications). Every
result computed from unverified data carries a warning, and `ouch data verify`
lists the files needing review. Treat the shipped 2026 figures as **projected
placeholders**.

---

## 17. Troubleshooting

**`profile not found`** — run `ouch init`, or `ouch profile new NAME`, or point
at a file directly with `--profile ./path/to.toml`.

**`no federal tax data for <year>`** — only the years listed by
`ouch data list` ship. Either pass `--year` for a year that exists, or add a
data file under `$OUCH_TAXDATA`.

**`no tax data for state 'XX'`** — the hint lists what is available. Add your
own file (see [§9.3](#93-adding-a-jurisdiction)).

**My marginal rate looks wrong.** It is not read from a bracket table — it is
measured by re-running the pipeline with $1,000 more income, so it includes
NIIT, phase-outs, and state/local effects. `ouch scenario sweep` around your
income will show where the jumps are.

**`--format json` did nothing.** Only `estimate` (including
`--compare-filing-status`) emits JSON. `scenario sweep` is the one command that
honours `--format csv`.

**`taxdata.path '…' is not a directory`** — the path set in `config.toml` (or
`$OUCH_TAXDATA`, which overrides it) does not exist. The error names where it
was set. Fix the path rather than removing it, or your own data files will
not be used.

**Two W-2s summed into one person.** Owner assignment happens per document
during `import pdf`. `--yes` assigns everything to `taxpayer`; use `--owner` or
answer the prompts.

**`--annualized` errors out.** It needs
`payments.annualized_income_fractions` in the profile, four values summing to
1.0.

**Nothing happens when I ask the AI.** It is off by default. Set
`OUCH_AI_ENABLED=1` (or `[ai] enabled = true`), install `pip install
"ouch[ai]"`, and export the key named by `ai.api_key_env`.

**A result contains a `⚠ unverified` warning.** That is correct and
deliberate — the shipped data has not been independently checked. Run
`ouch data verify`.

---

## 18. Glossary

**AGI** — adjusted gross income; total income less above-the-line adjustments.

**Above-the-line adjustment** — a deduction taken before AGI, available whether
or not you itemize.

**AMT / TMT** — alternative minimum tax; the tentative minimum tax is the
parallel computation, and AMT is the excess of TMT over regular tax. Prior-year
AMT becomes a credit recoverable in later years.

**Effective rate** — total tax divided by a base (AGI, gross income, or taxable
income). `ouch` reports the first two.

**Fidelity** — how faithfully a line models the statute: `exact`,
`approximate`, or `heuristic`.

**Line item** — one node in the computation trace, with an id, amount, rule,
authority, and inputs.

**Marginal rate** — the tax on the next dollar, measured numerically.

**NIIT** — the 3.8% net investment income tax above a MAGI threshold. It is
never withheld by an employer.

**Preferential income** — qualified dividends and long-term capital gains,
taxed at 0/15/20% but **stacked on top of** ordinary income, so which band they
land in depends on your ordinary income.

**Safe harbor** — pay at least 90% of the current year's tax, or 100% (110% for
higher-income filers) of last year's, and no underpayment penalty applies even
if you owe in April.

**Scenario** — a named patch against a base profile.

**Trace** — the acyclic graph of line items behind a result.

**Wash sale (§1091)** — a loss is disallowed if you buy the same or a
substantially identical security within 30 days before or after the sale. In an
IRA the disallowance is **permanent**, because the basis adjustment has nowhere
to go.
