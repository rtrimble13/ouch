# Vignette 5 — Should we convert to Roth?

**The Reyes family, married filing jointly, ages 58 and 57, Colorado.** $310k
of income, a large traditional IRA, and seven years until required minimum
distributions. Their advisor suggested "filling up the 24% bracket."

**Commands introduced:** `ouch scenario new / list / show / delete / run /
compare / sweep`
**Concepts:** patches vs copies · relative and computed values · marginal cost
of a change · cliff detection · assertions as guardrails · what a scenario
patch cannot do

---

## The profile

```toml
schema_version = 2
tax_year       = 2026

[taxpayer]
filing_status = "married_filing_jointly"
birth_date    = "1968-04-22"
state         = "CO"

[spouse]
birth_date = "1969-09-30"

[income.wages]
taxpayer_w2       = 210000
spouse_w2         = 60000
taxpayer_ss_wages = 210000
spouse_ss_wages   = 60000

[income.investment]
interest            = 4000
ordinary_dividends  = 18000
qualified_dividends = 16000
long_term_gains     = 18000

[payments.withholding]
federal_ytd          = 42000
state_ytd            = 11000
federal_per_period   = 1800
pay_periods_per_year = 24

[payments.prior_year]
agi       = 295000
total_tax = 57000
```

Baseline: **$63,854** of total tax, a 20.60% effective rate, and a 29.30%
combined marginal rate.

---

## 1. Sweep before you commit

The question is not "should we convert?" but "how much?". A sweep answers the
whole shape at once.

```bash
$ ouch scenario sweep --var income.retirement.roth_conversion \
                      --range 0:250000:25000
```

```
income.retirement.roth_conversion     Total tax   Δ tax/Δ var     total_tax_all_juri  marginal_rate_comb
──────────────────────────────────────────────────────────────────────────────────
             0        63,854             —            63,854.0000              0.2930
        25,000        70,954        28.40%            70,954.0000              0.2930
        50,000        78,054        28.40%            78,054.0000              0.2930
        75,000        85,154        28.40%            85,154.0000              0.2930
       100,000        92,254        28.40%            92,254.0000              0.2930
       125,000        99,354        28.40%            99,354.0000              0.2930
       150,000       106,566        28.85%           106,566.0000              0.3730
       175,000       115,666        36.40%           115,666.0000              0.3730   ⚠ cliff
       200,000       124,766        36.40%           124,766.0000              0.3730
       225,000       133,866        36.40%           133,866.0000              0.3730
       250,000       142,966        36.40%           142,966.0000              0.3730

⚠ Cliff detected at income.retirement.roth_conversion ≈ 175,000: marginal rate
  jumps to 36.4% — a threshold or phase-out sits between the neighboring steps
```

Three columns, three different questions:

- **`Total tax`** — what you would owe at that conversion amount.
- **`Δ tax/Δ var`** — the marginal cost *of the conversion itself*: extra tax
  divided by extra conversion, step to step. This is the number the decision
  turns on.
- **`marginal_rate_comb`** — the rate on the next dollar of ordinary income at
  that point, which tells you where you have landed.

The advisor's "24% bracket" advice is already contradicted at $25,000: the true
all-in marginal cost is **28.40%**, because Colorado's 4.4% flat tax rides
along. Nobody converting in Colorado pays 24%.

### Narrow the range to find the edge

```bash
$ ouch scenario sweep --var income.retirement.roth_conversion \
                      --range 100000:180000:10000 \
                      --metric marginal_rate_combined
```

```
income.retirement.roth_conversion     Total tax   Δ tax/Δ var     marginal_rate_comb
──────────────────────────────────────────────────────────────
       100,000        92,254             —                 0.2930
       110,000        95,094        28.40%                 0.2930
       120,000        97,934        28.40%                 0.2930
       130,000       100,774        28.40%                 0.2930
       140,000       103,614        28.40%                 0.2930
       150,000       106,566        29.52%                 0.3730
       160,000       110,206        36.40%                 0.3730   ⚠ cliff
       170,000       113,846        36.40%                 0.3730
       180,000       117,486        36.40%                 0.3730
```

