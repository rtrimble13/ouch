# Vignette 8 — Half a year in two states

**Marcus and Elena, married filing jointly, mid-fifties.** They spent January
through May in Washington, took a job in the Bay Area in June, and sold a long
-held position along the way — $190,000 of long-term gains on top of $353,000
of wages. Marcus also carries an AMT credit from an option exercise three years
ago that he has never been able to use.

**Commands introduced:** `ouch estimate --state / --locality / --federal-only`
**Concepts:** part-year residency · `former_state` · localities and the missing
-data warning · the AMT credit carryforward · which jurisdiction each dollar
belongs to

---

## The profile

```toml
schema_version = 2
tax_year       = 2026

[taxpayer]
filing_status    = "married_filing_jointly"
birth_date       = "1974-01-09"
state            = "CA"
residency_months = 7
former_state     = "WA"

[spouse]
birth_date = "1976-06-21"

[income.wages]
taxpayer_w2       = 265000
spouse_w2         = 88000
taxpayer_ss_wages = 265000
spouse_ss_wages   = 88000

[income.investment]
interest            = 5000
ordinary_dividends  = 12000
qualified_dividends = 11000
long_term_gains     = 190000

[payments.withholding]
federal_ytd          = 74000
state_ytd            = 9000
federal_per_period   = 3100
pay_periods_per_year = 24

[payments.prior_year]
agi       = 340000
total_tax = 79000
```

Three fields carry the move:

- **`state = "CA"`** — where they live now, and the jurisdiction the summary
  header names.
- **`residency_months = 7`** — June through December.
- **`former_state = "WA"`** — where the other five months were spent.

---

## 1. The result

```bash
$ ouch estimate
```

```
╭─── ouch · Tax Year 2026 · Married Filing Jointly · CA · fidelity: approximate ───╮
│ Total income                                       $ 560,000                     │
│ Adjusted gross income                              $ 560,000                     │
│ Deduction (standard)                              $ (30,000)                     │
│ Taxable income                                     $ 530,000                     │
│                                                                                  │
│ Federal income tax                                  $ 94,804                     │
│   ordinary                                            $ 64,654                   │
│   preferential (QD + LTCG)                            $ 30,150                   │
│ Additional Medicare tax                                $ 927                     │
│ Net investment income tax                            $ 7,866                     │
│   ──────────────────────────────────────────────────────────                     │
│ Federal total                                      $ 103,597                     │
│ CA state tax                                        $ 25,745                     │
│   ══════════════════════════════════════════════════════════                     │
│ TOTAL TAX BURDEN                                   $ 129,342                     │
│                                                                                  │
│   Effective rate (of AGI)                               23.10%                   │
│   Effective rate (of gross income)                      23.10%                   │
│   Marginal rate on next dollar (combined)               30.32%                   │
│                                                                                  │
│ Withheld + paid (projected through year end)       $ 114,000                     │
│ ▸ PROJECTED BALANCE DUE                             $ 15,342                     │
│                                                                                  │
│   ⚠  part-year residency: state tax allocated by month ratio (7/12 in CA,        │
│      remainder in WA) — approximate; states use their own allocation schedules   │
│   ⚠  AMT within 10% of regular tax — a small change could trigger it             │
│   ⚠  EITC: investment income exceeds the $11,950 limit                           │
│   ⚠  Tax data for 2026 is unverified (projected)                                 │
│   ⚠  State tax data (CA 2026) is unverified                                      │
╰──────────────────────────────────────────────────────────────────────────────────╯
```

The $190,000 of long-term gains and $11,000 of qualified dividends cost
**$30,150** federally. All $201,000 of it lands in the 15% preferential band:
ordinary taxable income of $329,000 sets the floor, which is past the 0% ceiling
of $96,700 but well short of the 20% threshold of $600,050. On top of that,
**$7,866** of NIIT — 3.8% of the full $207,000 of net investment income
($5,000 interest + $12,000 dividends + $190,000 gains), since MAGI clears the
joint threshold by far more than that.

---

## 2. How part-year allocation works — and its limit

```bash
$ ouch estimate --breakdown
```

