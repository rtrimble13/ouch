# Vignette 2 — The April surprise, fixed in July

**Ade and Chidi Okonkwo, married filing jointly, Brooklyn.** Two W-2 incomes
($185k and $96k), one child in kindergarten, Ade's $28k consulting sideline,
and a brokerage account. Last April they owed money they hadn't budgeted for. It is
now July and they would like not to repeat that.

**Commands introduced:** `ouch withhold check`, `ouch withhold solve`,
`ouch withhold w4`
**Concepts:** the safe harbor · dual-earner under-withholding · the taxes no
employer withholds · target modes as a cash-flow choice

---

## The profile

```toml
schema_version = 2
tax_year       = 2026

[taxpayer]
filing_status  = "married_filing_jointly"
birth_date     = "1986-03-02"
state          = "NY"
locality       = "NYC"

[spouse]
birth_date = "1988-11-19"

[[dependents]]
birth_date   = "2019-05-04"
relationship = "child"

[income.wages]
taxpayer_w2       = 185000
spouse_w2         = 96000
taxpayer_ss_wages = 176100
spouse_ss_wages   = 96000

[income.business]
owner          = "taxpayer"
schedule_c_net = 28000

[income.investment]
interest            = 1200
ordinary_dividends  = 9500
qualified_dividends = 8100
long_term_gains     = 14000

[payments.withholding]
federal_ytd          = 34800
state_ytd            = 11500
local_ytd            = 4200
federal_per_period   = 1450
pay_periods_per_year = 24
periods_remaining    = 11

[payments.prior_year]
agi       = 268000
total_tax = 58900
```

Three details that carry weight later:

- **`taxpayer_ss_wages` / `spouse_ss_wages`** are W-2 box 3, which an
  employer caps at the Social Security wage base ($176,100 in this data) —
  so Ade's box 3 is lower than box 1. **`owner`** says whose business the
  consulting is. `ouch` uses the owner's box 3 to work out how much of *that
  person's* wage base is left for the consulting income.
- **`periods_remaining = 11`** pins the calendar. Leave it at `0` and `ouch`
  derives it from today's date and the pay-period count.
- **`[payments.prior_year]`** is what makes the prior-year safe-harbor test
  possible at all. Skip it and the analysis degrades to a question mark.

---

## 1. Where do we stand?

```bash
$ ouch estimate
```

```
╭─ ouch · Tax Year 2026 · Married Filing Jointly · NY / NYC · fidelity: approximate ─╮
│ Total income                                       $ 333,700                       │
│ Adjusted gross income                              $ 333,325                       │
│ Deduction (standard)                              $ (30,000)                       │
│ Taxable income                                     $ 303,325                       │
│                                                                                    │
│ Federal income tax                                  $ 56,503                       │
│   ordinary                                            $ 53,188                     │
│   preferential (QD + LTCG)                             $ 3,315                     │
│ Self-employment tax                                    $ 750                       │
│ Additional Medicare tax                                $ 512                       │
│ Net investment income tax                              $ 939                       │
│ Credits                                            $ (2,000)                       │
│   ──────────────────────────────────────────────────────────                       │
│ Federal total                                       $ 56,703                       │
│ NY state tax                                        $ 17,836                       │
│ NYC local tax                                       $ 11,971                       │
│   ══════════════════════════════════════════════════════════                       │
│ TOTAL TAX BURDEN                                    $ 86,511                       │
│                                                                                    │
│   Effective rate (of AGI)                               25.95%                     │
│   Effective rate (of gross income)                      25.92%                     │
│   Marginal rate on next dollar (combined)               34.78%                     │
│                                                                                    │
│ Withheld + paid (projected through year end)        $ 66,450                       │
│ ▸ PROJECTED BALANCE DUE                             $ 20,061                       │
│                                                                                    │
│   ⚠  EITC: investment income exceeds the $11,950 limit                             │
│   ⚠  Tax data for 2026 is unverified (projected)                                   │
│   ⚠  State tax data (NY 2026) is unverified                                        │
│   ⚠  Safe harbor NOT met — see `ouch withhold check`                               │
╰────────────────────────────────────────────────────────────────────────────────────╯
```

$20,061 due in April. Four lines here never appear on a single-W-2 return, and
between them they explain most of the gap.

### The taxes nobody withheld

**Self-employment tax: $750.** On $28,000 of consulting income? That looks far
too low until you read the rule:

```bash
$ ouch explain fed.setax
```