The transition sits between $140,000 and $150,000: the combined marginal rate
goes 29.30% → 37.30% as the conversion pushes taxable income past $394,600 and
out of the 24% federal bracket into 32%. Both figures decompose the same way —
`ouch estimate --marginal` reports federal 24.90% → 32.90% (the bracket plus
0.9% Additional Medicare, since their wages already exceed the joint threshold),
and Colorado's flat 4.4% rides on top of each.

The cliff flag fires when the *step* marginal jumps by more than
`--cliff-threshold` (default 3 percentage points) between neighbouring points.

**Conversions up to about $140,000 cost 28.40%. Beyond that, 36.40%.** That is
the actionable finding, and it is nothing like "24%".

Finer sweeps cost more compute — every point is a full pipeline run — so the
usual method is coarse, then narrow, as above.

---

## 2. Name the good one

```bash
$ ouch scenario new roth-140k --set income.retirement.roth_conversion=140000
```

```
✔ scenario written to ~/.config/ouch/scenarios/roth-140k.toml
```

A scenario is a **named patch against a base profile — never a copy**. That
matters through the year: when the Reyes family updates their W-2 figures in
November, every scenario automatically reflects the new baseline instead of
carrying a stale snapshot.

```toml
name = "roth-140k"
base = "default"

[patch]
"income.retirement.roth_conversion" = 140000
```

Preview before writing with `--dry-run`:

```bash
$ ouch --dry-run scenario new demo --set income.retirement.roth_conversion=50000 \
                                   --set taxpayer.state=TX
```

```
name = "demo"
base = "default"

[patch]
"income.retirement.roth_conversion" = 50000
"taxpayer.state" = "TX"
```

`base = "default"` means "whatever profile is active", so the same scenario
works against `--profile spouse` too.

---

## 3. Run and compare

```bash
$ ouch scenario run roth-140k
```

```
                                  baseline     roth-140k
────────────────────────────────────────────────────────
AGI                              $ 310,000     $ 450,000
Taxable income                   $ 280,000     $ 420,000
Federal total                     $ 51,534      $ 85,134
NIIT                               $ 1,520       $ 1,520
State tax                         $ 12,320      $ 18,480
TOTAL TAX                         $ 63,854     $ 103,614
Effective rate (AGI)                20.60%        23.03%
Marginal rate (next $)              29.30%        29.30%

roth-140k: Δ tax vs baseline $ 39,760
  Marginal cost of the change: 28.40% of the changed amount (Δ input $ 140,000)
```

`run NAME` is shorthand for `compare baseline NAME`. **`baseline` is a
pseudo-scenario** meaning the unpatched profile — you can name it in any
comparison.

The **marginal cost of the change** line is the one to read: $39,760 of extra
tax on $140,000 of conversion is 28.40%. Not the 24% bracket, not the 29.30%
marginal rate — the actual average cost of this actual change.

### Compare several at once

```bash
$ ouch scenario new roth-max --template roth-conversion
$ ouch scenario compare baseline roth-140k roth-max
```

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

roth-max: Δ tax vs baseline $ 21,300
  Marginal cost of the change: 28.40% of the changed amount (Δ input $ 75,000)