```
ca.agi · $ 560,000 · CA AGI
  federal_agi + additions − subtractions
ca.taxable · $ 548,920 · CA taxable income
  state AGI less deduction and exemptions
ca.tax · $ 25,745 · CA income tax
  progressive rate schedule less credits
wa.tax · $ 0 · WA income tax (part-year)
  full-year WA tax × 5/12 residency ratio
```

`ouch` computes the **full-year** liability in each state and prorates by
residency months. Full-year California on this income would be $44,134; times
7/12 gives $25,745. Washington has no income tax, so the other five months cost
nothing.

Confirm it directly:

```bash
$ ouch estimate --set taxpayer.residency_months=12
```

```
│ CA state tax                                        $ 44,134           │
```

**$18,389 of California tax avoided** by having moved in June rather than
January.

### Read the fidelity warning

> ⚠ part-year residency: state tax allocated by month ratio (7/12 in CA,
> remainder in WA) — approximate; states use their own allocation schedules

This is an honest simplification. A real part-year return does not prorate by
months. California would source the wages earned while resident, tax
non-residents on California-source income, and compute the rate on total income
before applying it to the California portion — and a $190,000 capital gain is
sourced by where you lived when you *realized* it, not by a month ratio.

For a move like this, treat `ouch`'s state number as the right order of
magnitude and the federal number as solid. The federal computation is unaffected
by residency; only the state allocation is approximate.

### When both states tax income

Change the former state to one that levies income tax and a second line appears:

```bash
$ ouch estimate --set taxpayer.former_state=NY
```

```
│ CA state tax                                        $ 25,745           │
│ NY (part-year)                                      $ 13,905           │
│   ══════════════════════════════════════════════════════════           │
│ TOTAL TAX BURDEN                                   $ 143,247           │
```

```
ny.tax · $ 13,905 · NY income tax (part-year)
  full-year NY tax × 5/12 residency ratio
```

Full-year New York, times 5/12. Note that `ouch` does **not** model the credit
for taxes paid to another state here — the two allocations are computed
independently. If the same dollar could be taxed twice, this arithmetic will
overstate it.

### Forget `former_state` and `ouch` tells you

```bash
$ ouch estimate --set taxpayer.former_state=""
```

```
⚠  part-year residency: state tax allocated by month ratio (7/12 in CA,
   remaining months unallocated — set taxpayer.former_state)
```

Five months of income are then in nobody's base, which will understate the
total. `ouch` names the missing field rather than quietly returning a smaller
number.

---

## 3. Localities

Marcus and Elena have no local income tax. Many people do, and `ouch` ships
local data for **NYC only**.

For a state known to levy municipal income tax, an unset locality gets called
out:

```bash
$ ouch --profile okonkwo estimate --locality ""
```

```
│ NY state tax                                        $ 17,836           │
│ TOTAL TAX BURDEN                                    $ 74,539           │
│   ⚠  NY has local income taxes but no locality is set — local tax computed
│      as zero, which is probably wrong
```

With the locality set, the missing $11,971 appears:

```bash
$ ouch --profile okonkwo estimate --locality NYC
```

```
│ NY state tax                                        $ 17,836           │
│ NYC local tax                                       $ 11,971           │
│   ══════════════════════════════════════════════════════════           │
│ TOTAL TAX BURDEN                                    $ 86,511           │
```

The watched states are NY, PA, OH, MD, MI, KY, IN, MO, AL, DE, and WV. Ask for a
locality with no data file and you get an error, not a zero:

```bash
$ ouch estimate --locality BOSTON
```

```
✖ no tax data for locality 'BOSTON' in 2026
  → available localities: NYC
```

```bash
$ echo $?
7
```

Exit **7** is the unsupported-jurisdiction code. Adding the missing file is a
ten-line job — vignette 10.

---

## 4. Jurisdiction overrides

Three flags let you re-run against different jurisdictions without touching the
profile:

```bash
ouch estimate --state TX          # what if we lived in Texas?
ouch estimate --locality NYC      # add a locality
ouch estimate --federal-only      # strip state and local entirely
```

`--federal-only` is the fastest way to see how much of the burden is federal:

```
│ TOTAL TAX BURDEN                                   $ 103,597           │
```

