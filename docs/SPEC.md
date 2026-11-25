# `ouch` — Code Specification

**A CPA-grade personal tax estimation CLI**

| Field | Value |
|---|---|
| Project name | `ouch` |
| Version (spec) | 1.0.0-draft |
| Target platform | Linux (POSIX); macOS supported, Windows best-effort |
| Language | Python 3.11+ |
| License | (TBD — MIT suggested) |
| Status | Specification / pre-implementation |

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [Design Principles](#2-design-principles)
3. [Installation and Runtime Requirements](#3-installation-and-runtime-requirements)
4. [Architecture](#4-architecture)
5. [Configuration System](#5-configuration-system)
6. [Tax Data Files](#6-tax-data-files)
7. [Core Data Model](#7-core-data-model)
8. [CLI Specification](#8-cli-specification)
9. [Calculation Engine](#9-calculation-engine)
10. [Withholding Solver](#10-withholding-solver)
11. [PDF Form Ingestion](#11-pdf-form-ingestion)
12. [Scenario Analysis](#12-scenario-analysis)
13. [Tax-Loss Harvesting (Day 2)](#13-tax-loss-harvesting-day-2)
14. [AI CPA Agent](#14-ai-cpa-agent)
15. [Error Handling and Validation](#15-error-handling-and-validation)
16. [Testing and Accuracy Strategy](#16-testing-and-accuracy-strategy)
17. [Security and Privacy](#17-security-and-privacy)
18. [User Vignettes (Tutorials)](#18-user-vignettes-tutorials)
19. [Roadmap](#19-roadmap)
20. [Appendices](#20-appendices)

---

## 1. Purpose and Scope

### 1.1 What `ouch` is

`ouch` is a local-first command-line tool that estimates an individual's total
tax burden across federal, state, and local jurisdictions, and helps the user
act on that estimate — primarily by tuning payroll withholding so that the
April balance is close to zero.

The name is the user's reaction to the number.

### 1.2 Primary use cases

| # | Use case | Primary command | Milestone |
|---|---|---|---|
| UC-1 | Estimate total tax burden and effective tax rate | `ouch estimate` | M1 |
| UC-2 | Estimate correct employer withholding to avoid a year-end bill | `ouch withhold` | M1 |
| UC-3 | Assess investment portfolio for tax-loss harvesting opportunities | `ouch harvest` | M3 (Day 2) |
| UC-4 | AI CPA agent for personalized insight and guidance | `ouch ask` / `ouch agent` | M4 |

### 1.3 Secondary use cases

- Ingest PDF tax forms (W-2, 1099 family, K-1, 1098) to populate a profile.
- Compare "what-if" scenarios (Roth conversion, bonus timing, filing status,
  relocation, RSU vest, itemizing vs. standard).
- Compute quarterly estimated payments and check safe-harbor compliance.
- Report the marginal rate on the *next* dollar — the number that actually
  drives planning decisions.

### 1.4 Explicit non-goals

`ouch` **does not**:

- Prepare, generate, or electronically file a tax return.
- Produce IRS-submittable forms.
- Constitute tax advice. Every output surface carries a disclaimer (§17.4).
- Handle entity returns (1120, 1120-S, 1065). Pass-through *inputs* (K-1) are
  supported; the entity return itself is out of scope.
- Handle estate/gift (706/709), trust (1041), or nonresident alien (1040-NR)
  computations in v1.
- Maintain authoritative tax law. Rate and threshold data ship as versioned
  data files that the user or maintainers update annually and must verify
  against primary sources.

### 1.5 Accuracy posture

`ouch` targets **planning-grade accuracy**: within materiality for decision
making, with explicit disclosure of every simplification. Each calculation
module declares a `fidelity` level:

| Level | Meaning |
|---|---|
| `exact` | Implements the statutory computation in full for supported inputs. |
| `approximate` | Implements the common path; documented edge cases omitted. |
| `heuristic` | Estimate only; flagged loudly in output. |

The engine surfaces the *lowest* fidelity touched by any line in a computation
as the overall confidence of the result.

---

## 2. Design Principles

**P1 — Data is not code.**
No rate, bracket, threshold, phase-out range, standard deduction, wage base, or
credit amount appears in a `.py` file. All of it lives in versioned YAML keyed
by tax year and jurisdiction. Annual updates are data PRs, never code PRs.

**P2 — Every number is traceable.**
The engine emits a *computation trace*: an ordered list of line items, each
with a label, amount, the rule that produced it, and a citation (IRC section,
form line, or state statute). `ouch explain <line>` walks that trace. There are
no unexplained numbers.

**P3 — Pure functional core, imperative shell.**
The calculation engine is pure: `TaxInput -> TaxResult`, no I/O, no clock, no
globals, no mutation of inputs. All I/O (file reads, PDF parsing, network,
terminal) lives in the shell. This makes the core exhaustively testable and the
scenario engine trivial (just call the function again with a modified input).

**P4 — Local-first, private by default.**
No network calls occur unless the user explicitly invokes an AI command. Tax
data never leaves the machine implicitly. Profiles may be encrypted at rest.

**P5 — Fail loudly, never silently guess.**
Unsupported state? Missing bracket year? Ambiguous PDF field? The tool refuses
with a specific, actionable message rather than substituting a plausible
default. Silent defaults are how a planning tool becomes a liability.

**P6 — Intuitive interface, robust internals.**
Common actions are one command with sensible defaults. Money is `Decimal`,
never `float`. Rounding is explicit and matches IRS convention. Input
validation is total.

**P7 — Progressive disclosure.**
Default output is a one-screen summary. `-v` adds subtotals. `-vv` adds the
full line-item trace. `--json` gives the machine-readable everything.

---

## 3. Installation and Runtime Requirements

### 3.1 Runtime

- Python **3.11+** (uses `tomllib`, `Self`, exception groups, `StrEnum`).
- Linux x86_64/arm64 primary target. No compiled extensions required for the
  core; PDF and AI features are optional extras.

### 3.2 Dependencies

| Package | Purpose | Extra |
|---|---|---|
| `typer` | CLI framework, subcommands, shell completion | core |
| `rich` | Tables, trees, color, progress | core |
| `pydantic` v2 | Schema validation for config, profiles, tax data | core |
| `PyYAML` (or `ruamel.yaml`) | Tax data files | core |
| `platformdirs` | XDG-correct config/data paths | core |
| `pdfplumber` | Text/table extraction from PDFs | `[pdf]` |
| `pypdf` | AcroForm field extraction, encryption handling | `[pdf]` |
| `ocrmypdf` + `tesseract` | OCR fallback for scanned forms | `[ocr]` |
| `anthropic` (or provider SDK) | AI CPA agent | `[ai]` |
| `keyring` | API key / passphrase storage | `[ai]`, `[crypto]` |
| `cryptography` | Profile encryption at rest | `[crypto]` |
| `pandas` (optional) | Lot-level portfolio ingest for harvesting | `[harvest]` |

### 3.3 Install

`ouch` installs into a standard virtual environment with `pip`. No installer
tooling beyond `venv` and `pip` is required or assumed.

**User install:**

```bash
python3 -m venv ~/.venvs/ouch
source ~/.venvs/ouch/bin/activate

pip install --upgrade pip
pip install ouch                       # core only
pip install "ouch[pdf]"                # add PDF ingestion
pip install "ouch[pdf,ai,harvest]"     # selected extras
pip install "ouch[all]"                # everything

ouch --version
ouch init                              # interactive first-run setup
ouch completion install bash|zsh|fish
```

**Running without activating.** The console script works by absolute path, so
the venv need not be active:

```bash
~/.venvs/ouch/bin/ouch estimate
```

For convenience, either symlink the entry point onto `PATH` or alias it:

```bash
ln -s ~/.venvs/ouch/bin/ouch ~/.local/bin/ouch     # preferred
# or
echo "alias ouch='~/.venvs/ouch/bin/ouch'" >> ~/.bashrc
```

A symlink is preferred over an alias: aliases are not visible to shell
completion, `cron`, `systemd` timers, or non-interactive shells, and `ouch`
is a plausible thing to run on a schedule (e.g., a monthly
`ouch withhold check`).

**Development install:**

```bash
git clone https://github.com/<org>/ouch.git
cd ouch
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -e ".[all,dev]"            # editable + test/lint tooling

pytest                                 # full suite incl. golden fixtures
ouch data validate                     # schema-check shipped tax data
```

**Requirements files.** The project ships hash-pinned lockfiles for
reproducible installs (§17.3):

```bash
pip install -r requirements/base.txt --require-hashes
pip install -r requirements/dev.txt  --require-hashes
```

`pyproject.toml` declares the extras (`pdf`, `ocr`, `ai`, `crypto`, `harvest`,
`all`, `dev`) mapping to the dependency table in §3.2.

**Packaging notes.**

- The console entry point is declared as
  `[project.scripts] ouch = "ouch.cli.app:main"`.
- `ouch` must not assume it is the only package in its environment. It pins
  no upper bounds tighter than necessary and imports optional extras lazily,
  so that a missing extra produces a clear message rather than an
  `ImportError` at startup:

  ```
  ✖ PDF support is not installed.
    → pip install "ouch[pdf]"   (in ~/.venvs/ouch)
  ```

- Because a shared venv can be upgraded underneath the tool, `ouch --version`
  reports the versions of engaged optional dependencies alongside its own, and
  `ouch data validate` is safe to run after any upgrade.
- Python 3.11+ is enforced via `requires-python` so `pip` refuses rather than
  installing a package that will fail at import on `tomllib`.

> **Isolation still matters.** A dedicated venv (rather than `--user` or a
> system-wide install) keeps `ouch`'s pinned dependencies from colliding with
> other projects. The profile contains a complete financial portrait (§17.1),
> so keeping its runtime dependencies pinned and separate is a security
> property, not just hygiene.

### 3.4 Filesystem layout (XDG)

```
$XDG_CONFIG_HOME/ouch/            # ~/.config/ouch/
├── config.toml                   # global settings
├── profiles/
│   ├── default.toml              # the user's tax profile
│   └── spouse-selfemployed.toml
└── scenarios/
    └── roth-conversion-2026.toml

$XDG_DATA_HOME/ouch/              # ~/.local/share/ouch/
├── taxdata/
│   ├── federal/2025.yaml
│   ├── federal/2026.yaml
│   ├── state/NY-2026.yaml
│   ├── state/PA-2026.yaml
│   └── local/NYC-2026.yaml
├── imports/                      # parsed PDF artifacts + provenance
└── portfolio/
    └── lots.csv

$XDG_CACHE_HOME/ouch/             # ~/.cache/ouch/
├── ocr/                          # OCR'd PDF cache
└── agent/                        # AI session transcripts (opt-in)

$XDG_STATE_HOME/ouch/
└── ouch.log
```

---

## 4. Architecture

### 4.1 Layering

```
┌──────────────────────────────────────────────────────────────┐
│  Shell (impure)                                              │
│  cli/ · io/ · pdf/ · agent/ · render/                        │
└───────────────────────────┬──────────────────────────────────┘
                            │  TaxInput (validated, immutable)
┌───────────────────────────▼──────────────────────────────────┐
│  Core (pure)                                                 │
│  engine/  federal · state · local · credits · payments       │
│  Returns TaxResult + ComputationTrace. No I/O whatsoever.    │
└───────────────────────────┬──────────────────────────────────┘
                            │  reads
┌───────────────────────────▼──────────────────────────────────┐
│  Data (inert)                                                │
│  taxdata/*.yaml — brackets, thresholds, phase-outs, rules    │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Package layout

```
ouch/
├── __init__.py
├── __main__.py
├── cli/
│   ├── app.py                # typer root, global options
│   ├── cmd_init.py
│   ├── cmd_estimate.py
│   ├── cmd_withhold.py
│   ├── cmd_scenario.py
│   ├── cmd_import.py
│   ├── cmd_harvest.py
│   ├── cmd_agent.py
│   ├── cmd_explain.py
│   └── cmd_data.py           # taxdata validate/list/update
├── config/
│   ├── settings.py           # global config model + discovery/precedence
│   ├── profile.py            # TaxProfile model, load/save/merge
│   └── crypto.py             # optional at-rest encryption
├── model/
│   ├── money.py              # Money type (Decimal wrapper), rounding rules
│   ├── enums.py              # FilingStatus, IncomeKind, Jurisdiction...
│   ├── input.py              # TaxInput and sub-models
│   ├── result.py             # TaxResult, LineItem, ComputationTrace
│   └── portfolio.py          # Lot, Position, HarvestCandidate
├── engine/
│   ├── pipeline.py           # orchestration; the canonical ordering
│   ├── income.py             # classification and aggregation
│   ├── adjustments.py        # above-the-line
│   ├── deductions.py         # standard vs. itemized, QBI
│   ├── federal.py            # ordinary + preferential stacking
│   ├── amt.py
│   ├── setax.py              # SE tax, Additional Medicare, NIIT
│   ├── credits/
│   │   ├── base.py           # Credit protocol, phase-out primitives
│   │   ├── ctc.py  eitc.py  care.py  education.py  saver.py  ...
│   ├── state/
│   │   ├── base.py           # StateModule protocol
│   │   ├── generic_flat.py   # covers all flat-rate states via data
│   │   ├── generic_bracket.py# covers most progressive states via data
│   │   ├── none.py           # no-income-tax states
│   │   └── overrides/        # NY.py, CA.py, NJ.py — genuine oddities only
│   ├── local/
│   │   ├── base.py
│   │   └── overrides/NYC.py, PA_EIT.py, OH_RITA.py
│   ├── payments.py           # withholding, estimates, safe harbor, 2210
│   └── solver.py             # withholding + goal-seek
├── taxdata/
│   ├── loader.py             # discovery, schema validation, year resolution
│   └── schema.py             # pydantic models for every data file
├── pdf/
│   ├── detect.py             # form-type classification
│   ├── extract.py            # AcroForm → text → OCR cascade
│   ├── maps/                 # per-form box→field mapping tables
│   └── review.py             # confidence scoring + interactive confirm
├── scenario/
│   ├── model.py              # Scenario = base profile + patch set
│   ├── runner.py             # run, compare, sweep
│   └── diff.py               # structured result deltas
├── harvest/
│   ├── lots.py               # lot ingest, normalization
│   ├── washsale.py           # §1091 window analysis
│   └── ranker.py             # candidate scoring
├── agent/
│   ├── client.py             # provider-agnostic LLM interface
│   ├── tools.py              # tool/function schemas exposed to the model
│   ├── context.py            # redaction + context assembly
│   └── guardrails.py         # refusal + citation policy
└── render/
    ├── table.py  json.py  csv.py  markdown.py  trace.py
```

### 4.3 Request flow (`ouch estimate`)

```
CLI parse
   └─> load global config          (config.toml)
   └─> load profile                (profiles/<name>.toml)
   └─> apply CLI overrides         (--income, --filing-status, ...)
   └─> apply scenario patch        (--scenario <name>)
   └─> validate → TaxInput         (pydantic; fail fast, all errors at once)
   └─> resolve tax year data       (taxdata/federal/<year>.yaml + state + local)
   └─> engine.pipeline.run(input, data) ──> TaxResult + Trace   [PURE]
   └─> render (table | json | csv | markdown)
   └─> exit code
```

---

## 5. Configuration System

### 5.1 Precedence (highest wins)

```
1. Command-line flags
2. Environment variables            (OUCH_*)
3. Scenario patch file              (--scenario)
4. Profile file                     (--profile / default)
5. Global config                    (config.toml)
6. Built-in defaults
```

Every resolved value records its origin; `ouch config show --origin` prints the
source of each setting. This eliminates "why is it using that number?"

### 5.2 `config.toml`

```toml
[general]
default_profile = "default"
tax_year        = 2026          # "current" resolves via system date
currency        = "USD"
color           = "auto"        # auto | always | never
confirm_destructive = true

[output]
format       = "table"          # table | json | csv | markdown
verbosity    = 1                # 0..3
round_display = "dollar"        # dollar | cent
show_citations = true

[taxdata]
path         = "~/.local/share/ouch/taxdata"
strict_year  = true             # refuse to extrapolate a missing year
allow_projected = false         # permit inflation-projected data files

[privacy]
encrypt_profiles = false
redact_in_logs   = true

[ai]
enabled     = false
provider    = "anthropic"
model       = "claude-sonnet-5"     # configurable; see provider docs
api_key_env = "ANTHROPIC_API_KEY"   # or keyring
max_context_lines = 400
require_confirmation = true         # confirm before any data leaves machine
transcript_log = false
```

### 5.3 Profile schema (`profiles/default.toml`)

The profile is the user's tax situation. It is the single most important file
in the tool and is designed to be hand-editable.

```toml
schema_version = 2
tax_year       = 2026

[taxpayer]
name           = "A. Taxpayer"       # local only, never transmitted
filing_status  = "married_filing_jointly"
birth_date     = "1985-04-12"
blind          = false
state          = "NY"
locality       = "NYC"               # optional; keyed to local module
residency_months = 12                # part-year support

[spouse]
name       = "B. Taxpayer"
birth_date = "1986-09-30"
blind      = false

[[dependents]]
name          = "C. Taxpayer"
birth_date    = "2016-02-01"
relationship  = "child"
months_in_home = 12
student       = false
disabled      = false
qualifies_ctc = true                 # engine re-derives; this is an override

# ─────────────── INCOME ───────────────
[income.wages]
taxpayer_w2      = 185_000
spouse_w2        = 96_000
taxpayer_ss_wages = 185_000          # box 3, for SS wage base coordination
spouse_ss_wages   = 96_000

[income.investment]
interest              = 3_400
tax_exempt_interest   = 1_200
in_state_muni_interest = 900         # state add-back logic
qualified_dividends   = 12_500
ordinary_dividends    = 14_000       # inclusive of qualified
short_term_gains      = -2_000
long_term_gains       = 41_000
capital_loss_carryforward = 0
section_1250_gain     = 0            # 25% rate group
collectibles_gain     = 0            # 28% rate group

[income.business]
schedule_c_net    = 28_000
se_health_premiums = 9_600
qbi_eligible_income = 28_000
qbi_w2_wages_paid  = 0
qbi_ubia           = 0
sstb               = false           # specified service trade/business

[income.retirement]
pension                 = 0
ira_distributions       = 0
taxable_social_security = 0          # engine computes if gross provided
social_security_gross   = 0
roth_conversion         = 0

[income.other]
rental_net       = 6_200
k1_ordinary      = 0
unemployment     = 0
other_income     = 0

# ─────────────── ADJUSTMENTS ───────────────
[adjustments]
traditional_ira      = 0
hsa                  = 8_300
student_loan_interest = 0
educator_expenses    = 0
sep_solo401k         = 6_000
alimony_paid         = 0             # pre-2019 decrees only
early_withdrawal_penalty = 0

# ─────────────── DEDUCTIONS ───────────────
[deductions]
mode = "auto"                        # auto | standard | itemized

[deductions.itemized]
mortgage_interest      = 21_400
mortgage_balance       = 610_000     # for the acquisition-debt limit
state_local_income_tax = 0           # engine computes if zero
real_estate_tax        = 14_800
personal_property_tax  = 620
charitable_cash        = 9_000
charitable_noncash     = 1_500
medical_expenses       = 3_100
investment_interest    = 0

# ─────────────── PAYMENTS ───────────────
[payments.withholding]
federal_ytd    = 31_800
state_ytd      = 12_400
local_ytd      = 6_900
federal_per_period = 1_325
pay_periods_per_year = 24
periods_remaining  = 11              # engine defaults from today's date

[payments.estimated]
q1_federal = 0
q2_federal = 0
q3_federal = 0
q4_federal = 0

[payments.prior_year]
agi              = 268_000
total_tax        = 58_900            # for safe-harbor test
```

### 5.4 Environment variables

| Variable | Effect |
|---|---|
| `OUCH_CONFIG` | Path to alternate `config.toml` |
| `OUCH_PROFILE` | Profile name or path |
| `OUCH_TAXDATA` | Override tax data directory |
| `OUCH_TAX_YEAR` | Override tax year |
| `OUCH_NO_COLOR` / `NO_COLOR` | Disable color |
| `OUCH_AI_ENABLED` | `0`/`1` |
| `ANTHROPIC_API_KEY` | AI provider key (never written to disk by `ouch`) |

---

## 6. Tax Data Files

### 6.1 Rules

- One file per **jurisdiction per year**. Immutable once published.
- Every file carries `source` citations and an `effective` date range.
- Schema-validated on load (`taxdata/schema.py`); a malformed file is a hard
  error, never a warning.
- `verified: true|false` — files derived from projections rather than published
  IRS/state figures must set `verified: false`, and the engine stamps every
  result computed from them with a projection warning.

> **All figures in the examples below are illustrative placeholders.**
> Real files must be populated from primary sources (IRS Revenue Procedures,
> state DOR publications) and cited in the `source` block. Recent federal
> legislation has changed several of these parameters — including the SALT
> cap, senior additional deduction, QBI permanence, and new deductions for
> tips and overtime — so verify each figure against the published guidance for
> the year in question before trusting output.

### 6.2 Federal data file

```yaml
# taxdata/federal/2026.yaml
meta:
  jurisdiction: US
  year: 2026
  schema_version: 3
  verified: false
  source:
    - "IRS Rev. Proc. 20XX-XX"
    - "IRC §1, §63, §199A, §1411"
  notes: "Illustrative values — replace with published figures."

ordinary_brackets:
  single:
    - {up_to: 11_925,   rate: 0.10}
    - {up_to: 48_475,   rate: 0.12}
    - {up_to: 103_350,  rate: 0.22}
    - {up_to: 197_300,  rate: 0.24}
    - {up_to: 250_525,  rate: 0.32}
    - {up_to: 626_350,  rate: 0.35}
    - {up_to: null,     rate: 0.37}
  married_filing_jointly: [...]
  married_filing_separately: [...]
  head_of_household: [...]
  qualifying_surviving_spouse: [...]

preferential_brackets:          # LTCG / qualified dividends, 0/15/20
  single:
    - {up_to: 48_350,  rate: 0.00}
    - {up_to: 533_400, rate: 0.15}
    - {up_to: null,    rate: 0.20}
  married_filing_jointly: [...]

special_rate_groups:
  unrecaptured_1250: 0.25
  collectibles: 0.28

standard_deduction:
  single: 15_000
  married_filing_jointly: 30_000
  married_filing_separately: 15_000
  head_of_household: 22_500
  additional_age65: {single: 2_000, married: 1_600}
  additional_blind: {single: 2_000, married: 1_600}
  dependent_floor: 1_350
  dependent_earned_addon: 450

itemized:
  salt_cap:
    amount: 10_000
    mfs_amount: 5_000
    phasedown: null            # or, when a phase-down applies (2025 on):
    # phasedown:
    #   threshold: {amount: 500_000, mfs_amount: 250_000}   # MAGI
    #   rate: 0.30                 # cap reduced by rate × (MAGI − threshold)
    #   floor: {amount: 10_000, mfs_amount: 5_000}          # never below
  medical_agi_floor: 0.075
  mortgage_acquisition_limit: 750_000
  mortgage_grandfathered_limit: 1_000_000
  charitable_agi_limits: {cash: 0.60, noncash: 0.30, appreciated: 0.30}

qbi:
  rate: 0.20
  threshold: {single: 197_300, married_filing_jointly: 394_600}
  phase_in_range: {single: 50_000, married_filing_jointly: 100_000}
  wage_limit_pct: 0.50
  wage_ubia_alt: {wage_pct: 0.25, ubia_pct: 0.025}
  sstb_disallowed_above_phasein: true

payroll:
  social_security:
    rate_employee: 0.062
    rate_self_employed: 0.124
    wage_base: 176_100
  medicare:
    rate_employee: 0.0145
    rate_self_employed: 0.029
  additional_medicare:
    rate: 0.009
    threshold:
      single: 200_000
      married_filing_jointly: 250_000
      married_filing_separately: 125_000
  se_income_factor: 0.9235
  se_deduction_pct: 0.50

niit:
  rate: 0.038
  threshold:
    single: 200_000
    married_filing_jointly: 250_000
    married_filing_separately: 125_000

amt:
  exemption: {single: 88_100, married_filing_jointly: 137_000}
  phaseout_threshold: {single: 626_350, married_filing_jointly: 1_252_700}
  phaseout_rate: 0.25
  brackets:
    - {up_to: 239_100, rate: 0.26}
    - {up_to: null,    rate: 0.28}

capital_loss:
  annual_ordinary_offset: 3_000
  mfs_offset: 1_500

credits:
  child_tax_credit:
    amount_per_child: 2_000
    refundable_cap: 1_700
    phaseout_start: {single: 200_000, married_filing_jointly: 400_000}
    phaseout_rate_per_1000: 50
    qualifying_age_max: 16
  other_dependent_credit:
    amount: 500
  child_dependent_care:
    max_expenses: {one: 3_000, two_plus: 6_000}
    rate_table: [...]
  eitc:
    parameters_by_children: [...]
  education:
    aotc: {max: 2_500, refundable_pct: 0.40, phaseout: {...}}
    llc:  {rate: 0.20, max_expenses: 10_000, phaseout: {...}}
  savers_credit:
    tiers: [...]

estimated_payments:
  safe_harbor:
    current_year_pct: 0.90
    prior_year_pct: 1.00
    prior_year_pct_high_income: 1.10
    high_income_agi_threshold: 150_000
    high_income_agi_threshold_mfs: 75_000
  due_dates: ["04-15", "06-15", "09-15", "01-15"]
  underpayment_rate_by_quarter: [0.07, 0.07, 0.07, 0.07]

social_security_taxability:
  base_amount: {single: 25_000, married_filing_jointly: 32_000}
  adjusted_base: {single: 34_000, married_filing_jointly: 44_000}
  max_inclusion: 0.85
```

### 6.3 State data file

Three regimes are expressed entirely in data; only genuine oddities require a
Python override module.

```yaml
# taxdata/state/NY-2026.yaml
meta: {jurisdiction: NY, year: 2026, verified: false, source: ["NY DTF ..."]}

regime: progressive            # none | flat | progressive

starting_point: federal_agi    # federal_agi | federal_taxable | federal_wages | independent

modifications:
  additions:
    - {id: out_of_state_muni, label: "Non-NY municipal interest", source_field: tax_exempt_interest_out_of_state}
    - {id: state_tax_addback, label: "State tax deducted federally", source_field: itemized_salt_income}
  subtractions:
    - {id: social_security, label: "Social Security", source_field: taxable_social_security}
    - {id: pension_exclusion, label: "Pension exclusion", cap: 20_000, min_age: 59.5}
    - {id: us_treasury_interest, label: "US obligation interest", source_field: treasury_interest}

brackets:
  single: [...]
  married_filing_jointly: [...]

standard_deduction: {single: 8_000, married_filing_jointly: 16_050}
personal_exemption: {per_dependent: 1_000}

itemized:
  allowed: true
  decouple_from_federal: true
  salt_deductible: false

credits:
  - {id: household, type: nonrefundable, table: [...]}
  - {id: child_care, type: refundable, pct_of_federal: 0.20}
  - {id: earned_income, type: refundable, pct_of_federal: 0.30}

capital_gains_treatment: ordinary     # ordinary | preferential | exempt_pct
supplemental_withholding_rate: 0.1090

reciprocity_states: []
credit_for_taxes_paid_other_states: true
```

Flat-rate and no-tax states use the same schema with `regime: flat` (single
`rate` key) or `regime: none` (engine short-circuits to zero and says so).

### 6.4 Local data file

```yaml
# taxdata/local/NYC-2026.yaml
meta: {jurisdiction: NYC, parent: NY, year: 2026, verified: false}
regime: progressive
applies_to: residents            # residents | workers | both
starting_point: state_taxable
brackets:
  married_filing_jointly: [...]
credits:
  - {id: nyc_school_tax, type: refundable, amount: 63}
  - {id: nyc_household, type: nonrefundable, table: [...]}
```

Municipal wage taxes (PA EIT/LST, Ohio RITA/CCA, MD county, MI city, KY
occupational) are modeled with `regime: flat` and
`applies_to: both` plus a `work_locality` field on the profile, since
work-city and home-city rates can both apply with partial credit.

### 6.5 Data commands

```bash
ouch data list                        # jurisdictions × years available
ouch data validate                    # schema-check every file, exit 1 on error
ouch data show federal 2026 --key qbi
ouch data diff federal 2025 2026      # what changed year over year
ouch data verify                      # list unverified/projected files
```

---

## 7. Core Data Model

### 7.1 Money

```python
class Money:
    """Decimal-backed money. No float arithmetic anywhere in ouch."""
    __slots__ = ("_cents",)

    # Construction from str/int/Decimal only; float raises TypeError.
    # Arithmetic: +, -, *scalar, /scalar; comparison; abs; min/max.
    # Rounding is explicit and never implicit:
    #   .round_dollar(mode=HALF_UP)   IRS convention for return lines
    #   .round_cent(mode=HALF_EVEN)   intermediate accumulation
```

**Rounding policy.** Intermediate values retain cents. Only values that would
appear on a return line are rounded to whole dollars, using ROUND_HALF_UP, at
the point the line is emitted. Bracket computations use unrounded inputs. This
policy is asserted in tests against known returns.

### 7.2 Key enums

```python
class FilingStatus(StrEnum):
    SINGLE = "single"
    MARRIED_FILING_JOINTLY = "married_filing_jointly"
    MARRIED_FILING_SEPARATELY = "married_filing_separately"
    HEAD_OF_HOUSEHOLD = "head_of_household"
    QUALIFYING_SURVIVING_SPOUSE = "qualifying_surviving_spouse"

class RateGroup(StrEnum):
    ORDINARY = "ordinary"
    PREFERENTIAL = "preferential"      # 0/15/20
    UNRECAPTURED_1250 = "unrecap_1250" # 25%
    COLLECTIBLES = "collectibles"      # 28%

class Fidelity(StrEnum):
    EXACT = "exact"; APPROXIMATE = "approximate"; HEURISTIC = "heuristic"
```

### 7.3 `TaxInput`

Frozen pydantic model mirroring the profile schema, post-validation and
post-merge. Immutable — the scenario engine produces new instances via
`model_copy(update=...)`, never mutation.

### 7.4 `LineItem` and `ComputationTrace`

```python
@dataclass(frozen=True)
class LineItem:
    id: str                  # "fed.agi", "fed.tax.ordinary", "ny.taxable"
    label: str               # "Adjusted Gross Income"
    amount: Money
    jurisdiction: str        # "federal" | "NY" | "NYC"
    form_ref: str | None     # "1040 line 11"
    authority: str | None    # "IRC §62"
    rule: str                # human-readable derivation
    inputs: tuple[str, ...]  # ids of upstream line items — forms a DAG
    fidelity: Fidelity
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class ComputationTrace:
    items: tuple[LineItem, ...]
    def get(self, id: str) -> LineItem: ...
    def ancestors(self, id: str) -> list[LineItem]: ...   # powers `ouch explain`
```

Because each `LineItem` names its inputs, the trace is a DAG. `ouch explain
fed.tax.total` renders the subtree that produced it. This is the mechanism
behind Principle P2, and it is also what the AI agent reads (§14) — the agent
never re-derives numbers, it only narrates the trace.

### 7.5 `TaxResult`

```python
@dataclass(frozen=True)
class TaxResult:
    year: int
    input_fingerprint: str            # sha256 of canonicalized TaxInput

    # Federal
    total_income: Money
    agi: Money
    deduction_taken: Money
    deduction_mode: Literal["standard", "itemized"]
    qbi_deduction: Money
    taxable_income: Money
    tax_ordinary: Money
    tax_preferential: Money
    amt_additional: Money
    se_tax: Money
    additional_medicare: Money
    niit: Money
    credits_nonrefundable: Money
    credits_refundable: Money
    federal_total_tax: Money

    # State / local
    state: StateResult | None
    local: LocalResult | None

    # Aggregates
    total_tax_all_jurisdictions: Money
    total_payments: Money
    balance_due_or_refund: Money      # negative = refund

    effective_rate_agi: Decimal
    effective_rate_gross: Decimal
    effective_rate_taxable: Decimal
    marginal_rate_federal: Decimal
    marginal_rate_combined: Decimal   # fed + state + local + FICA/NIIT on next $
    average_rate_by_jurisdiction: dict[str, Decimal]

    safe_harbor: SafeHarborResult
    trace: ComputationTrace
    fidelity: Fidelity                # min() across all lines
    warnings: tuple[Warning, ...]
```

---

## 8. CLI Specification

### 8.1 Global options

```
ouch [GLOBAL OPTIONS] COMMAND [ARGS]

  -p, --profile NAME|PATH     Profile to use            [env OUCH_PROFILE]
  -y, --year YEAR             Tax year                  [env OUCH_TAX_YEAR]
  -c, --config PATH           Alternate config.toml
  -f, --format FMT            table|json|csv|markdown   [default: table]
  -o, --output PATH           Write to file instead of stdout
  -v, --verbose               Repeatable: -v, -vv, -vvv
  -q, --quiet                 Errors only
      --no-color              Disable ANSI color
      --dry-run               Compute but write nothing to disk
      --no-ai                 Hard-disable all network/AI paths this run
      --explain               Append computation trace to output
      --version / --help
```

### 8.2 Command tree

```
ouch
├── init                      Interactive first-run setup
├── estimate                  UC-1: total burden + effective rate
├── withhold                  UC-2: withholding recommendation
│   ├── check                   Are you on track? Safe-harbor status
│   ├── solve                   Per-paycheck amount to hit a target
│   └── w4                      Translate result into W-4 line entries
├── scenario                  UC-3 support: what-if analysis
│   ├── new / list / show / delete
│   ├── run NAME
│   ├── compare A B [C...]
│   └── sweep --var PATH --range LO:HI:STEP
├── import                    PDF ingestion
│   ├── pdf FILE...
│   ├── review                  Confirm low-confidence fields
│   └── status
├── harvest                   Day 2: tax-loss harvesting
│   ├── scan
│   ├── simulate --sell LOT_ID...
│   └── washsale-check
├── ask "question"            One-shot AI CPA question
├── agent                     Interactive AI CPA session
├── explain LINE_ID           Walk the derivation of any line
├── profile                   show | edit | validate | new | copy | encrypt
├── data                      list | validate | show | diff | verify
├── config                    show | set | path
└── completion                install | show
```

### 8.3 `ouch estimate` — UC-1

```
ouch estimate [OPTIONS]

  --federal-only              Skip state and local
  --state CODE                Override profile state
  --locality NAME             Override profile locality
  --compare-filing-status     Run all legal statuses side by side
  --itemize / --standard      Force deduction mode (default: auto, take larger)
  --marginal                  Show marginal rate on next $1 / $1,000 / $10,000
  --breakdown                 Full line-item table by jurisdiction
  --set PATH=VALUE            Ad-hoc override, repeatable
                              e.g. --set income.wages.taxpayer_w2=200000
```

**Default output (verbosity 1):**

```
╭─ ouch · Tax Year 2026 · Married Filing Jointly · NY / NYC ─────────────╮
│                                                                        │
│  Total income                                    $  372,100            │
│  Adjusted gross income                           $  356,240            │
│  Deduction (itemized)                            $ ( 46,800)           │
│  QBI deduction                                   $ (  4,180)           │
│  Taxable income                                  $  305,260            │
│                                                                        │
│  Federal income tax                              $   58,412            │
│    ordinary                                      $   47,180            │
│    preferential (QD + LTCG)                      $   11,232            │
│  Self-employment tax                             $    3,957            │
│  Net investment income tax                       $    2,014            │
│  Credits                                         $ (  2,000)           │
│  ──────────────────────────────────────────────────────────            │
│  Federal total                                   $   62,383            │
│  New York State                                  $   20,118            │
│  New York City                                   $   11,044            │
│  ══════════════════════════════════════════════════════════            │
│  TOTAL TAX BURDEN                                $   93,545            │
│                                                                        │
│  Effective rate (of AGI)                             26.26%            │
│  Effective rate (incl. payroll tax)                  29.41%            │
│  Marginal rate on next dollar                        45.85%            │
│                                                                        │
│  Withheld + paid to date                         $   51,100            │
│  ▸ PROJECTED BALANCE DUE                         $   42,445            │
│                                                                        │
│  ⚠  Safe harbor NOT met — see `ouch withhold check`                    │
│  ⚠  Tax data for 2026 is unverified (projected)                        │
╰────────────────────────────────────────────────────────────────────────╯
  Estimate only — not tax advice. Run `ouch --explain estimate` for detail.
```

Numbers above are illustrative of *format*, not of any real computation.

### 8.4 Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error |
| 2 | Invalid CLI usage |
| 3 | Configuration or profile error |
| 4 | Validation error in input data |
| 5 | Tax data missing or malformed for requested year/jurisdiction |
| 6 | PDF parse failure (unreadable, encrypted, unrecognized) |
| 7 | Unsupported jurisdiction |
| 8 | AI provider error (network, auth, rate limit) |
| 9 | Computation guard tripped (internal invariant violated) |
| 10 | Result computed but fidelity below `--min-fidelity` |

---

## 9. Calculation Engine

### 9.1 Canonical pipeline order

Order matters enormously. Several steps are circular in the statute (state tax
deduction ↔ federal itemized ↔ state starting point) and are resolved by
iteration, not by guessing. The pipeline is:

```
 1. Classify and aggregate income by rate group
 2. Compute self-employment tax                          → SE deduction
 3. Above-the-line adjustments (incl. ½ SE tax, SE health)
 4. Taxable Social Security (iterative — depends on AGI, feeds AGI)
 5. Adjusted Gross Income
 6. Deduction: standard vs. itemized (needs state tax estimate → §9.9 loop)
 7. QBI deduction (needs taxable income before QBI)
 8. Taxable income
 9. Federal tax: preferential stacking algorithm (§9.4)
10. AMT parallel computation; add excess over regular tax
11. Additional Medicare tax; Net Investment Income Tax
12. Nonrefundable credits (ordered; limited to tax liability)
13. Refundable credits
14. Federal total tax
15. State: starting point → modifications → deduction → tax → credits
16. Local: starting point → tax → credits
17. Payments, safe harbor, balance due
18. Rate metrics (effective, marginal, by jurisdiction)
```

Each step appends `LineItem`s to the trace. The pipeline asserts invariants
between steps (§15.3) and raises exit-code 9 rather than emitting a wrong
number.

### 9.2 Income classification

Income is bucketed by rate group at ingest, and the buckets never merge:

| Bucket | Contents |
|---|---|
| `ordinary_earned` | W-2 wages, SE net income, tips |
| `ordinary_unearned` | Interest, non-qualified dividends, pension, IRA, rents, ST gains, unemployment, Roth conversion |
| `preferential` | Qualified dividends, net LTCG |
| `unrecap_1250` | Unrecaptured §1250 gain (25% group) |
| `collectibles` | Collectibles gain (28% group) |
| `excluded` | Municipal interest, non-taxable SS portion, HSA distributions |

**Capital gain netting** follows the statutory order: net short-term against
short-term, long-term against long-term, then cross-net; apply the annual
ordinary-income offset limit; carry the remainder forward with character
preserved (ST/LT). Character preservation is a common source of error and is
unit-tested independently.

### 9.3 Taxable Social Security (iterative)

Taxable SS depends on "combined income" (AGI excluding SS + tax-exempt interest
+ ½ SS), but taxable SS is itself a component of AGI. Implement as a fixed-point
loop:

```
ss_taxable = 0
repeat up to 8 times:
    provisional = agi_ex_ss + tax_exempt_interest + 0.5 * ss_gross
    new_taxable = tiered_inclusion(provisional, base, adjusted_base, cap=0.85)
    if |new_taxable - ss_taxable| < $0.01: break
    ss_taxable = new_taxable
else: raise ConvergenceError  → exit 9
```

### 9.4 Preferential rate stacking — the critical algorithm

This is the single most common defect in amateur tax calculators. Qualified
dividends and long-term capital gains are **not** taxed at a flat rate; they
sit on top of ordinary income, and the bracket that applies is determined by
*total* taxable income. Additionally, ordinary income is taxed as if the
preferential income did not exist.

```python
def federal_income_tax(taxable_income, pref_income, brackets, pref_brackets,
                       rate_group_amounts) -> tuple[Money, list[LineItem]]:
    """
    taxable_income : total taxable income (ordinary + preferential)
    pref_income    : qualified dividends + net LTCG (already netted, >= 0)
    """
    ordinary_taxable = max(taxable_income - pref_income, 0)

    # 1. Ordinary income taxed through ordinary brackets, alone.
    tax = apply_brackets(ordinary_taxable, brackets)

    # 2. Preferential income fills the preferential brackets, but starting
    #    from the top of ordinary income — NOT from zero.
    remaining = pref_income
    floor = ordinary_taxable
    for band in pref_brackets:                     # ascending
        band_top = band.up_to or INFINITY
        if band_top <= floor:
            continue                               # band fully consumed
        amount_in_band = min(remaining, band_top - floor)
        if amount_in_band > 0:
            tax += amount_in_band * band.rate
            remaining -= amount_in_band
            floor += amount_in_band
        if remaining == 0:
            break

    # 3. 25% and 28% groups are separate stacks with their own ceilings;
    #    each is taxed at the LESSER of its statutory rate and the rate that
    #    would apply if it were ordinary income.
    tax += special_rate_groups(rate_group_amounts, ordinary_taxable, brackets)
    return tax
```

**Required test cases** (each with a hand-computed expected value):

1. All ordinary, no preferential.
2. All preferential, zero ordinary (0% band fully used).
3. Preferential straddling the 0%/15% boundary.
4. Preferential straddling 15%/20%.
5. Ordinary income alone exceeding the top preferential threshold.
6. Preferential income that pushes total income across a NIIT threshold.
7. Capital loss reducing preferential to zero with ordinary offset applied.
8. Presence of §1250 and collectibles groups simultaneously.

### 9.5 Deduction determination

```
standard = base[status]
         + additional_age65 * count(age >= 65 among taxpayer, spouse)
         + additional_blind * count(blind)
         (+ any statutory add-ons defined in the data file for the year)

itemized = medical_over_floor
         + min(SALT_total, salt_cap)          # SALT = income-or-sales + RE + PP;
                                               # cap after any phase-down (below)
         + qualified_mortgage_interest         # limited by acquisition debt
         + charitable (subject to AGI % limits by donation type)
         + investment_interest (limited to net investment income)
         + other

mode = "itemized" if itemized > standard else "standard"     # unless forced
```

The engine reports the *crossover*: how much additional deductible spending
would make itemizing worthwhile, or how much itemizing beats the standard
deduction by. That number drives real decisions (bunching charitable gifts).

**SALT cap phase-down** (IRC §164(b)(7), 2025 onward): when the data file
carries `salt_cap.phasedown`,
`salt_cap = max(floor, cap − rate × max(0, MAGI − threshold))`, with the
married-filing-separately amounts for MFS. MAGI is AGI plus income excluded
under §§911, 931 and 933; ouch has no inputs for those exclusions, so v1 uses
AGI. AGI does not depend on itemized deductions, so the phase-down adds no
circularity to the §9.9 SALT loop. Inside the band each dollar of MAGI also
removes `rate` dollars of deduction, which `scenario sweep` reports as a cliff.

**Mortgage interest limitation**: deductible portion =
`interest × min(1, acquisition_limit / average_balance)`, using the
grandfathered limit if the profile flags pre-cutoff debt.

### 9.6 QBI (§199A)

```
tentative      = 0.20 × qualified_business_income
overall_limit  = 0.20 × (taxable_income_before_QBI − net_capital_gain)
                 # net_capital_gain = preferential income

if taxable_income <= threshold:
    deduction = min(tentative, overall_limit)

elif taxable_income >= threshold + phase_in_range:
    if sstb: deduction = 0
    else:
        wage_cap  = max(0.50 × W2_wages,
                        0.25 × W2_wages + 0.025 × UBIA)
        deduction = min(tentative, wage_cap, overall_limit)

else:  # inside the phase-in range
    pct = (taxable_income − threshold) / phase_in_range
    if sstb: reduce QBI, W2, and UBIA by pct before applying the above
    apply the wage limitation only to the `pct` fraction of the excess
    deduction = min(result, overall_limit)
```

Fidelity: `approximate` — aggregation elections across multiple businesses and
REIT/PTP components are v2. The engine warns when more than one business is
present.

### 9.7 Self-employment tax, Additional Medicare, NIIT

```
se_base       = se_net_income × se_income_factor            # 92.35%
ss_available  = max(0, wage_base − W2_social_security_wages) # coordination!
ss_portion    = min(se_base, ss_available) × se_ss_rate
medicare      = se_base × se_medicare_rate
se_tax        = ss_portion + medicare
se_deduction  = se_tax × 0.50                # above-the-line

addl_medicare = max(0, (W2_medicare_wages + se_base) − threshold[status]) × 0.009
                # note: employer withholds only above $200k on a single job;
                # MFJ households routinely owe this at filing. Flag it.

nii  = interest + dividends + net_cap_gains + passive_rents + royalties
       − allocable investment expenses
niit = min(nii, max(0, MAGI − threshold[status])) × 0.038
```

The W-2/SE Social Security coordination is mandatory: a wage earner with a side
business must not pay the SS portion twice above the wage base. This is a
common error and is explicitly tested.

### 9.8 Credits engine

Every credit implements a common protocol so phase-outs are uniform and
testable:

```python
class Credit(Protocol):
    id: str
    refundable: bool
    ordering: int                 # statutory application order
    def eligible(self, ti: TaxInput) -> bool: ...
    def gross_amount(self, ti: TaxInput, r: PartialResult) -> Money: ...
    def phaseout(self, amount: Money, ti: TaxInput, r: PartialResult) -> Money: ...
```

Phase-out primitives provided in `credits/base.py`:

| Primitive | Form |
|---|---|
| `cliff(threshold)` | Full amount below, zero above |
| `linear(start, end)` | Straight-line reduction across a range |
| `stepped(start, per_increment, increment)` | e.g. $50 per $1,000 of excess (CTC) |
| `tiered(table)` | Rate table by AGI band (Saver's, care credit) |
| `plateau(phase_in, plateau, phase_out)` | EITC's trapezoid |

Nonrefundable credits are applied in statutory order and clamped to remaining
liability; the residue of each is reported so the user can see what was lost.
Refundable credits are applied after and may drive the balance negative.

### 9.9 State and local computation

```
state_starting = resolve(starting_point, federal_result)
state_agi      = state_starting + Σ additions − Σ subtractions
state_deduction= max(state_standard, state_itemized) per state rules
state_taxable  = max(0, state_agi − state_deduction − exemptions)
state_tax      = apply(regime, state_taxable)
                 + preferential handling if the state decouples
state_tax     -= credits (incl. credit for taxes paid to other states)

local_starting = resolve(local.starting_point, state_result)
local_tax      = apply(local.regime, local_starting) − local_credits
```

**The circular dependency.** Federal itemized deductions include state and
local income tax; state taxable income sometimes starts from federal taxable
income. Resolve by fixed-point iteration:

```
state_tax_estimate = prior_year_state_tax or 0
for i in range(MAX_ITER = 6):
    federal = compute_federal(input, salt_income_component=state_tax_estimate)
    state   = compute_state(input, federal)
    if |state.tax − state_tax_estimate| < $1.00: break
    state_tax_estimate = state.tax
else:
    raise ConvergenceError            # exit 9; never emit an unconverged number
```

When the SALT cap binds (common in high-tax states), the loop converges on the
first iteration because the deduction is already at the cap — detect and
short-circuit.

**Part-year and multi-state** (v1.5): allocate income by residency period and
apply the credit for taxes paid to other jurisdictions. v1 supports full-year
residency only and refuses otherwise with exit code 7.

**Locality resolution**: `locality` on the profile maps to a local data file.
If the state has local taxes but the user supplied no locality, `ouch` warns
rather than silently computing zero — a zero local tax in Ohio or Pennsylvania
is almost certainly wrong.

### 9.10 Rate metrics

| Metric | Definition |
|---|---|
| Effective (AGI) | total income tax ÷ AGI |
| Effective (gross) | total income tax ÷ total income including excluded |
| Effective (all-in) | (income tax + employee payroll + SE tax) ÷ total income |
| Marginal (federal) | Δ federal tax from adding $1,000 ÷ 1,000 |
| Marginal (combined) | Δ (federal + state + local + NIIT + Medicare) ÷ 1,000 |
| Marginal (by source) | Same, computed separately for wage, LTCG, and SE dollars |

Marginal rates are computed **numerically** — re-run the pipeline with a
perturbed input — not analytically. This automatically captures phase-out
cliffs, which is exactly what makes marginal rates interesting (a household in
a CTC phase-out can face a marginal rate several points above its statutory
bracket). The perturbation size is configurable; the default reports both the
$1,000 and $10,000 marginal rate when they differ by more than 1 point,
because a divergence means a cliff sits between them.

---

## 10. Withholding Solver

This is UC-2 and deserves first-class treatment: it is the use case that
actually changes the user's cash flow.

### 10.1 `ouch withhold check`

Reports current trajectory:

```
Projected total tax                     $ 93,545
Withheld to date (all jurisdictions)    $ 51,100
Projected additional withholding        $ 18,975     (11 periods × $1,725)
Projected total payments                $ 70,075
──────────────────────────────────────────────────
Projected balance due                   $ 23,470

Safe harbor analysis (federal):
  90% of current-year tax               $ 56,145
  100% of prior-year tax                $ 58,900
  110% of prior-year tax (AGI > $150k)  $ 64,790   ← your requirement
  Projected federal payments            $ 46,300
  Status: ✗ SHORT by $18,490
  Estimated underpayment penalty        $    612    (Form 2210 approximation)
```

### 10.2 `ouch withhold solve`

Goal-seek: find the per-paycheck federal (and state/local) withholding that
produces a target outcome.

```
ouch withhold solve [OPTIONS]

  --target zero               Balance due of $0                    [default]
  --target refund:AMOUNT      End with a specific refund
  --target owe:AMOUNT         End owing a specific amount (keep the float)
  --target safe-harbor        Minimum withholding to avoid penalty only
  --periods-remaining N       Override auto-derived count
  --jurisdiction fed|state|local|all
  --even                      Spread evenly over remaining periods  [default]
  --catch-up                  Front-load into the next N periods
  --w4                        Also emit W-4 line entries
```

Algorithm: bisection on the withholding variable over the pure pipeline.
Because the pipeline is pure and monotonic in withholding, bisection converges
in ~20 iterations to the cent. No analytic inversion is attempted — phase-outs
and the safe-harbor floor make the function piecewise.

```python
def solve_withholding(base: TaxInput, target: Money, periods: int) -> Money:
    lo, hi = Money(0), estimate_upper_bound(base)
    for _ in range(MAX_ITER := 64):
        mid = (lo + hi) / 2
        result = pipeline.run(base.with_withholding_per_period(mid, periods))
        delta = result.balance_due_or_refund - target
        if abs(delta) <= Money("0.01"):
            return mid
        lo, hi = (mid, hi) if delta > 0 else (lo, mid)
    raise ConvergenceError
```

### 10.3 `ouch withhold w4`

Withholding tables and the W-4 are not a simple "withhold $X" instruction, so
the tool translates its answer into the two levers the form actually offers:

- **Step 4(c) — extra withholding per pay period.** The primary lever.
  Directly expressible from the solver output.
- **Step 4(a)/4(b) — other income / deductions.** Used when the required
  adjustment is large enough that 4(c) alone would look anomalous, or when the
  user has non-wage income they'd rather cover through payroll.
- **Step 2 — multiple jobs.** Detected automatically when both spouses have
  W-2 income, with a warning that under-withholding in dual-earner households
  is the single most common cause of a surprise April bill.

Output includes a per-employer breakdown when both spouses have wages, since
only one employer can act on a given W-4.

> The tool does not fill out or submit a W-4. It prints the values for the user
> to enter with their employer.

### 10.4 Quarterly estimates

For non-wage income, `ouch withhold estimates` produces a four-payment schedule
with due dates, and supports the **annualized income installment method** for
lumpy income (a Q4 RSU vest should not create a Q1 underpayment penalty).
Fidelity: `approximate` for the annualized method in v1.

---

## 11. PDF Form Ingestion

### 11.1 Objective

Reduce first-run friction from "type 40 numbers" to "drop a folder of PDFs."
Ingestion is **assistive, never authoritative**: every extracted value is
presented for confirmation before it is written to a profile.

### 11.2 Supported forms (v1)

| Form | Fields extracted | Priority |
|---|---|---|
| W-2 | Boxes 1–6, 12 (coded), 16, 17, 18, 19, 20 | P0 |
| 1099-INT | Boxes 1, 3, 8, 9, 13 | P0 |
| 1099-DIV | Boxes 1a, 1b, 2a, 2b, 2d, 7, 12 | P0 |
| 1099-B | Proceeds, basis, ST/LT, wash-sale disallowed, lot detail | P0 |
| 1099-NEC / MISC | Box 1 / boxes 1–3 | P1 |
| 1099-R | Boxes 1, 2a, 4, 7, 12–14 | P1 |
| SSA-1099 | Net benefits, withholding | P1 |
| 1098 | Mortgage interest, points, outstanding principal | P1 |
| 1098-T / 1098-E | Qualified expenses / student loan interest | P2 |
| K-1 (1065 / 1120-S) | Boxes 1, 2, 5–9, 13, 17/20 codes | P2 |
| 1040 (prior year) | AGI, total tax — for safe-harbor baseline | P0 |
| Consolidated broker statement | Multi-form composite | P1 |

### 11.3 Extraction cascade

```
1. AcroForm fields          → pypdf, if the PDF has a fillable form layer
2. Positional text          → pdfplumber, with per-issuer layout templates
3. Label-anchored regex     → find "Box 1" / "Wages, tips" and read right/below
4. Table extraction         → pdfplumber tables (broker statements)
5. OCR                      → ocrmypdf + tesseract, scanned documents only
6. Manual                   → prompt the user for the field
```

Each stage yields a confidence score. The cascade stops at the first stage that
produces a value above `confidence_threshold` (default 0.85).

### 11.4 Form detection

`pdf/detect.py` classifies by scoring text against per-form signature sets
(OMB control number, form title, characteristic box labels). Ambiguous
classification prompts the user rather than guessing. Multi-form PDFs
(consolidated 1099s) are split into logical sections first.

### 11.5 Mapping tables

Mappings live in data, not code:

```yaml
# pdf/maps/w2.yaml
form: W-2
signatures: ["Wage and Tax Statement", "OMB No. 1545-0008"]
fields:
  - box: "1"
    labels: ["Wages, tips, other compensation"]
    target: income.wages.{owner}_w2
    type: money
    validate: {min: 0, max: 100_000_000}
  - box: "2"
    labels: ["Federal income tax withheld"]
    target: payments.withholding.federal_ytd
    aggregate: sum          # multiple W-2s add together
  - box: "3"
    labels: ["Social security wages"]
    target: income.wages.{owner}_ss_wages
  - box: "12"
    type: coded
    codes:
      D:  adjustments.elective_deferral_401k
      W:  adjustments.hsa_employer
      DD: informational.employer_health_cost
```

### 11.6 Review workflow

```bash
ouch import pdf ~/tax-docs/2026/*.pdf
```

```
Scanning 7 documents...

  ✔ W-2_Acme.pdf              W-2          9 fields    confidence 0.98
  ✔ 1099-INT_BigBank.pdf      1099-INT     3 fields    confidence 0.96
  ⚠ 1099-B_Broker.pdf         1099-B      41 lots      confidence 0.71
  ✔ 1098_Mortgage.pdf         1098         3 fields    confidence 0.94
  ✖ scan_003.pdf              unknown      —           needs OCR or manual
  …

3 fields need review.

  1099-B · Box 1e (cost basis), lot #17
    Extracted: $12,4O0.00        ← 'O' where a zero is expected
    Context:   "…acquired 03/14/2024  12,4O0.00  14,220.00…"
    [a]ccept  [e]dit  [s]kip  [v]iew page  ?
```

Nothing is written until review completes. Then:

```
Writing to profile 'default' (backup: default.toml.2026-07-24T14:22:05.bak)
  income.wages.taxpayer_w2        185,000  (was 0)          [W-2_Acme.pdf]
  payments.withholding.federal_ytd 31,800  (was 0)          [W-2_Acme.pdf]
  ...
Provenance recorded in ~/.local/share/ouch/imports/2026-07-24T14-22-05.json
```

### 11.7 Provenance

Every imported value records source file, page, extraction method, confidence,
and timestamp. `ouch profile show --provenance` displays the origin of each
field, and `ouch import status` lists what has and has not been imported for
the year — a checklist against the user's expected document set.

### 11.8 Constraints

- Encrypted PDFs: prompt for a password; never store it.
- Imported PDFs are **not** copied into `ouch` storage by default.
- Extraction never sends document content to a network service, including the
  AI provider, unless the user explicitly runs an AI command and confirms.

---

## 12. Scenario Analysis

### 12.1 Model

A scenario is a **named patch** against a base profile — never a full copy.
This keeps scenarios valid as the base profile is updated through the year.

```toml
# scenarios/roth-conversion-2026.toml
name        = "Roth conversion $75k"
base        = "default"
description = "Convert $75k from traditional IRA before year end"
tags        = ["retirement", "2026"]

[patch]
"income.retirement.roth_conversion" = 75_000

[assert]                       # optional guardrails; fail the run if violated
"result.marginal_rate_federal" = {lt = 0.35}
```

Patch paths use dotted profile addresses. Values may be absolute
(`= 75_000`), relative (`= "+10%"`, `= "-5000"`), or computed
(`= "= income.wages.taxpayer_w2 * 0.10"`).

### 12.2 Commands

```bash
ouch scenario new roth --set income.retirement.roth_conversion=75000
ouch scenario run roth
ouch scenario compare baseline roth roth-150k
ouch scenario sweep --var income.retirement.roth_conversion \
                    --range 0:200000:10000 \
                    --metric marginal_rate_combined,total_tax_all_jurisdictions \
                    --format csv
```

### 12.3 Comparison output

```
                              Baseline      Roth $75k        Δ
─────────────────────────────────────────────────────────────────
AGI                          $ 356,240     $ 431,240   +$ 75,000
Taxable income               $ 305,260     $ 380,260   +$ 75,000
Federal income tax           $  58,412     $  85,162   +$ 26,750
NIIT                         $   2,014     $   4,864   +$  2,850
New York State               $  20,118     $  25,893   +$  5,775
New York City                $  11,044     $  13,819   +$  2,775
─────────────────────────────────────────────────────────────────
TOTAL TAX                    $  93,545     $ 131,695   +$ 38,150
Effective rate                  26.26%        30.54%     +4.28pp
Marginal rate (next $)          45.85%        49.71%     +3.86pp

Marginal cost of the conversion: 50.87% of the converted amount.

⚠ Crosses the NIIT threshold — $2,850 of the increase is NIIT on
  investment income that was previously below the threshold.
⚠ Pushes preferential income from the 15% band into the 20% band.
```

The "marginal cost of the change" line — Δtax ÷ Δinput — is the number that
answers the user's actual question, and it is always shown.

### 12.4 Sweeps

Sweeps evaluate a variable across a range and emit a table or CSV, revealing
cliffs that a single-point estimate hides. Because the core is pure, sweeps
parallelize with `multiprocessing` and cache on input fingerprint.

Detected cliffs (any single step producing a marginal rate spike above a
configurable threshold) are called out explicitly:

```
⚠ Cliff detected at $198,000–$200,000: marginal rate 62.4%
  Cause: Child Tax Credit phase-out + IRMAA-adjacent threshold + NIIT onset
```

### 12.5 Built-in scenario templates

`ouch scenario new --template NAME` scaffolds common analyses:
`roth-conversion`, `bonus-deferral`, `filing-status-comparison`,
`relocate-state`, `bunch-charitable`, `rsu-vest`, `retire-early`,
`sell-home`, `529-vs-taxable`, `mega-backdoor`, `hsa-max`, `qcd`.

---

## 13. Tax-Loss Harvesting (Day 2)

### 13.1 Scope

Identify positions with unrealized losses whose realization would reduce
current-year tax, quantify the benefit, and flag wash-sale risk. This is
**analysis, not execution** — `ouch` never connects to a brokerage to trade.

### 13.2 Lot ingestion

```bash
ouch harvest import lots.csv                     # canonical schema
ouch harvest import --from-1099b broker.pdf      # reuse the PDF pipeline
ouch harvest import --format schwab positions.csv
```

Canonical lot schema:

```csv
account,symbol,lot_id,quantity,acquired_date,cost_basis,current_price,as_of,asset_class,is_ira
```

Lots in retirement accounts are marked `is_ira` and excluded from harvesting
with an explanatory note (a loss there has no tax value).

### 13.3 Wash-sale analysis (§1091)

```
For each candidate sale lot L of security S on hypothetical date D:
    window = [D − 30 days, D + 30 days]
    conflicts = purchases of S or substantially identical securities
                in ANY account, including:
                  - dividend reinvestments        (the usual culprit)
                  - automatic/recurring buys
                  - IRA and Roth purchases        (permanently disallowed loss)
                  - spouse's accounts             (attributed)
    if conflicts: compute disallowed portion pro-rata by shares repurchased
```

"Substantially identical" is a legal judgment the tool will not make
definitively. `ouch` flags exact-CUSIP matches as **certain**, and same-index
funds from different issuers as **review required**, with the reasoning shown.
Fidelity: `approximate`, and the output says so.

### 13.4 Benefit quantification

The benefit of harvesting is *not* `loss × marginal_rate`. The engine computes
it correctly by re-running the full pipeline:

```
benefit = tax(baseline) − tax(baseline with realized loss)
```

This automatically accounts for:

- The annual ordinary-income offset limit once capital losses exceed gains.
- The character-matching rule (ST losses offset ST gains first — and ST gains
  are taxed at ordinary rates, so ST losses are worth more).
- NIIT reduction.
- State treatment (some states do not follow the federal loss limitation).
- **Basis reduction**: the tool reports the deferred cost — harvesting lowers
  future basis, so the benefit is largely a *deferral*, valued by comparing
  the tax saved now against the tax created later at the user's assumed future
  rate (`--future-rate`, default = current marginal LTCG rate).

### 13.5 Ranking and output

```
ouch harvest scan --as-of 2026-12-15 --min-benefit 250
```

```
Harvest candidates · 2026 · marginal ST 45.85% / LT 28.85%

  #  Symbol  Lot      Held    Unrealized    Character   Tax benefit   Wash risk
  1  VXUS    L-0431   4 mo    $ (8,240)     short       $  3,777      ⚠ DRIP 11/28
  2  ARKK    L-0102   2.1 yr  $ (6,100)     long        $  1,760      ✔ clear
  3  BND     L-0388   8 mo    $ (2,950)     short       $  1,352      ✔ clear
  ────────────────────────────────────────────────────────────────────────────
  Realizing #2 and #3 together:
    Capital loss realized                    $  9,050
    Offsets existing realized gains          $  9,050
    Current-year tax reduction               $  3,112
    Deferred tax cost (basis reduction)      $  2,610  @ assumed 28.85%
    Net present benefit @ 5% / 10 yr         $    608
```

The deferred-cost line is included deliberately: harvesting is oversold, and a
CPA-grade tool should show the user both sides.

### 13.6 Additional checks

- **Holding-period alerts**: lots approaching the one-year long-term boundary,
  where waiting materially changes the rate.
- **Gain harvesting**: households in the 0% preferential band may benefit from
  *realizing* gains — the tool surfaces the room remaining in the 0% band.
- **Loss carryforward tracking** across years, with character preserved.
- **Charitable substitution**: appreciated lots better donated than sold.

---

## 14. AI CPA Agent

### 14.1 Design stance

The agent is a **narrator and advisor over deterministic output** — never a
calculator. Its cardinal rule:

> **The model never produces a number that the engine did not compute.**

Every figure in an agent response must trace to a `LineItem` id. The agent's
value is in interpretation, prioritization, and identifying planning
opportunities the user did not know to ask about — not arithmetic, which the
pure engine already does exactly and reproducibly.

### 14.2 Architecture

```
User question
   └─> context assembly     (redact → select relevant trace lines → serialize)
   └─> provider call        with tool definitions (§14.4)
   └─> tool-use loop        model calls ouch functions; engine returns real data
   └─> guardrails           citation check, number check, scope check
   └─> render               answer + cited line ids + disclaimer
```

`agent/client.py` defines a provider-agnostic interface:

```python
class LLMClient(Protocol):
    def complete(self, system: str, messages: list[Message],
                 tools: list[ToolSpec]) -> Response: ...
```

with an Anthropic implementation as the reference backend. Model id, provider,
and endpoint are configuration, not code — see `[ai]` in §5.2. Consult the
provider's current documentation for available model identifiers and pricing
(for Anthropic: <https://docs.claude.com/en/api/overview>); do not hardcode a
model string in source.

### 14.3 Commands

```bash
ouch ask "why did my effective rate jump this year?"
ouch ask "what's the marginal cost of a $50k Roth conversion?"
ouch agent                          # interactive REPL session
ouch agent --review                 # proactive review of the whole profile
```

### 14.4 Tools exposed to the model

The model cannot see raw profile data by default; it must request it through
tools, which produces an auditable trail of exactly what was accessed.

| Tool | Purpose |
|---|---|
| `get_result_summary()` | Top-level `TaxResult` fields |
| `get_line_item(id)` | One trace line with its authority and rule |
| `get_trace_subtree(id)` | Derivation of a line |
| `run_scenario(patch)` | Execute a what-if through the real engine |
| `sweep(variable, range)` | Marginal analysis across a range |
| `check_safe_harbor()` | Payment adequacy |
| `solve_withholding(target)` | Invoke the solver |
| `list_harvest_candidates()` | Day-2 integration |
| `get_taxdata(key, year)` | Look up a threshold with its citation |
| `get_profile_field(path)` | Explicit, logged, redaction-aware field read |

Scenario tools let the agent answer "should I…" questions by *actually running
the numbers* rather than estimating them. That is the core of the design.

### 14.5 System prompt requirements

The agent's system prompt must establish:

1. **Role**: an experienced CPA advising on personal tax planning.
2. **Numerical discipline**: never state a figure not returned by a tool; if a
   number is needed, call the tool; if the tool cannot produce it, say so.
3. **Citation**: attach `LineItem` ids or `taxdata` keys to every claim.
4. **Uncertainty**: state fidelity levels; distinguish settled law from
   positions requiring professional judgment.
5. **Scope boundary**: decline to opine on aggressive positions, evasion, or
   anything requiring facts not in evidence; recommend a licensed practitioner
   for filing decisions, audits, notices, and anything with legal exposure.
6. **No fabricated authority**: never invent an IRC section, revenue ruling, or
   court case. If unsure of a citation, describe the rule without a cite.
7. **Currency**: acknowledge that tax law changes and that the loaded data
   files may be unverified or projected for the year in question.

### 14.6 Guardrails (`agent/guardrails.py`)

Post-processing validation on every response:

| Check | Action on failure |
|---|---|
| Numeric grounding: every `$` figure matches a tool result within rounding | Strip the response, retry once with a correction, then refuse |
| Citation presence on advisory claims | Append "uncited" marker |
| Authority format sanity (IRC/Reg/Pub patterns) | Flag for user verification |
| Scope: evasion, fraud, undisclosed income | Hard refusal, logged |
| Disclaimer present | Injected unconditionally |

### 14.7 Privacy controls

- **Off by default.** `[ai].enabled = false` until the user turns it on.
- **Explicit confirmation** before the first transmission of each session,
  showing exactly what will be sent.
- **Redaction** (`agent/context.py`): names, SSNs, account numbers, employer
  names, and addresses are stripped or tokenized before transmission. Numbers
  needed for the analysis are sent; identity is not.
- **`--no-ai`** global flag hard-disables all network paths for a run.
- **`--local-only`** restricts the agent to an on-device model endpoint if the
  user configures one.
- Transcripts are not written unless `[ai].transcript_log = true`.

### 14.8 Example session

```
$ ouch agent

ouch AI CPA · profile 'default' · TY2026 · data: federal 2026 (unverified)
Type /help for commands, /quit to exit. Nothing is sent until you ask.

> I'm getting a $42k bill in April. What happened and what do I do?

Three things drove it, in order of size:

1. Under-withholding on dual W-2 income — $18,900 of the gap.
   Each employer withheld as though its wages were the household's only
   income. Combined wages of $281,000 land you in a higher bracket than
   either job's table assumes. [fed.payments.withholding, fed.tax.ordinary]

2. Schedule C income with no estimated payments — $11,400.
   $28,000 of net self-employment income carried $3,957 of SE tax plus
   ordinary income tax at your 32% marginal rate, and nothing was
   pre-paid. [se.tax.total, fed.tax.marginal]

3. NIIT and Additional Medicare tax — $3,100 combined.
   Neither is withheld by an employer at your income level, so both
   arrive as a surprise at filing. [niit.total, addl_medicare.total]

You are also short of the safe harbor, which adds an estimated $612
penalty. [payments.safe_harbor]

Two actions, in priority order:

  a) File a revised W-4 with extra withholding of $1,725 per pay period
     for your remaining 11 periods. That clears the safe harbor and
     eliminates the penalty. Run: ouch withhold solve --target safe-harbor --w4

  b) Consider a solo 401(k) on the Schedule C income. At your 45.85%
     combined marginal rate, a $10,000 deferral is worth about $4,585.
     Want me to run that scenario?

> yes, and compare it to maxing the HSA instead

[running scenario: solo401k_10k]
[running scenario: hsa_max]
...
```

---

## 15. Error Handling and Validation

### 15.1 Philosophy

An estimate produced from bad input is worse than no estimate, because the user
will act on it. `ouch` validates totally and fails specifically.

### 15.2 Error taxonomy

```python
OuchError
├── ConfigError            # malformed config.toml, unreadable profile
├── ProfileError
│   ├── SchemaError        # unknown key, wrong type
│   └── ConsistencyError   # spouse income with filing_status=single
├── TaxDataError
│   ├── MissingYearError   # no data file for requested year
│   ├── DataSchemaError
│   └── UnverifiedDataError  # only raised under --strict
├── JurisdictionError      # unsupported state/locality
├── PDFError
│   ├── EncryptedPDFError · UnrecognizedFormError · LowConfidenceError
├── ComputationError
│   ├── ConvergenceError   # iterative loop failed to settle
│   └── InvariantError     # internal guard tripped
└── AgentError             # provider auth/network/rate-limit/guardrail
```

Validation errors are **collected and reported together**, never one at a time:

```
✖ Profile validation failed (3 errors) — ~/.config/ouch/profiles/default.toml

  [taxpayer] line 8
    filing_status = "married"
    ✖ not a valid filing status
    → did you mean "married_filing_jointly" or "married_filing_separately"?

  [income.investment] line 34
    qualified_dividends = 14000
    ordinary_dividends  = 12500
    ✖ qualified dividends cannot exceed ordinary dividends
    → box 1b of Form 1099-DIV is a subset of box 1a

  [taxpayer] line 12
    state = "NY", locality = "Brooklyn"
    ✖ unknown locality 'Brooklyn' for NY
    → New York City residents (all five boroughs) use locality = "NYC"
```

Every error message follows the pattern: **what**, **where**, **why**, **fix**.

### 15.3 Engine invariants

Asserted between pipeline stages; a violation aborts with exit 9 rather than
producing a plausible-looking wrong answer.

```
AGI                 <= total_income
taxable_income      >= 0
deduction_taken     == max(standard, itemized) unless forced
tax_preferential    <= pref_income × max_pref_rate
nonrefundable_credits_applied <= tax_before_credits
Σ jurisdiction_tax  == total_tax_all_jurisdictions
every LineItem's declared inputs exist in the trace
trace DAG is acyclic
```

### 15.4 Warnings

Non-fatal but surfaced prominently and included in `--json` output:

- Unverified/projected tax data for the year.
- Any module operating at `heuristic` fidelity.
- Locality unset in a state known to have local taxes.
- Safe harbor not met.
- AMT within 10% of regular tax (i.e., a small change could trigger it).
- More than one business present with QBI (aggregation not modeled).
- Prior-year figures missing, disabling the prior-year safe-harbor test.

---

## 16. Testing and Accuracy Strategy

### 16.1 Test pyramid

| Layer | Content | Target |
|---|---|---|
| Unit | Bracket application, phase-out primitives, Money rounding, netting | 100% of `engine/` |
| Golden | Full returns with hand-computed or software-verified expected output | ≥ 60 fixtures |
| Property | Hypothesis-based invariant testing | See §16.3 |
| Data | Schema validation of every shipped tax data file | Every file, every year |
| CLI | End-to-end command invocation, exit codes, output formats | Every command |
| Snapshot | Rendered output stability | Key commands |

### 16.2 Golden fixtures

Each fixture is a directory:

```
tests/golden/mfj_ny_nyc_selfemployed/
├── profile.toml
├── expected.json          # every TaxResult field, to the dollar
├── expected_trace.json    # full line-item trace
└── SOURCE.md              # how the expected values were derived + cross-check
```

`SOURCE.md` must state the derivation basis: hand computation from forms,
agreement with commercial software, or an actual filed return with identifying
detail removed. **A fixture whose expected values were produced by `ouch`
itself is not a fixture** and is rejected in review.

Required coverage across fixtures: every filing status; standard and itemized;
each state regime (none/flat/progressive); at least three local tax regimes;
AMT-triggering; NIIT-triggering; SE income with and without W-2 wage-base
interaction; QBI below/inside/above the phase-in, SSTB and non-SSTB; EITC at
plateau edges; CTC in phase-out; capital loss carryforward; taxable Social
Security at each inclusion tier.

### 16.3 Property tests

```python
@given(profiles())
def test_monotonic_in_income(p):
    """More ordinary income never reduces total tax (absent credit cliffs)."""

@given(profiles())
def test_deduction_choice_is_optimal(p):
    """Auto mode never produces higher tax than forcing either mode."""

@given(profiles())
def test_marginal_rate_bounded(p):
    """Federal marginal rate lies within [0, 1] and, absent phase-outs,
       does not exceed the top statutory rate."""

@given(profiles())
def test_trace_reconciles(p):
    """Every reported aggregate equals the sum of its trace components."""

@given(profiles(), st.decimals())
def test_withholding_solver_inverts(p, target):
    """solve_withholding(target) fed back through the pipeline yields target."""

@given(profiles())
def test_purity(p):
    """Running the pipeline twice on the same input yields identical results
       and does not mutate the input."""
```

### 16.4 Regression discipline

- Every bug fix ships with the failing case added as a golden fixture.
- Tax data updates run the full golden suite for prior years; prior-year
  results must not change.
- A CI job diffs rendered output for a canonical profile across commits, so
  unintended numeric drift is visible in review.

### 16.5 Accuracy disclosure

`ouch estimate --accuracy` prints the fidelity level of every module engaged in
the computation, with the specific simplifications each makes. The user should
be able to know exactly where the tool is approximating.

---

## 17. Security and Privacy

### 17.1 Threat model

The profile contains a near-complete financial portrait: income, employer,
investments, dependents, and potentially SSNs from imported PDFs. Treat it as
highly sensitive.

### 17.2 Controls

- Config and profile files created with mode `0600`; directories `0700`.
  Startup warns on looser permissions.
- **SSNs are never stored.** The PDF importer discards any SSN/EIN it
  encounters and does not write it to the profile.
- Optional at-rest encryption (`ouch profile encrypt`) using
  AES-256-GCM with a key derived via Argon2id from a passphrase held in the
  system keyring.
- Logs are redacted by default: amounts bucketed, identifiers removed.
  `--debug-unredacted` requires an explicit flag and prints a warning.
- API keys are read from the environment or keyring only; `ouch` never writes a
  key to a file.
- No telemetry, ever. No analytics, no crash reporting, no update pings.
- Backups are created before any profile write, retained for N generations.

### 17.3 Supply chain

- Pinned dependencies with hashes; `pip-audit` in CI.
- Optional extras keep the default install surface small — a user who never
  uses AI never installs a network client.
- Reproducible builds; released artifacts signed.

### 17.4 Disclaimer requirement

Every human-readable output surface (summary, comparison, agent response,
exported report) terminates with:

```
Estimates only. ouch is not tax advice and does not prepare or file returns.
Tax data may be projected or outdated — verify against IRS and state
publications. Consult a licensed tax professional before acting.
```

The disclaimer is not suppressible. `--json` output carries it as a
`disclaimer` field.

---

## 18. User Vignettes (Tutorials)

These vignettes double as the user manual. Each introduces one capability
through a realistic situation, in increasing order of complexity. All figures
are illustrative.

---

### Vignette 1 — "What do I actually pay?"

**Maya, 29, single, software engineer in Austin, Texas.** One W-2, some index
funds, no dependents. She has never understood the difference between her
bracket and her actual rate.

**Goal:** UC-1 — total burden and effective rate.

```bash
$ ouch init
```

```
Welcome to ouch. Let's set up your tax profile.

Tax year [2026]: ⏎
Filing status:
  1) Single
  2) Married filing jointly
  3) Married filing separately
  4) Head of household
  5) Qualifying surviving spouse
Choose [1]: 1
Date of birth [YYYY-MM-DD]: 1997-06-14
State of residence [two-letter]: TX
  ℹ Texas has no state income tax. Local income tax: none.
Dependents [0]: 0

Income — you can add more later or import from PDFs.
  W-2 wages (box 1): 142000
  Federal income tax withheld (box 2): 21400
  Interest income: 850
  Ordinary dividends: 2100
  Qualified dividends (box 1b, subset of the above): 1950
  Long-term capital gains: 3400

✔ Profile written to ~/.config/ouch/profiles/default.toml
  Run `ouch estimate` to see where you stand.
```

```bash
$ ouch estimate
```

```
╭─ ouch · TY2026 · Single · TX (no state income tax) ────────────────────╮
│  Total income                                    $  148,350           │
│  Adjusted gross income                           $  148,350           │
│  Standard deduction                              $ ( 15,000)          │
│  Taxable income                                  $  133,350           │
│                                                                        │
│  Federal income tax                              $   24,181           │
│    ordinary                                      $   23,378           │
│    preferential (QD + LTCG)                      $      803           │
│  ──────────────────────────────────────────────────────────           │
│  TOTAL TAX BURDEN                                $   24,181           │
│                                                                        │
│  Effective rate (of AGI)                             16.30%           │
│  Effective rate (incl. payroll tax)                  23.62%           │
│  Marginal rate on next dollar                        24.00%           │
│                                                                        │
│  Withheld to date                                $   21,400           │
│  ▸ PROJECTED BALANCE DUE                         $    2,781           │
╰────────────────────────────────────────────────────────────────────────╯
```

Maya's reaction is the one the tool is named for, but the useful lesson is the
gap between **24% marginal** and **16.30% effective**. She digs in:

```bash
$ ouch explain fed.tax.ordinary
```

```
fed.tax.ordinary · $23,378 · Ordinary income tax
  Authority: IRC §1(j) · Form 1040 line 16
  Rule: progressive brackets applied to ordinary taxable income

  Ordinary taxable income        $127,999   (taxable income less preferential)
    10% × first $11,925          $  1,193
    12% × next  $36,550          $  4,386
    22% × next  $54,875          $ 12,073
    24% × next  $24,649          $  5,916
                                 ─────────
                                 $ 23,568   … see note
  Note: the 24% band applies to income above $103,350; your ordinary income
  reaches $127,999, of which $24,649 sits in that band.

  Inputs: fed.taxable_income, fed.income.preferential, taxdata.federal.2026
```

```bash
$ ouch explain fed.tax.preferential
```

```
fed.tax.preferential · $803 · Tax on qualified dividends and long-term gains
  Authority: IRC §1(h) · Qualified Dividends and Capital Gain Tax Worksheet

  Preferential income            $  5,350   (QD $1,950 + LTCG $3,400)
  Ordinary taxable income        $127,999   ← this is the floor

  Preferential income stacks ON TOP of ordinary income. The 0% band for
  single filers ends at $48,350, which your ordinary income already exceeds,
  so none of your preferential income qualifies for 0%.

    15% × $5,350                 $    803

  ⓘ Had your ordinary income been under $48,350, part of this would have
    been taxed at 0%. This is why "long-term gains are taxed at 15%" is
    only sometimes true.
```

**Concepts introduced:** `init`, `estimate`, `explain`, marginal vs. effective
rate, preferential stacking.

---

### Vignette 2 — The April surprise, fixed in July

**Ade and Chidi Okonkwo, married filing jointly, Brooklyn.** Two W-2 incomes
($185k and $96k), one child, a $28k consulting sideline, and a $42,445
projected balance due discovered in July. This is UC-2.

```bash
$ ouch withhold check
```

```
Projected balance due                   $ 42,445

Safe harbor analysis (federal):
  90% of projected current-year tax     $ 56,145
  110% of prior-year tax                $ 64,790   ← your requirement
                                                     (prior-year AGI > $150,000)
  Projected federal payments            $ 46,300
  Status  ✗ SHORT by $18,490
  Estimated underpayment penalty        $    612

Diagnosis:
  ⚠ Dual-earner under-withholding.  Each employer's withholding table
    assumes its wages are your household's only income. Your combined
    wages of $281,000 are taxed at a higher marginal rate than either
    employer is withholding for.
  ⚠ $28,000 of self-employment income with no estimated payments.
  ⚠ Additional Medicare tax of $729 — employers withhold this only above
    $200,000 per job; neither of yours crosses that alone.
  ⚠ Net investment income tax of $2,014 is never withheld by an employer.
```

```bash
$ ouch withhold solve --target zero --w4
```

```
11 pay periods remain in 2026 (semi-monthly, from 2026-07-24).

To reach a $0 balance:
  Additional federal withholding    $ 1,725 per period   ($18,975 total)
  Additional NY State withholding   $   402 per period   ($ 4,422 total)
  Additional NYC withholding        $   248 per period   ($ 2,728 total)

Because both spouses have wages, only ONE employer can act on each W-4.
Recommended split (higher earner absorbs the adjustment):

  Ade's employer — Form W-4
    Step 2:  ☑ check the box (multiple jobs / spouse works)
    Step 3:  $2,000        (one qualifying child under 17)
    Step 4(a) other income: $28,000     (consulting)
    Step 4(c) extra withholding per pay period: $1,725

  Chidi's employer — Form W-4
    Step 2:  ☑ check the box
    Step 3:  $0            (claim dependents on ONE W-4 only)
    Step 4(c) extra withholding per pay period: $0

  New York State IT-2104 — additional withholding: $402 per period

⚠ Filing Step 2 on both W-4s without coordinating Step 3 is the most common
  way households double-count the child credit and under-withhold again.

If $1,725 per period is too much cash flow right now:
  ouch withhold solve --target safe-harbor     → $1,140 per period, no penalty,
                                                  but ~$6,400 due in April.
```

```bash
$ ouch withhold solve --target safe-harbor
```

They choose the safe-harbor number, avoid the penalty, and keep the cash. Six
weeks later Ade re-runs `ouch withhold check` after a raise, and the tool picks
up the new figure from an updated profile.

**Concepts introduced:** `withhold check`, `withhold solve`, safe harbor,
dual-earner under-withholding, W-4 translation, target modes.

---

### Vignette 3 — Twelve PDFs and a coffee

**Dev, 41, married, Ohio.** He has a folder of documents and no intention of
typing them in.

```bash
$ ouch import pdf ~/Documents/tax-2026/*.pdf
```

```
Scanning 12 documents...

  ✔ W2_Cardinal_Health.pdf     W-2         11 fields   0.99
  ✔ W2_spouse_OSU.pdf          W-2         11 fields   0.98
  ✔ 1099-INT_Huntington.pdf    1099-INT     2 fields   0.97
  ✔ 1099-DIV_Vanguard.pdf      1099-DIV     6 fields   0.96
  ⚠ 1099-B_Vanguard.pdf        1099-B      63 lots     0.74
  ✔ 1098_Fifth_Third.pdf       1098         3 fields   0.95
  ✔ 1098-T_OSU.pdf             1098-T       2 fields   0.91
  ✔ 1040_2025.pdf              1040 (PY)    3 fields   0.99
  ✖ statement_march.pdf        not a tax form — skipped
  …

Owner assignment:
  W2_Cardinal_Health.pdf → [t]axpayer / [s]pouse ? t
  W2_spouse_OSU.pdf      → [t]axpayer / [s]pouse ? s

2 fields need review.

  1099-B · lot 41 · cost basis
    Extracted: $ 3,1O8.00
    Context:   "…VTI  12.000  03/2024   3,1O8.00   3,402.11…"
    [a]ccept  [e]dit  [s]kip  [v]iew  ? e
    Corrected value: 3108.00 ✔

  1098-T · box 1
    Extracted: $ 8,940.00   (confidence 0.68 — faint scan)
    [a]ccept  [e]dit  [s]kip  [v]iew  ? v
    → rendering page 1 to /tmp/ouch-review-8f2.png
    [a]ccept  [e]dit  [s]kip  ? a

✔ 41 fields staged. Review complete.

Writing to profile 'default'  (backup: default.toml.2026-07-24T09-11-02.bak)
  income.wages.taxpayer_w2         118,400   (was 96,000)   [W2_Cardinal…]
  income.wages.spouse_w2            74,200   (was 71,000)   [W2_spouse_OSU]
  payments.withholding.federal_ytd  23,880   (was 19,100)   [2 sources, summed]
  payments.prior_year.agi          201,340   (was 0)        [1040_2025.pdf]
  payments.prior_year.total_tax     38,720   (was 0)        [1040_2025.pdf]
  … 36 more

⚠ Ohio has municipal income tax. Your profile has no locality set.
  Run: ouch profile set taxpayer.locality=<city>  (see `ouch data list local`)

ℹ 63 capital gain lots were imported to ~/.local/share/ouch/portfolio/lots.csv
  These enable `ouch harvest scan`.

Provenance: ~/.local/share/ouch/imports/2026-07-24T09-11-02.json
```

Note what the prior-year 1040 unlocked: without `payments.prior_year.total_tax`
the safe-harbor test cannot run, so the importer treats that document as
high-priority and says so in `ouch import status`.

```bash
$ ouch profile show --provenance income.wages
```

```
income.wages.taxpayer_w2   $118,400
  source: W2_Cardinal_Health.pdf · page 1 · AcroForm field 'f1_09'
  method: acroform · confidence 0.99 · imported 2026-07-24T09:11:02
  reviewed: no (above threshold)
```

**Concepts introduced:** `import pdf`, review workflow, owner assignment,
aggregation across documents, provenance, prior-year baseline, locality warning.

---

### Vignette 4 — Freelancer, four payments a year

**Priya, 34, single, freelance industrial designer, Philadelphia.** No W-2 at
all. Net Schedule C income around $130k. Philadelphia has a city wage tax; her
concern is quarterly payments and whether she is over-paying.

```bash
$ ouch estimate --breakdown
```

```
Federal
  Schedule C net income                     $ 130,000
  ½ self-employment tax                     $ ( 9,181)
  Self-employed health insurance            $ ( 7,200)
  Solo 401(k) employee deferral             $ (23,000)
  ────────────────────────────────────────────────────
  Adjusted gross income                     $  90,619
  Standard deduction                        $ (15,000)
  QBI deduction (§199A)                     $ (15,124)
  Taxable income                            $  60,495
  Federal income tax                        $   8,247
  Self-employment tax                       $  18,362
  ────────────────────────────────────────────────────
  Federal total                             $  26,609

Pennsylvania (flat 3.07%)                   $   3,991
Philadelphia (resident wage/NPT)            $   4,540
════════════════════════════════════════════════════
TOTAL TAX BURDEN                            $  35,140
Effective rate (of gross Schedule C)           27.03%
Marginal rate on next dollar                   43.11%

ⓘ QBI deduction of $15,124 = 20% × $75,620 of qualified business income
  after the ½ SE tax, health, and retirement adjustments reduce it.
  You are below the §199A threshold, so no wage limitation applies.
  Run `ouch explain fed.qbi` for the full derivation.
```

The $15,124 QBI number surprises her — it is not 20% of $130,000, because the
above-the-line adjustments reduce qualified business income first. `ouch
explain fed.qbi` walks it.

```bash
$ ouch withhold estimates
```

```
2026 quarterly estimated payments · single · PA / Philadelphia

  Safe harbor requirement:
    90% of current-year tax        $ 31,626
    100% of prior-year tax         $ 28,400   ← lower; prior-year AGI < $150k
  Required annual payments         $ 28,400

  Q1  due 2026-04-15   $  7,100   ✔ paid 2026-04-11
  Q2  due 2026-06-15   $  7,100   ✔ paid 2026-06-14
  Q3  due 2026-09-15   $  7,100     upcoming
  Q4  due 2027-01-15   $  7,100

  Federal $ 5,325/qtr · PA $ 998/qtr · Philadelphia $ 1,135/qtr

⚠ You are on pace to pay $28,400 against a projected liability of $35,140.
  That is deliberate: the prior-year safe harbor protects you from penalty
  while you keep $6,740 of cash until April. If you would rather not owe in
  April: ouch withhold estimates --target zero  → $8,785/quarter.

ⓘ Income lumpy? If your Q4 is much larger than Q1, the annualized income
  installment method may reduce early-quarter requirements:
  ouch withhold estimates --annualized
```

**Concepts introduced:** self-employment path, QBI derivation, above-the-line
sequencing, flat-rate state, city wage tax, quarterly estimates, prior-year vs.
current-year safe harbor as a *cash-flow choice*, annualized installments.

---

### Vignette 5 — Should we convert to Roth?

**The Reyes family, MFJ, ages 58 and 57, Colorado.** $310k of income, a large
traditional IRA, and seven years until RMDs. Their advisor suggested "filling up
the 24% bracket."

```bash
$ ouch scenario sweep \
    --var income.retirement.roth_conversion \
    --range 0:250000:25000 \
    --metric total_tax_all_jurisdictions,marginal_rate_combined
```

```
Conversion    Total tax     Δ tax      Marginal cost   Combined marginal
────────────────────────────────────────────────────────────────────────
$      0      $ 61,240        —              —              26.55%
$ 25,000      $ 68,878     $  7,638        30.55%           30.55%
$ 50,000      $ 76,516     $ 15,276        30.55%           30.55%
$ 75,000      $ 84,741     $ 23,501        31.33%           35.65%   ⚠
$100,000      $ 93,653     $ 32,413        32.41%           35.65%
$125,000      $102,565     $ 41,325        33.06%           35.65%
$150,000      $113,204     $ 51,964        34.64%           42.55%   ⚠
$175,000      $123,842     $ 62,602        35.77%           42.55%
$200,000      $134,481     $ 73,241        36.62%           42.55%
$225,000      $145,119     $ 83,879        37.28%           42.55%
$250,000      $155,758     $ 94,518        37.81%           42.55%

⚠ Rate change at $62,000: 22% → 24% federal bracket
⚠ Rate change at $138,000: conversion pushes AGI past the NIIT threshold,
  subjecting $41,000 of investment income to the 3.8% surtax and adding
  $1,558 that is NOT attributable to the converted dollars themselves.

ⓘ "Filling up the 24% bracket" corresponds to a conversion of about
  $131,000 in your situation. The marginal cost of that conversion is
  33.2% all-in, not 24% — the gap is Colorado's flat tax and the NIIT
  spillover onto your investment income.
```

That last note is the whole point of the exercise: the advisor's rule of thumb
ignored two jurisdictions and a threshold effect on *unrelated* income.

```bash
$ ouch scenario new roth-131k --set income.retirement.roth_conversion=131000
$ ouch scenario compare baseline roth-131k --explain
```

They also model the alternative:

```bash
$ ouch scenario new qcd-at-70 --template qcd
$ ouch scenario compare roth-131k qcd-at-70
```

**Concepts introduced:** `scenario sweep`, cliff detection, marginal cost of a
change, threshold spillover onto unrelated income, scenario templates,
`compare`.

---

### Vignette 6 — December, and a losing position (Day 2)

**Sam, 44, MFJ, Massachusetts.** Realized $22,000 of short-term gains in
March from a position he regrets. It is December 12.

```bash
$ ouch harvest scan --as-of 2026-12-12
```

```
Portfolio: 214 lots · 6 accounts · as of 2026-12-12
Realized YTD: $22,000 short-term gain · $3,100 long-term gain

Harvest candidates · marginal ST 40.05% / LT 23.05% (fed+MA+NIIT)

  #  Symbol  Lot     Held    Unrealized   Char   Tax benefit  Wash risk
  1  ARKG    L-0217  7 mo    $ (14,200)   ST     $  5,687     ✔ clear
  2  VXUS    L-0431  4 mo    $ ( 8,240)   ST     $  3,300     ⚠ DRIP 11/28
  3  BND     L-0388  9 mo    $ ( 2,950)   ST     $  1,181     ✔ clear
  4  IEFA    L-0155  2.3 yr  $ ( 6,100)   LT     $  1,406     ✔ clear

⚠ Lot 2 (VXUS): a dividend reinvestment purchased 3.114 shares on
  2026-11-28, inside the 30-day window. Selling now disallows the loss on
  3.114 of your 41 shares — $626 of the $8,240 loss. The remaining $7,614
  is harvestable. Turn off automatic reinvestment for 31 days to clear it.

⚠ Lot 4 (IEFA): you also hold IEFA in your IRA. A purchase there within
  the window would PERMANENTLY disallow the loss, not merely defer it —
  the basis adjustment has nowhere to go. No IRA purchases detected.
```

```bash
$ ouch harvest simulate --sell L-0217 L-0388 L-0155
```

```
Simulated sale of 3 lots on 2026-12-12

  Short-term losses realized              $ (17,150)
  Long-term losses realized               $ ( 6,100)

  Netting (IRC §1211 ordering):
    ST losses offset ST gains             $  17,150  of $22,000  → $4,850 ST gain remains
    LT losses offset LT gains             $   3,100  of $ 3,100  → $0 LT gain remains
    Remaining LT loss offsets ST gain     $   3,000              → $1,850 ST gain remains
    Excess loss to ordinary income        $       0
    Carryforward to 2027                  $       0

  Tax effect:
                              Before      After        Δ
    Federal                 $ 47,880    $ 40,655    $ (7,225)
    Massachusetts           $  9,110    $  8,210    $   (900)
    NIIT                    $  1,244    $    571    $   (673)
    ─────────────────────────────────────────────────────────
    Total tax               $ 58,234    $ 49,436    $ (8,798)

  Deferred cost:
    Basis reduction                       $ 23,250
    Future tax at assumed 23.05%          $  5,359
    Net present benefit @ 5% / 10 yr      $  5,509

ⓘ Most of the benefit here is real rather than deferred, because you are
  converting short-term gain (taxed at 40.05%) into future long-term gain
  (23.05%). That rate arbitrage, not the deferral, is the value.

⚠ Do not repurchase these securities before 2027-01-12.
   ouch harvest washsale-check --watch  will warn you if you do.
```

**Concepts introduced:** `harvest scan`, `harvest simulate`, wash-sale windows
including DRIP and IRA traps, statutory netting order, character arbitrage,
deferred-cost honesty, carryforward.

---

### Vignette 7 — Asking the CPA

**Marcus, 52, MFJ, Illinois.** Recently exercised ISOs and does not know what
he is looking at.

```bash
$ ouch agent --review
```

```
⚠ AI review will transmit the following to anthropic (model: <configured>):
    • Computed tax result and line-item trace (amounts only)
    • Profile field names and values, REDACTED as follows:
        names → removed · employer → removed · SSN → never stored
        state/locality → retained (needed for analysis)
  Nothing is sent until you confirm.  Proceed? [y/N] y
```

```
Reviewed your 2026 profile. Four things, most important first.

1. You have an AMT exposure you probably don't know about.
   Your ISO exercise created $184,000 of bargain element. That amount is
   invisible for regular tax but fully included for AMT. Your tentative
   minimum tax now exceeds your regular tax by $31,400, which you owe.
   [amt.tentative, amt.additional]

   The good news: that $31,400 becomes an AMT credit you can recover in
   future years when regular tax exceeds tentative minimum tax. It is a
   timing cost, not a permanent one — but it is a cash cost this April.

2. There is a disqualifying-disposition strategy worth modeling.
   Selling some shares before year end converts that portion from AMT
   preference income to ordinary compensation income, which can reduce
   total tax despite the higher rate. Want me to run it?
   I would model sale quantities from 0 to all 12,000 shares.

3. Your withholding does not contemplate any of this.
   Projected balance due is $38,900 and you are $22,100 short of the safe
   harbor, with an estimated $740 penalty. Since it's September, the
   fastest fix is payroll withholding rather than a Q3 estimate —
   withholding is treated as paid evenly across the year regardless of
   when it occurs, which can retroactively cure earlier quarters.
   [payments.safe_harbor, payments.withholding]

4. Illinois treats this differently than the federal return.
   Illinois has no AMT, so the $184,000 preference does not appear in your
   Illinois base at all. Your state exposure is limited to the ordinary
   income from any disqualifying disposition. [IL.taxable]

I want to be direct about limits: ISO planning interacts with your holding
periods, your concentration risk, and your view of the stock, none of which
I can see. The AMT credit recovery schedule in particular depends on future
years' income. This is worth an hour with a CPA who can see the grant
documents.

> run the disqualifying disposition sweep

[sweep: shares_sold 0..12000 step 1000 · 13 pipeline runs]
...
```

**Concepts introduced:** `agent --review`, explicit transmission consent and
redaction, agent-invoked scenarios through the real engine, citation of line
items, the agent naming its own limits.

---

### Vignette 8 — "Would moving actually help?"

**Jordan, 38, single, fully remote, currently in California.** Weighing Texas,
Washington, and Tennessee.

```bash
$ ouch scenario compare --relocate CA,TX,WA,TN,NV,FL
```

```
Relocation comparison · TY2026 · single · $215,000 W-2 · $40,000 LTCG

                    CA          TX          WA          TN
──────────────────────────────────────────────────────────────
Federal          $ 44,180    $ 44,180    $ 44,180    $ 44,180
State income     $ 16,842    $      0    $      0    $      0
State cap gains  $      —    $      —    $  2,800*   $      —
Local            $      0    $      0    $      0    $      0
──────────────────────────────────────────────────────────────
TOTAL            $ 61,022    $ 44,180    $ 46,980    $ 44,180
Effective rate     23.93%      17.33%      18.42%      17.33%
Annual delta          —      $(16,842)   $(14,042)   $(16,842)

* Washington's capital gains excise tax applies above an annual standard
  deduction; your $40,000 of long-term gain is partially exposed.

⚠ This compares INCOME tax only. Property tax, sales tax, insurance, and
  cost of living frequently offset a large share of the difference and are
  outside ouch's scope.
⚠ Part-year relocation is modeled separately — a mid-year move requires
  income allocation between states. See `ouch estimate --part-year`.
⚠ Remote work may create a tax obligation in your employer's state under
  convenience-of-the-employer rules. ouch does not model this. Ask a CPA
  before relying on this comparison.
```

The warnings matter as much as the table. A tool that reports a $16,842 saving
without flagging the convenience rule and the omitted non-income taxes is
giving the user a partial picture, which is how planning tools cause harm.

**Concepts introduced:** multi-state comparison, no-income-tax states that
nonetheless tax something, scope honesty.

---

## 19. Roadmap

### M1 — Core estimator (UC-1, UC-2)

Config and profile system · federal engine (ordinary, preferential stacking,
SE tax, NIIT, Additional Medicare, standard/itemized, CTC/ODC) · flat and
progressive state modules driven by data · withholding solver · `estimate`,
`withhold`, `explain`, `profile`, `data`, `config` · trace infrastructure ·
30+ golden fixtures.

**Exit criteria:** all golden fixtures pass to the dollar; the preferential
stacking test matrix (§9.4) passes; `withhold solve` inverts within $0.01.

### M2 — Ingestion and scenarios

PDF pipeline for P0 forms with review workflow · scenario patch model, `run`,
`compare`, `sweep`, cliff detection · AMT · QBI · full credit suite with
phase-outs · local tax modules (NYC, PA EIT, OH) · JSON/CSV/markdown output.

### M3 — Day 2: portfolio and harvesting

Lot ingestion · wash-sale engine · benefit quantification through the real
pipeline · deferred-cost modeling · gain harvesting and holding-period alerts ·
carryforward tracking.

### M4 — AI CPA agent

Provider-agnostic client · tool schemas · redaction and consent · guardrails ·
`ask`, `agent`, `agent --review`.

### M5 — Depth

Part-year and multi-state allocation · annualized installment method · AMT
credit carryforward · K-1 depth · REIT/PTP QBI components · additional states
and localities · optional TUI.

### Deliberately deferred

Return preparation, e-filing, brokerage connectivity, entity returns,
international (FEIE, FTC beyond the basic credit, PFIC), estate and gift.

---

## 20. Appendices

### A. Glossary

| Term | Meaning in `ouch` |
|---|---|
| **Trace** | The DAG of `LineItem`s produced by a computation |
| **Fidelity** | Declared accuracy level of a module: exact / approximate / heuristic |
| **Patch** | A set of dotted-path overrides defining a scenario |
| **Preferential income** | Qualified dividends + net long-term capital gains |
| **Marginal cost** | Δ tax ÷ Δ input for a scenario change |
| **Safe harbor** | Payment level that avoids an underpayment penalty |
| **Provenance** | Origin record for an imported field |
| **Verified data** | Tax data file populated from published primary sources |

### B. Data file version compatibility

`schema_version` on each data file is checked against the range the running
`ouch` supports. Mismatch is a hard error with an upgrade instruction. Profiles
carry their own `schema_version`; `ouch profile migrate` upgrades in place with
a backup.

### C. Output format contract

`--format json` emits a stable, versioned schema:

```json
{
  "ouch_version": "1.0.0",
  "schema_version": 1,
  "tax_year": 2026,
  "input_fingerprint": "sha256:…",
  "fidelity": "approximate",
  "result": { "...": "all TaxResult fields" },
  "trace": [ { "id": "fed.agi", "label": "...", "amount": "356240.00", "...": "" } ],
  "warnings": [ { "code": "UNVERIFIED_DATA", "message": "..." } ],
  "disclaimer": "Estimates only. ouch is not tax advice…"
}
```

Consumers should key on `id`, never on ordering. New fields may be added within
a `schema_version`; fields are removed only on a major bump.

### D. Contributing tax data

1. One PR per jurisdiction-year.
2. Every value cited in `meta.source` to a primary document.
3. `verified: true` only when every figure traces to published guidance.
4. Include at least one golden fixture exercising the new file.
5. `ouch data validate` and the full golden suite must pass.
6. Reviewer independently checks a random sample of figures against sources.

### E. Primary sources to consult when populating data files

- IRS annual inflation-adjustment Revenue Procedures (brackets, standard
  deduction, phase-outs, AMT exemption)
- IRS Publication 17 (general), 505 (withholding and estimated tax),
  550 (investment income), 590-A/B (IRAs), 15-T (withholding methods)
- Form instructions: 1040, Schedule D, Form 8949, 8995/8995-A, 6251, 8959,
  8960, 2210
- SSA annual wage-base announcement
- State Department of Revenue publications and rate schedules
- Municipal tax authorities (NYC DOF, PA DCED official EIT register, Ohio RITA
  and CCA, Maryland comptroller county rates)

> Tax legislation enacted after this specification was written may have changed
> deductions, credits, and thresholds materially. Verify every figure for the
> year being modeled before marking a data file `verified`.

### F. Non-advice statement

`ouch` is a personal planning tool. It does not prepare, review, sign, or file
tax returns; it does not create a preparer relationship; and its output is an
estimate that may be wrong. Users should verify material decisions with a
licensed CPA, EA, or tax attorney.
