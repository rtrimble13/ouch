# Vignette 1 — "What do I actually pay?"

**Maya, 29, single, software engineer in Austin, Texas.** One W-2, some index
funds, no dependents. She knows she is "in the 24% bracket" and has never
understood why her paycheck doesn't look like it.

**Commands introduced:** `ouch init`, `ouch estimate`, `ouch explain`
**Concepts:** marginal vs effective rate · preferential rate stacking · the
computation trace

---

## 1. Set up a profile

```bash
$ ouch init
```

```
Welcome to ouch. Let's set up your tax profile.

Tax year [2026]: 2026
Filing status:
  1) Single
  2) Married Filing Jointly
  3) Married Filing Separately
  4) Head Of Household
  5) Qualifying Surviving Spouse
Choose [1]: 1
Date of birth [YYYY-MM-DD]: 1997-06-14
State of residence [two-letter] []: TX
  ℹ TX has no state income tax.
Dependents [0]: 0

Income — you can add more later by editing the profile.
  W-2 wages (box 1) [0]: 142000
  Federal income tax withheld (box 2) [0]: 21400
  Interest income [0]: 850
  Ordinary dividends [0]: 2100
  Qualified dividends (box 1b, subset of the above) [0]: 1950
  Long-term capital gains [0]: 3400

✔ Profile written to ~/.config/ouch/profiles/default.toml
  Run `ouch estimate` to see where you stand.
```

`init` writes plain TOML you own and can edit:

```toml
schema_version = 2
tax_year       = 2026

[taxpayer]
filing_status  = "single"
birth_date     = "1997-06-14"
state          = "TX"

[income.wages]
taxpayer_w2 = 142000

[income.investment]
interest            = 850
ordinary_dividends  = 2100
qualified_dividends = 1950
long_term_gains     = 3400

[payments.withholding]
federal_ytd = 21400
```

