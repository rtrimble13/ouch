# Vignette 10 — Under the hood

**Priya from vignette 4**, still missing her Philadelphia city wage tax. And
anyone who wants `ouch` in a script, a Makefile, or a CI job.

**Commands introduced:** `ouch data list / validate / show / verify`,
`ouch config show / path`, `ouch profile show / validate / new / path`
**Concepts:** the tax-data search path · writing a jurisdiction file ·
configuration precedence · JSON and CSV output · exit codes as a contract

---

## 1. What data is loaded?

```bash
$ ouch data list
```

```
federal: 2025, 2026
state: CA-2025, CA-2026, CO-2025, CO-2026, FL-2025, FL-2026, MA-2025, MA-2026,
       NY-2025, NY-2026, PA-2025, PA-2026, TX-2025, TX-2026, WA-2025, WA-2026
local: NYC-2025, NYC-2026
```

That is everything `ouch` can compute today. Ask for anything else and you get
an error rather than a wrong number:

```bash
$ ouch estimate --state OR
```

```
✖ no tax data for state 'OR' in 2026
  → available states: CA, CO, FL, MA, NY, PA, TX, WA — contribute a data file
    (see spec appendix D)
```

### The search path

Files are resolved in this order, **first hit wins**:

1. `taxdata.path` from `config.toml`, or `$OUCH_TAXDATA`, which overrides it
2. `~/.local/share/ouch/taxdata/`
3. the files packaged inside `ouch`

So your own file **shadows** a shipped one. That is how you patch a bad rate
without waiting for a release, and how you add a jurisdiction that doesn't ship.

Layout under any root:

```
federal/<YEAR>.yaml
state/<CODE>-<YEAR>.yaml
local/<NAME>-<YEAR>.yaml
```

---

## 2. Add Philadelphia

Priya's estimate has been carrying this warning since vignette 4:

```
⚠ PA has local income taxes but no locality is set — local tax computed as
  zero, which is probably wrong
```

Ten lines fix it.

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

Every field earns its place:

| Field | Why |
|---|---|
| `jurisdiction` | The code you pass to `--locality` |
| `parent` | The state this locality sits inside |
| `schema_version` | 1–3 supported; a newer number is a hard error |
| `verified: false` | **Be honest.** This is what makes every result carry a warning |
| `source` | Where you got the numbers, for the next person (probably you) |
| `regime` | `none`, `flat`, or `progressive` |
| `applies_to` | `residents`, `workers`, or `both` |
| `starting_point` | Which base to tax — here, PA taxable income |
| `rate` | Required for `flat`; use `brackets` for `progressive` |

Check it, then use it:

```bash
$ ouch data list
```

```
local: NYC-2025, NYC-2026, PHL-2026
```

```bash
$ ouch data validate
```

```
  ✔ federal/2025.yaml
  ✔ federal/2026.yaml
  ...
  ✔ local/NYC-2026.yaml
✔ 21 data files valid
```

```bash
$ ouch estimate --locality PHL
```

```
╭─ ouch · Tax Year 2026 · Single · PA / PHL · fidelity: approximate ─╮
│ Total income                                       $ 130,000       │
│ Adjusted gross income                               $ 90,616       │
│ Deduction (standard)                              $ (15,000)       │
│ QBI deduction                                     $ (15,123)       │
│ Taxable income                                      $ 60,493       │
│                                                                    │
│ Federal income tax                                   $ 8,222       │
│   ordinary                                             $ 8,222     │
│ Self-employment tax                                 $ 18,368       │
│   ──────────────────────────────────────────────────────────       │
│ Federal total                                       $ 26,591       │
│ PA state tax                                         $ 2,782       │
│ PHL local tax                                        $ 3,398       │
│   ══════════════════════════════════════════════════════════       │
│ TOTAL TAX BURDEN                                    $ 32,771       │
```

**$3,398 that was invisible ten minutes ago.** Make it permanent by setting
`locality = "PHL"` in the profile.

### A malformed file is a hard error

```yaml
meta:
  jurisdiction: OR
  year: 2026
regime: progressive       # ...but no brackets
```

```bash
$ ouch data validate
```