```

Rows appear conditionally: NIIT, state, and local lines show only when some
scenario has them. `compare` also calls out threshold spillover in words when a
scenario crosses into NIIT or triggers AMT — the case where extra tax lands on
income you did not touch.

---

## 4. Templates

```bash
$ ouch scenario new hsa --template hsa-max
```

Six ship:

| Template | Patches |
|---|---|
| `roth-conversion` | `income.retirement.roth_conversion`, plus a marginal-rate assertion |
| `bonus-deferral` | `income.wages.taxpayer_w2` down by $25,000 |
| `hsa-max` | `adjustments.hsa` |
| `bunch-charitable` | `deductions.itemized.charitable_cash` at `+100%` |
| `relocate-state` | `taxpayer.state`, `taxpayer.locality` |
| `solo401k` | `adjustments.sep_solo401k` |

A template is a starting point you edit, not a finished answer — the amounts
are placeholders. Ask for one that doesn't exist and you get the list:

```
✖ unknown template 'nope'
  → available: bonus-deferral, bunch-charitable, hsa-max, relocate-state,
    roth-conversion, solo401k
```

---

## 5. Relative and computed patch values

Patches take three forms:

| Form | Example | Meaning |
|---|---|---|
| absolute | `75000`, `true`, `"TX"` | Set it |
| relative | `"+10%"`, `"-5000"`, `"+2500"` | Adjust from the base value |
| computed | `"= income.wages.taxpayer_w2 * 0.10"` | Arithmetic over paths and numbers |

```toml
name        = "tuned"
base        = "default"
description = "10% raise, and a solo 401(k) sized at 10% of wages"

[patch]
"income.wages.taxpayer_w2"   = "+10%"
"adjustments.sep_solo401k"   = "= income.wages.taxpayer_w2 * 0.10"
"income.investment.interest" = "-1500"
```

```bash
$ ouch scenario compare baseline tuned
```

```
                                  baseline         tuned
────────────────────────────────────────────────────────
AGI                              $ 310,000     $ 308,500
Taxable income                   $ 280,000     $ 278,500
Federal total                     $ 51,534      $ 51,117
NIIT                               $ 1,520       $ 1,463
State tax                         $ 12,320      $ 12,254
TOTAL TAX                         $ 63,854      $ 63,371
Effective rate (AGI)                20.60%        20.54%
Marginal rate (next $)              29.30%        29.30%

tuned: Δ tax vs baseline $ (483)
  Marginal cost of the change: -1.19% of the changed amount (Δ input $ 40,500)
```

> **Every patch value resolves against the *base* profile, not against the
> other patches.** Here the 401(k) is 10% of the **original** $210,000, not of
> the raised $231,000. That ordering-independence is deliberate — patch entries
> in a TOML table have no defined order, so making them depend on each other
> would make results depend on file layout. When you need a chained
> calculation, do the arithmetic yourself and write the absolute value.

Computed expressions support `+ - * /` and parentheses over numbers and dotted
profile paths, and are evaluated by a small recursive-descent parser. `ouch`
never calls `eval` on your scenario files.

---

## 6. Assertions: guardrails that fail the run

A scenario can carry conditions that must hold. This is how you encode "convert,
but never past this rate":

```toml
name        = "guardrail"
base        = "default"
description = "Convert only while the federal marginal rate stays under 30%"

[patch]
"income.retirement.roth_conversion" = 200_000

[assert]
"result.marginal_rate_federal" = {lt = 0.30}
```

```bash
$ ouch scenario compare baseline guardrail
```

```
                                  baseline     guardrail
────────────────────────────────────────────────────────
AGI                              $ 310,000     $ 510,000
TOTAL TAX                         $ 63,854     $ 124,766
Effective rate (AGI)                20.60%        24.46%
Marginal rate (next $)              29.30%        37.30%

guardrail: Δ tax vs baseline $ 60,912
  Marginal cost of the change: 30.46% of the changed amount (Δ input $ 200,000)
  ✖ assert result.marginal_rate_federal lt 0.3 violated (actual 0.3290)