$103,597 of $129,342 — about 80%.

> These flags reload the tax data for the jurisdiction you name, which is why
> **relocation must be modelled with `--state`, not with a scenario patch.**
> A scenario that patches `taxpayer.state` changes the label but keeps the
> original state's data. Vignette 5 §7 has the demonstration.

---

## 5. The AMT credit Marcus has been carrying

Three years ago he exercised incentive stock options, triggered AMT, and paid
$31,400 he has never recovered. That is not a lost payment — it becomes a
**minimum tax credit** (Form 8801) usable in a later year, but only to the
extent regular tax exceeds tentative minimum tax that year.

Record it:

```toml
[carryovers]
amt_credit = 31400
```

```bash
$ ouch estimate
```

```
│ Federal income tax                                  $ 94,804           │
│   ordinary                                            $ 64,654         │
│   preferential (QD + LTCG)                            $ 30,150         │
│ Additional Medicare tax                                $ 927           │
│ Net investment income tax                            $ 7,866           │
│ Credits                                            $ (6,934)           │
│   ──────────────────────────────────────────────────────────           │
│ Federal total                                       $ 96,663           │
│                                                                        │
│   ⚠  AMT credit carryforward remaining: $24,466 (carries to future years)
```

```
fed.credits.amt · $ 6,934 · Minimum tax credit (AMT carryforward)
  prior-year AMT recovered up to the excess of regular tax over tentative
  minimum tax
```

**$6,934 recovered this year, $24,466 still carried.** The limit is the
headroom between regular tax and tentative minimum tax — the credit exists
precisely to unwind AMT once you are clear of it, so the more AMT-exposed the
year, the less of it you can use. `ouch` reports the remainder rather than
silently dropping it, so you can carry the number forward.

### The proximity warning

```
⚠ AMT within 10% of regular tax — a small change could trigger it
```

They are not paying AMT, but they are close enough that another preference item
would tip them in — and that would zero out the credit recovery entirely.

**A caveat worth stating plainly:** `ouch`'s AMT is deliberately simplified. It
adds back the standard deduction (or the SALT deduction if itemizing) and
nothing else. **ISO bargain elements — the single most common cause of AMT for
people who have a credit carryforward at all — are not modeled.** The credit
carryforward mechanics work; the AMT trigger detection will miss the exact
situation that created Marcus's credit. Fidelity for this module is
`approximate`, and the header says so.

---

## 6. Fixing the payments

```bash
$ ouch withhold check
$ ouch withhold solve --target safe-harbor
```

The mid-year move makes this worth doing twice: California withholding started
in June, and the capital gain had no withholding at all. Vignette 2 covers the
mechanics; the only thing specific to a move is that the state withholding in
your profile should reflect the *new* state's rate from the month you started
there.

---

## What Marcus and Elena learned

- Part-year state tax is the **full-year liability × residency-month ratio** —
  a real approximation, and `ouch` labels it as one.
- Moving in June instead of January saved **$18,389** of California tax on these
  numbers.
- `former_state` matters: leave it blank and five months of income sit in no
  state's base at all.
- A missing locality is a **warning** in the eleven states known to levy one,
  and an **error** (exit 7) if you name a jurisdiction with no data file.
- A prior AMT payment is a recoverable credit, limited each year by the
  headroom between regular tax and tentative minimum tax — $6,934 of $31,400
  this year.
- `--state`, `--locality`, and `--federal-only` reload data; scenario patches
  do not.

## Try it yourself

```bash
ouch estimate --state WA                                # full year in Washington
ouch estimate --set taxpayer.residency_months=3         # if they had moved in October
ouch scenario sweep --var taxpayer.residency_months --range 0:12:3 \
                    --metric total_tax_all_jurisdictions
    # works, but read the Total tax column only — `Δ tax/Δ var` divides dollars
    # by months and is meaningless for a non-money variable
ouch --explain estimate --federal-only
ouch explain fed.niit
```

---

**Previous:** [Vignette 7 — The refund that isn't a refund](07-credits-and-dependents.md) ·
**Next:** [Vignette 9 — Asking the CPA](09-the-ai-cpa.md)