```
fed.setax · $ 750 · Self-employment tax
├── Authority: IRC §1401 · Schedule SE
├── Rule: 92.35% of SE net income; SS portion limited to the wage base remaining
│   after the taxpayer's own W-2 social security wages (the wage base is per
│   person)
└── taxdata.federal.2026 (data reference)
```

Ade's W-2 has already used Ade's entire wage base ($176,100 in box 3), so the
consulting income owes **Medicare only** — $28,000 × 92.35% × 2.9% ≈ $750.

The wage base is **per person**, not per household. Chidi's wages don't count
against Ade's base. If the consulting were Chidi's (`owner = "spouse"`),
Chidi's $96,000 would leave $80,100 of base, the full 15.3% would apply, and
SE tax would be **$3,956**. This coordination trips people up in both
directions: a pleasant surprise here, an unpleasant one for a freelancer with
no W-2 (vignette 4, where the full 15.3% applies).

**Additional Medicare tax: $512.**

```
fed.medicare.additional · $ 512 · Additional Medicare tax
├── Authority: IRC §3101(b)(2) · Form 8959
├── Rule: 0.9% of Medicare wages + SE income above the threshold; employers
│   withhold only above $200k per job
```

The rule statement contains the trap. The threshold is $250,000 for a joint
return, but an *employer* only starts withholding it above $200,000 **per
job**. Neither Ade's $185k nor Chidi's $96k crosses $200k alone, so neither
payroll department withheld a cent — and the household is $56,858 over the
joint threshold. 0.9% of that is $512, due at filing.

**Net investment income tax: $939.** 3.8% on the lesser of net investment
income ($1,200 interest + $9,500 dividends + $14,000 gains = $24,700) and the
MAGI overage. No employer ever withholds NIIT. It arrives entirely at filing.

**Dual-earner under-withholding** is the quiet fourth one, and it has no line
of its own because it is not a tax — it is an arithmetic mismatch. Each
employer's withholding tables assume its own wages are the household's only
income, so each withholds as though the family earned $185k or $96k. The family
actually earns $333,700, and marginal dollars are taxed at 34.78%.

---

## 2. Diagnose the payment position

```bash
$ ouch withhold check
```

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

Two separate facts, and conflating them is the classic mistake:

1. **They will owe $20,061 in April.** That is a cash-flow event.
2. **They are $283 short of the safe harbor.** That is a *penalty* event, and
   it is tiny.

The safe harbor is the lesser of 90% of this year's tax ($51,033) and the
prior-year requirement ($64,790 — the **110%** variant, because prior-year AGI
of $268,000 exceeds the high-income threshold; under it, the test would be
100%). Pay the lesser of those and the IRS charges no underpayment penalty
regardless of what you owe at filing.

So the household has a genuine choice, not a problem with one answer.

> **If you have no prior-year figures**, the test can only run one way and
> `ouch` says so rather than guessing:
>
> ```
>   90% of current-year tax                   $ 21,933
>   Prior-year test unavailable (no prior-year figures)
>   Status: ? current-year test shortfall $ 533 (prior-year data missing)
> ```
>
> This is what vignette 3's prior-year 1040 import is for.

---

## 3. Solve for a target

The solver bisects over the full pipeline — it does not invert a formula, it
re-runs the whole computation until the balance lands where you asked.

### Option A: owe nothing in April

```bash
$ ouch withhold solve --target zero --w4
```

```
11 pay periods remain in 2026.

To reach a $0 balance:
  Federal withholding per period          $ 3,273.69
  (currently $ 1,450.00; change of $ 1,823.69 per period, $ 20,061 total)
  Resulting April balance due: $ 0

Form W-4 entries (give to ONE employer — the higher earner):
  Step 2:  ☑ check the box (multiple jobs / spouse works)
  ⚠ Dual-earner under-withholding is the most common cause of a surprise April
    bill; claim dependents on ONE W-4 only.
  Step 3:  dependents as computed on your return (1 dependent(s))
  Step 4(a) other income: $ 28,000 (self-employment)
  Step 4(c) extra withholding per pay period: $ 1,824
  ouch does not fill out or submit a W-4; enter these with your employer.
```

The W-4 block adapts to the profile. The Step 2 box and the dual-earner warning
appear *because* both spouses have W-2 wages. Step 4(a) appears *because* there
is Schedule C income. The warning about claiming dependents on one W-4 only is
there because doing it on both is how households under-withhold twice in a row.

`ouch withhold w4` is shorthand for exactly this command.