```
  ✖ state/OR-2026.yaml
      regime 'progressive' requires `brackets`
```

```bash
$ echo $?
5
```

And the same file blocks any computation that would use it:

```bash
$ ouch estimate --state OR
```

```
✖ ~/.local/share/ouch/taxdata/state/OR-2026.yaml: regime 'progressive' requires `brackets`
```

Exit 5, not a zero-tax state. `ouch` will not compute through a file it cannot
trust.

---

## 3. Inspect any figure

```bash
$ ouch data show federal 2026 --key niit
```

```json
{
  "rate": "0.038",
  "threshold": {
    "single": 200000,
    "married_filing_jointly": 250000,
    "married_filing_separately": 125000,
    "head_of_household": 200000,
    "qualifying_surviving_spouse": 250000
  }
}
```

```bash
$ ouch data show state MA 2026 --key meta
```

```json
{
  "jurisdiction": "MA",
  "year": 2026,
  "schema_version": 3,
  "verified": false,
  "source": ["MA DOR — Part B income tax rate"],
  "notes": "4% surtax above $1M and 8.5% ST-gain rate not modeled."
}
```

**Read the `notes`.** They record what a module deliberately does not do —
here, that Massachusetts' millionaire surtax and short-term-gain rate are
absent. That is where a state's fidelity limits are documented.

For `federal`, the second argument is the year and there is no third:
`ouch data show federal 2026`. For state and local it is
`ouch data show state CA 2026`.

### What still needs checking

```bash
$ ouch data verify
```

```
Unverified / projected data files (results carry a warning):
  ⚠ federal/2025
  ⚠ federal/2026
  ⚠ state/CA-2025
  ⚠ state/CA-2026
  ...
```

Everything, currently. `verified: false` is the shipped default until each
figure has been independently checked against a primary source — an IRS Revenue
Procedure, a state DOR publication. **Treat the shipped 2026 numbers as
projected placeholders.** Every result computed from them carries a warning, and
the vignettes' figures are illustrative for that reason.

---

## 4. Configuration

```bash
$ ouch config path
$ ouch config show --origin
```

```
ai.enabled = False    (default)
general.default_profile = 'default'    (default)
general.tax_year = 'current'    (default)
output.format = 'table'    (default)
output.verbosity = 1    (default)
...
```

The `--origin` column is the useful part: it tells you *why* a setting has the
value it has.

```toml
# ~/.config/ouch/config.toml
[general]
default_profile = "priya"
tax_year        = 2026

[output]
verbosity = 2
```

```bash
$ ouch config show --origin | grep default_profile
```

```
general.default_profile = 'priya'    (/home/you/.config/ouch/config.toml)
```

And an environment variable outranks the file:

```bash
$ OUCH_PROFILE=maya ouch config show --origin | grep default_profile
```

```
general.default_profile = 'maya'    (env OUCH_PROFILE)
```

### Precedence

Highest wins:

1. Command-line flags
2. Environment variables (`OUCH_*`)
3. Scenario patch
4. Profile file
5. `config.toml`
6. Built-in defaults

### Environment variables

| Variable | Effect |
|---|---|
| `OUCH_PROFILE` | Default profile |
| `OUCH_TAX_YEAR` | Default tax year |
| `OUCH_CONFIG` | Alternate `config.toml` |
| `OUCH_TAXDATA` | Tax data directory — overrides `taxdata.path` |
| `OUCH_AI_ENABLED` | Turn the AI feature on |
| `OUCH_NO_COLOR` / `NO_COLOR` | Disable colour |

Or point at a whole different config for one run:

```bash
ouch --config ~/work/ouch-config.toml estimate
```