`init` asks about the common cases only. Everything else — business income,
itemized deductions, dependents, prior-year figures — you add by editing this
file. The [manual's profile reference](../MANUAL.md#7-profile-reference) lists
every field.

> **Note on `qualified_dividends`.** Box 1b of a 1099-DIV is a *subset* of box
> 1a, not an addition to it. `ouch` enforces that: enter more qualified than
> ordinary and the profile fails validation with an explanation. Maya's
> $2,100 of dividends includes $1,950 of qualified ones; only $150 is ordinary.

---

## 2. The one-screen answer

```bash
$ ouch estimate
```

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
  Estimates only. ouch is not tax advice and does not prepare or file returns.
  Run `ouch --explain estimate` for detail.
```

Read the header first. `Single · TX` confirms the jurisdictions;
`fidelity: exact` says every line in this computation models the statute
directly rather than approximating it. Lines that don't apply — AMT,
self-employment tax, NIIT, credits, state tax — are simply absent.

Then read the two warnings, because they are honest and they matter:

- **Unverified data.** The 2026 figures that ship with `ouch` are projected
  placeholders. `ouch data verify` lists what still needs checking against
  primary sources.
- **No prior-year figures.** Without last year's total tax, the prior-year
  safe-harbor test can't run. Vignette 2 shows why that matters.

### Marginal 24%, effective 16.43%

This is the whole lesson of the first screen. Maya's **last** dollar is taxed at
24%. Her **average** dollar is taxed at 16.43%, because the earlier dollars went
through the 10%, 12%, and 22% bands first, and $15,000 came off the top as the
standard deduction.

The two numbers answer different questions. Effective tells you what this year
cost. Marginal tells you what the *next* decision costs — a raise, a bonus, a
retirement contribution. Never use one for the other's job.

Confirm the marginal figure directly:

```bash
$ ouch estimate --marginal
```

```
  Marginal (federal, next $1,000): 24.00%   Marginal (combined): 24.00%
```

`ouch` does not read that 24% off a bracket table. It re-runs the entire
computation with $1,000 more income and measures the difference. That
distinction seems pedantic here — Maya sits in the middle of a bracket — but it
is what makes the number trustworthy when phase-outs, NIIT, and credit cliffs
are in play. You will see it earn its keep in vignettes 5 and 7.

---

## 3. Where did $23,567 come from?

```bash
$ ouch explain fed.tax.ordinary
```

```
fed.tax.ordinary · $ 23,567 · Ordinary income tax
├── Authority: IRC §1(j) · 1040 line 16
├── Rule: progressive brackets applied to ordinary taxable income, computed as
│   if preferential income did not exist
├── fed.taxable · $ 133,350 · Taxable income
│   ├── Authority: IRC §63 · 1040 line 15
│   ├── Rule: AGI less deduction less QBI
│   ├── fed.agi · $ 148,350 · Adjusted gross income
│   │   ├── Authority: IRC §62 · 1040 line 11
│   │   ├── Rule: total income less above-the-line adjustments
│   │   ├── fed.income.total · $ 148,350 · Total income
│   │   │   ├── Authority: IRC §61 · 1040 line 9
│   │   │   ├── Rule: sum of all income included in gross income, by rate group
│   │   │   ├── fed.income.wages · $ 142,000 · Wages
│   │   │   │   ├── Authority: 1040 line 1a
│   │   │   │   └── Rule: sum of W-2 box 1 wages
│   │   │   └── fed.income.capital · $ 3,400 · Net capital gain/(loss) in income
│   │   │       ├── Authority: IRC §1211, §1212 · Schedule D
│   │   │       └── Rule: statutory netting: ST vs ST, LT vs LT, cross-net,
│   │   │           ordinary offset limited
│   │   └── fed.adjustments · $ 0 · Above-the-line adjustments
│   │       └── … (elided)
│   └── fed.deduction · $ 15,000 · Deduction (standard)
│       ├── Authority: IRC §63 · 1040 line 12
│       ├── Rule: max(standard $15,000, itemized $0)
│       └── … (elided)
└── taxdata.federal.2026 (data reference)
```

Every line carries an **id**, an **amount**, an **authority** (the code section
and the form line), a **rule**, and its upstream inputs — recursively, to the
leaves. That is the computation trace, and it is the reason `ouch` has no
unexplained numbers.

The arithmetic behind that line, using the brackets `ouch` loaded
(`ouch data show federal 2026 --key ordinary_brackets`):

| Band | Rate | Amount taxed | Tax |
|---|---|---|---|
| first $11,925 | 10% | 11,925 | 1,192.50 |
| to $48,475 | 12% | 36,550 | 4,386.00 |
| to $103,350 | 22% | 54,875 | 12,072.50 |
| to $197,300 | 24% | 24,650 | 5,916.00 |
| | | **128,000** | **23,567.00** |

Note the base: **$128,000**, not $133,350. That is taxable income *less the
$5,350 of qualified dividends and long-term gains*, which get their own
treatment — which is the next line.

### To see every line at once

```bash
$ ouch estimate --breakdown
```

```
fed.income.wages · $ 142,000 · Wages
  sum of W-2 box 1 wages
fed.income.capital · $ 3,400 · Net capital gain/(loss) in income
  statutory netting: ST vs ST, LT vs LT, cross-net, ordinary offset limited
fed.setax · $ 0 · Self-employment tax
  92.35% of SE net income; SS portion limited to the wage base remaining after
  the taxpayer's own W-2 social security wages (the wage base is per person)
fed.adjustments · $ 0 · Above-the-line adjustments
  ½ SE tax + SE health (limited to SE income) + IRA/HSA/retirement and other adjustments
fed.income.total · $ 148,350 · Total income
  sum of all income included in gross income, by rate group
fed.agi · $ 148,350 · Adjusted gross income
  total income less above-the-line adjustments
fed.deduction · $ 15,000 · Deduction (standard)
  max(standard $15,000, itemized $0)
fed.taxable · $ 133,350 · Taxable income
  AGI less deduction less QBI
fed.tax.ordinary · $ 23,567 · Ordinary income tax
  progressive brackets applied to ordinary taxable income, computed as if
  preferential income did not exist
fed.tax.preferential · $ 803 · Tax on qualified dividends and LTCG
  preferential income stacks on top of ordinary income and fills the 0/15/20
  brackets from that floor
fed.tax.total · $ 24,370 · Federal total tax
  income tax + AMT + SE tax + Additional Medicare + NIIT − credits
tx.tax · $ 0 · TX income tax
  TX has no personal income tax
total.tax · $ 24,370 · Total tax, all jurisdictions
  federal + state + local
total.payments · $ 21,400 · Withholding and estimated payments projected through year end
  YTD withholding + per-period × periods remaining + estimates
total.balance · $ 2,970 · Projected balance due / (refund)
  total tax less total payments
```

Those ids on the left are exactly what `ouch explain` accepts. Ask for one that
doesn't exist and `ouch` lists the ones that do:

```bash
$ ouch explain fed.nope
```

```
✖ no line item 'fed.nope' in this computation
  → available: fed.adjustments, fed.agi, fed.deduction, fed.income.capital,
    fed.income.total, fed.income.wages, fed.setax, fed.tax.ordinary,
    fed.tax.preferential, fed.tax.total, fed.taxable, total.balance,
    total.payments, total.tax, tx.tax
```

Which ids exist depends on your profile. Maya has no self-employment income, so
there is no `fed.setax` breakdown to speak of; a freelancer's trace has more
lines, a Californian's has state lines. The trace describes *this* computation.

---

## 4. The $803 that teaches the most

```bash
$ ouch explain fed.tax.preferential
```

```
fed.tax.preferential · $ 803 · Tax on qualified dividends and LTCG
├── Authority: IRC §1(h) · QD & CG Tax Worksheet
├── Rule: preferential income stacks on top of ordinary income and fills the
│   0/15/20 brackets from that floor
├── fed.taxable · $ 133,350 · Taxable income
│   └── … (the same derivation as above)
└── taxdata.federal.2026 (data reference)
```

Everyone "knows" long-term gains are taxed at 15%. The rule is more
interesting, and the phrase to hold onto is **from that floor**.

The preferential brackets for a single filer in 2026
(`ouch data show federal 2026 --key preferential_brackets`) are 0% up to
$48,350, then 15% up to $533,400, then 20%. But preferential income does not
start at zero — it stacks **on top of** ordinary income. Maya's ordinary taxable
income is $128,000, which already blows past $48,350, so the 0% band is fully
consumed before a single dollar of her gains arrives. All $5,350 lands in the
15% band:

```
5,350 × 15% = $802.50  →  $803
```

Prove it by lowering the ordinary income and rerunning. `--set` applies an
override in memory without touching the profile:

```bash
$ ouch estimate --set income.wages.taxpayer_w2=45000
```

```
│ Total income                                        $ 51,350           │
│ Adjusted gross income                               $ 51,350           │
│ Deduction (standard)                              $ (15,000)           │
│ Taxable income                                      $ 36,350           │
│                                                                        │
│ Federal income tax                                   $ 3,482           │
│   ordinary                                             $ 3,482         │
```

The preferential line has vanished — not because the gains disappeared, but
because at $31,000 of ordinary taxable income the whole $5,350 fits inside the
0% band. Same gains, same taxpayer, **$803 versus $0**, decided entirely by
what sits underneath them.

That is why "long-term gains are taxed at 15%" is only sometimes true, and why
timing a realization against a low-income year is a real strategy rather than
folklore. Vignette 6 turns this into a tool: `harvest scan` reports exactly how
much 0%-band room you have left.

---

## 5. Trying something out

Maya's employer offers an HSA. What is it worth?

```bash
$ ouch estimate --set adjustments.hsa=4400
```

```
│ TOTAL TAX BURDEN                                    $ 23,314           │
│ ▸ PROJECTED BALANCE DUE                              $ 1,914           │
```

$24,370 → $23,314: **$1,056** saved, on a $4,400 contribution. That is 24% —
her marginal rate — which is exactly what an above-the-line deduction is worth.
The marginal rate did its job.

`--set` is repeatable and never writes to disk. When a what-if is worth keeping,
promote it to a named scenario — that is vignette 5.

---

## What Maya learned

- Her **marginal** rate (24%) and her **effective** rate (16.43%) are different
  numbers answering different questions.
- Qualified dividends and long-term gains are taxed **from the floor set by her
  ordinary income**, which is why hers cost 15% and would have cost 0% on a
  smaller salary.
- Every number has an id, an authority, and a derivation: `--breakdown` lists
  them, `explain` walks them.
- She is $2,970 short. Fixing that is vignette 2.

## Try it yourself

```bash
ouch --explain estimate              # append the fed.tax.total derivation
ouch -vvv estimate                   # summary plus the full trace
    # note: --explain and -v are GLOBAL options and must come before the
    # subcommand. `ouch estimate --explain` exits 2 with "No such option".
ouch estimate --standard             # force the standard deduction
ouch estimate --set income.investment.long_term_gains=40000 --marginal
ouch --format json estimate | head -40
```

---

**Next:** [Vignette 2 — The April surprise, fixed in July](02-the-april-surprise.md)