Note what the solver does **not** do: it adjusts federal withholding only. NY
and NYC withholding are read from the profile and projected forward unchanged;
the $20,061 above is the all-jurisdiction balance, closed with federal dollars.
If you want to split the fix across IT-2104 as well, model it by editing the
state per-period figure and re-running.

### Option B: avoid the penalty, keep the cash

```bash
$ ouch withhold solve --target safe-harbor
```

```
11 pay periods remain in 2026.

To reach meet the federal safe harbor (penalty avoidance only):
  Federal withholding per period          $ 1,475.72
  (currently $ 1,450.00; change of $ 25.72 per period, $ 283 total)
  Resulting April balance due: $ 19,778
```

**$26 a paycheck.** That is the entire cost of eliminating the penalty. They
will still owe $19,778 in April, but they keep that money for the next nine
months and the IRS charges nothing for the privilege.

Which option is right depends on whether they can be trusted to have $19,778 in
April. `ouch` will not decide that for them; it prices both.

### Option C: something in between

```bash
$ ouch withhold solve --target owe:5000
```

```
To reach owing $ 5,000 in April:
  Federal withholding per period          $ 2,819.15
  (currently $ 1,450.00; change of $ 1,369.15 per period, $ 15,061 total)
  Resulting April balance due: $ 5,000
```

`--target` accepts `zero`, `safe-harbor`, `owe:AMOUNT`, and `refund:AMOUNT`.
Anything else is a usage error with the list:

```
✖ unknown --target 'wat'
  → use zero, refund:AMOUNT, owe:AMOUNT, or safe-harbor
```

### What if they act later?

```bash
$ ouch withhold solve --target zero --periods-remaining 5
```

```
5 pay periods remain in 2026.

To reach a $0 balance:
  Federal withholding per period          $ 7,202.12
  (currently $ 1,450.00; change of $ 5,752.12 per period, $ 28,761 total)
```

The same $20,061, squeezed into five paychecks instead of eleven. Acting in July
costs $1,824 per period; acting in November costs $5,752. That is the argument
for running `withhold check` in the summer.

---

## 4. Why withholding, and not a quarterly payment?

They could write a Q3 estimated-payment cheque instead. Withholding is usually
the better instrument, for a reason that is pure timing:

**Withholding is treated as paid evenly across the year, no matter when it
actually happened.** A December increase in withholding retroactively counts
toward Q1. An estimated payment counts on the day it is made and cannot cure an
earlier quarter.

If you are behind and it is late in the year, the payroll department is the
faster fix. Vignette 4 shows the estimated-payment path, which is the right tool
when there is no paycheck to adjust.

---

## 5. Confirming the fix

Once the new W-4 is in effect, update the profile and re-run. A household on
track looks like this:

```
Projected total tax                         $ 24,370
Withheld to date (all jurisdictions)        $ 21,400
Projected additional withholding            $ 17,830     (10 periods × $ 1,783)
Projected total payments                    $ 39,230
────────────────────────────────────────────────────────────
Projected refund                            $ 14,861

Safe harbor analysis (federal):
  90% of current-year tax                   $ 21,933
  100% of prior-year tax                   $ 21,900
  Projected federal payments                $ 39,230
  Status: ✔ safe harbor met
```

— though a $14,861 refund is its own kind of mistake, and `withhold solve
--target zero` is the cure for that too. (Note the **100%** prior-year test
here: this filer's prior-year AGI is below the high-income threshold.)

---

## What the Okonkwos learned

- Three taxes their employers were never going to withhold: Additional
  Medicare (because the threshold is per-job for withholding but per-household
  for liability), NIIT (never withheld at all), and self-employment tax.
- The **safe harbor** is about penalties, not about owing. They were $283 from
  clearing it while $20,061 short on cash.
- `withhold solve` prices each option: $1,824 a period to owe nothing, or $26 a
  period to owe nothing *extra*.
- Acting in July costs a third of what acting in November costs.

## Try it yourself

```bash
ouch withhold check
ouch withhold solve --target refund:1000
ouch withhold w4
ouch estimate --set income.business.schedule_c_net=0     # what did the sideline cost?
ouch estimate --set income.business.owner=spouse         # if the consulting were Chidi's
ouch explain fed.niit
```

---

**Previous:** [Vignette 1 — What do I actually pay?](01-first-estimate.md) ·
**Next:** [Vignette 3 — Twelve PDFs and a coffee](03-importing-documents.md)