> **Your own data directory.** Set it once in `config.toml` instead of
> exporting a variable in every shell:
>
> ```toml
> [taxdata]
> path = "~/tax/ouch-data"
> ```
>
> `OUCH_TAXDATA` still overrides it for a single run. If the directory doesn't
> exist, `ouch` stops with exit 3 and names where the path was set, rather
> than quietly using the shipped data. Several keys are declared with defaults
> but not yet consumed: `general.currency`, `general.confirm_destructive`,
> `output.round_display`, `taxdata.strict_year`, `taxdata.allow_projected`,
> `privacy.encrypt_profiles`, `privacy.redact_in_logs`, and
> `ai.transcript_log`. The
> [manual's configuration reference](../MANUAL.md#8-configuration-reference)
> marks each one.

---

## 5. Profiles as files

```bash
$ ouch profile path
$ ouch profile new second-opinion       # commented template
$ ouch profile validate
$ ouch profile show
```

`profile show` prints the **post-validation** view — defaults filled in, types
coerced, exactly what the engine received:

```json
{
  "tax_year": 2026,
  "taxpayer": {
    "name": "",
    "birth_date": "1997-06-14",
    "blind": false,
    "filing_status": "single",
    "state": "TX",
    "locality": "",
    "residency_months": 12,
    "former_state": ""
  },
  ...
}
```

When a figure surprises you, this is the fastest way to check that `ouch` read
what you meant.

`profile validate` collects **every** error at once rather than stopping at the
first:

```
✖ Profile validation failed (2 errors)
  [taxpayer.filing_status]
    ✖ Input should be 'single', 'married_filing_jointly',
      'married_filing_separately', 'head_of_household' or
      'qualifying_surviving_spouse'
    → did you mean "married_filing_jointly" or "married_filing_separately"?
  [income.investment]
    ✖ Value error, qualified dividends cannot exceed ordinary dividends
      (box 1b of Form 1099-DIV is a subset of box 1a)
```

Exit 3. Note the hints: `ouch` recognises common mistakes and names the fix.

Profiles are written mode `0600` in a `0700` directory, and every write leaves a
timestamped `.bak` next to the original.

---

## 6. Machine-readable output

### JSON

```bash
$ ouch --format json estimate
```

```json
{
  "ouch_version": "0.1.0",
  "schema_version": 1,
  "tax_year": 2026,
  "input_fingerprint": "sha256:3c0ddc8ff2678cbf74e386f45e34a4a2dadddfc1ea600476a32328cf0c8114dc",
  "fidelity": "exact",
  "result": { "...": "every TaxResult field" },
  "trace": [ "...": "every line item" ],
  "warnings": [],
  "disclaimer": "Estimates only. ouch is not tax advice ..."
}
```

Amounts are **decimal strings**, not floats — `"86510.60"`, never `86510.6`.
Parse them with `Decimal`, not `float`, or you have thrown away the reason
`ouch` uses exact arithmetic internally.

```bash
$ ouch --format json --profile okonkwo estimate | python3 -c "
import json,sys
d = json.load(sys.stdin)
r = d['result']
print('total   ', r['total_tax_all_jurisdictions'])
print('marginal', r['marginal_rate_combined'])
print('fidelity', d['fidelity'])
print('warnings', [w['message'] for w in d['warnings']])
"
```

```
total    86510.60
marginal 0.3478
fidelity approximate
warnings ['EITC: investment income exceeds the $11,950 limit',
          'Tax data for 2026 is unverified (projected)',
          'State tax data (NY 2026) is unverified',
          'Safe harbor NOT met — see `ouch withhold check`']
```

`input_fingerprint` is a SHA-256 of the canonicalised input. Store it alongside
a saved result and you can prove later exactly which profile produced it.

Write straight to a file:

```bash
ouch --format json --output ~/estimates/2026-07.json estimate
```

`--output` captures whatever a command would print, in any format: the table
panel, `withhold check`, a CSV sweep. The file is written only if the command
succeeds, so a failed run leaves no stale or partial snapshot, and the exit
code tells your script why. A missing directory is exit 2 before any work is
done.

### CSV

```bash
$ ouch --format csv scenario sweep --var income.retirement.roth_conversion \
                                   --range 0:50000:25000 \
                                   --metric total_tax_all_jurisdictions
```

```
income.retirement.roth_conversion,total_tax,step_marginal,cliff,total_tax_all_jurisdictions
0,63854,,,63854
25000,70954,0.2840,,70954
50000,78054,0.2840,,78054
```

### What honours what

| Command | `json` | `csv` |
|---|---|---|
| `estimate` | ✔ (incl. `--compare-filing-status`) | falls back to the table |
| `scenario sweep` | falls back to the table | ✔ |
| everything else | unchanged | unchanged |

`--format markdown` currently renders the same as `table`. `profile show` and
`data show` always emit JSON regardless of `--format`. Every command honours
`--output`.

---

## 7. Exit codes are a contract

| Code | Meaning |
|---|---|
| 0 | Success |
| 2 | Invalid CLI usage |
| 3 | Configuration or profile error |
| 4 | Input validation error (e.g. a lot CSV) |
| 5 | Tax data missing or malformed |
| 6 | PDF could not be read |
| 7 | Unsupported jurisdiction |
| 8 | AI disabled, not installed, or a provider failure |
| 9 | Computation guard tripped, or a scenario assertion failed |

They are stable, so `ouch` composes:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Fail the build if the shipped tax data is broken.
ouch data validate

# Fail if any profile stopped validating after an edit.
for p in ~/.config/ouch/profiles/*.toml; do
  ouch --profile "$p" profile validate
done

# Fail if a planning constraint is violated — [assert] exits 9.
ouch scenario compare baseline roth-140k

# Snapshot this month's estimate, keyed by input fingerprint.
ouch --format json --output "estimates/$(date +%Y-%m).json" estimate
```

Exit **9** deserves a note. It means `ouch` detected that it was about to emit a
number it could not stand behind — a tripped invariant, a solver that failed to
converge, a violated assertion — and refused. It never substitutes a guess.
Wiring it into CI turns your tax planning constraints into a build check.

---

## 8. Rehearsing without consequences

```bash
ouch --dry-run init                         # print the profile, write nothing
ouch --dry-run profile new backup
ouch --dry-run scenario new test --set adjustments.hsa=8300
ouch --dry-run import pdf ~/docs/*.pdf      # full review + diff, no write
ouch --dry-run harvest import lots.csv      # validate only
```

`--dry-run` is global and every write path honours it. Combined with `--config`
and `XDG_CONFIG_HOME`, you can rehearse an entire workflow against a throwaway
directory:

```bash
export XDG_CONFIG_HOME=/tmp/ouch-sandbox/config
export XDG_DATA_HOME=/tmp/ouch-sandbox/data
ouch init
```

That is exactly how the profiles in these vignettes were built.

---

## 9. Everything on disk

| Path | Contents |
|---|---|
| `~/.config/ouch/config.toml` | Global settings |
| `~/.config/ouch/profiles/*.toml` | Profiles (`0600`, dir `0700`) |
| `~/.config/ouch/profiles/*.toml.<ts>.bak` | Automatic backups |
| `~/.config/ouch/scenarios/*.toml` | Scenarios |
| `~/.local/share/ouch/taxdata/` | Your tax data overrides |
| `~/.local/share/ouch/portfolio/lots.csv` | Imported portfolio |
| `~/.local/share/ouch/imports/<ts>.json` | Provenance records |

Nothing else. No cache, no telemetry, no network — except the AI feature you
have to turn on twice.

All of it is plain text. Put `~/.config/ouch/` in a private git repository and
you get versioned tax planning: every profile edit, every scenario, every data
override, with history.

---

## What you learned

- Tax data resolves `taxdata.path` (or `$OUCH_TAXDATA`) → XDG data dir →
  packaged, first hit wins, so **your file shadows the shipped one**.
- A ten-line YAML file added a real jurisdiction and surfaced $3,398 of tax.
- A malformed data file is exit 5, never a silent zero.
- `config show --origin` answers "why is this setting what it is", including
  where `taxdata.path` came from.
- JSON amounts are decimal strings; `input_fingerprint` ties a result to its
  input.
- Exit codes are stable enough to build CI on, and exit 9 means `ouch` refused
  rather than guessed.

## Try it yourself

```bash
ouch data show federal 2026 --key qbi
ouch data show federal 2026 --key credits.eitc
ouch data show local NYC 2026 --key brackets
ouch config show --origin
ouch --format json estimate | python3 -m json.tool | less
```

---

**Previous:** [Vignette 9 — Asking the CPA](09-the-ai-cpa.md) ·
**Back to:** [the index](README.md) · [the manual](../MANUAL.md)