✖ scenario assertion violated (see above)
```

```bash
$ echo $?
9
```

The numbers still print — you want to see what failed — but the command exits
**9**. That makes assertions usable in a script or a pre-commit check: encode
your planning constraints once, and a scenario that breaks them fails loudly.

Operators: `lt`, `le`, `gt`, `ge`, `eq`. Paths address the result object, e.g.
`result.marginal_rate_federal`, `result.total_tax_all_jurisdictions`,
`result.niit`.

---

## 7. What a scenario patch cannot do

One important limitation. **A patch that changes `taxpayer.state` or
`taxpayer.locality` does not reload the tax data.** The jurisdiction files are
resolved once, from the unpatched profile, before any scenario runs.

```bash
$ ouch scenario new tx-move --template relocate-state
$ ouch scenario compare baseline tx-move
```

```
State tax                         $ 12,320      $ 12,320
TOTAL TAX                         $ 63,854      $ 63,854
```

Δ 0 — because Colorado's data was used for both columns, even though the patch
sets `taxpayer.state = "TX"`. The `relocate-state` template will mislead you if
you take that result at face value.

Model relocation with `estimate --state` instead, which resolves the data
*after* the override:

```bash
$ ouch estimate                    # Colorado
$ ouch estimate --state TX         # Texas
```

```
╭─ ouch · Tax Year 2026 · Married Filing Jointly · CO · fidelity: exact ─╮
│ CO state tax                                        $ 12,320           │
│ TOTAL TAX BURDEN                                    $ 63,854           │

╭─ ouch · Tax Year 2026 · Married Filing Jointly · TX · fidelity: exact ─╮
│ TOTAL TAX BURDEN                                    $ 51,534           │
```

**$12,320 a year**, which is the real answer. (Income tax only — property
taxes, sales tax, insurance, and cost of living are outside `ouch`'s scope, and
they are frequently what makes the move a wash.)

Use scenarios for anything that varies *within* a jurisdiction, and
`--state` / `--locality` for anything that changes the jurisdiction.

---

## 8. Housekeeping

```bash
$ ouch scenario list
```

```
  guardrail                Convert only while the federal marginal rate stays under 30%
  roth-140k
  roth-max                 Convert from traditional IRA before year end
  tuned                    10% raise, and a solo 401(k) sized at 10% of wages
```

```bash
$ ouch scenario show roth-max
```

```
roth-max (base: default)
  Convert from traditional IRA before year end
  income.retirement.roth_conversion = 75000
  assert result.marginal_rate_federal lt 0.35
```

```bash
$ ouch scenario delete tuned
```

`new` refuses to clobber an existing scenario:

```
✖ scenario 'roth-140k' already exists at ~/.config/ouch/scenarios/roth-140k.toml
  → delete it first with `ouch scenario delete`
```

Scenario files live in `~/.config/ouch/scenarios/`. They are plain TOML —
version-control them, share them, hand-edit them.

---

## 9. Feeding a spreadsheet

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

`sweep` is the one command that honours `--format csv`. The `cliff` column is
`1` where a cliff was flagged, empty otherwise.

---

## What the Reyes family learned

- "Fill up the 24% bracket" was wrong twice: the all-in cost of conversion is
  **28.40%** because of Colorado, and the bracket edge that matters sits near
  **$140,000**, past which it becomes **36.40%**.
- `Δ tax/Δ var` prices the change; `marginal_rate_combined` describes where you
  landed. They are different columns for a reason.
- Scenarios are patches, so they stay correct as the base profile changes
  through the year — and every value resolves against that base, not against
  sibling patches.
- `[assert]` turns a planning constraint into a failing exit code.
- Changing state or locality needs `--state` / `--locality`, not a patch.

## Try it yourself

```bash
ouch scenario sweep --var adjustments.hsa --range 0:8300:1000
ouch scenario sweep --var income.investment.long_term_gains --range 0:300000:25000 \
                    --cliff-threshold 0.01
ouch scenario new bunch --template bunch-charitable
ouch scenario compare baseline bunch roth-140k
```

---

**Previous:** [Vignette 4 — Freelancer, four payments a year](04-freelancer-quarterly.md) ·
**Next:** [Vignette 6 — December, and a losing position](06-harvesting-losses.md)
