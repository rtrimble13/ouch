# Vignette 4 — Freelancer, four payments a year

**Priya, 34, single, freelance industrial designer, Pennsylvania.** No W-2 at
all. About $130k of net Schedule C income, a solo 401(k), and her own health
insurance. She sends the IRS money four times a year and has never been sure
whether it is the right amount.

**Commands introduced:** `ouch withhold estimates`
**Concepts:** self-employment tax without a wage base to share · above-the-line
sequencing · QBI (§199A) · quarterly due dates · the annualized income
installment method · **which marginal rate you are actually reading**

---

## The profile

```toml
schema_version = 2
tax_year       = 2026

[taxpayer]
filing_status = "single"
birth_date    = "1992-02-11"
state         = "PA"

[income.business]
schedule_c_net      = 130000
se_health_premiums  = 7200
qbi_eligible_income = 130000

[adjustments]
sep_solo401k = 23000

[payments.estimated]
q1_federal = 5000
q2_federal = 5000

[payments.prior_year]
agi       = 118000
total_tax = 28400
```

`qbi_eligible_income` is separate from `schedule_c_net` on purpose — not every
dollar of business income is §199A-qualified, and `ouch` will not assume it is.

---

## 1. The whole picture

```bash
$ ouch estimate
```

```
╭─────────────────── ouch · Tax Year 2026 · Single · PA · fidelity: approximate ───╮
│ Total income                                       $ 130,000                     │
│ Adjusted gross income                               $ 90,616                     │
│ Deduction (standard)                              $ (15,000)                     │
│ QBI deduction                                     $ (15,123)                     │
│ Taxable income                                      $ 60,493                     │
│                                                                                  │
│ Federal income tax                                   $ 8,222                     │
│   ordinary                                             $ 8,222                   │
│ Self-employment tax                                 $ 18,368                     │
│   ──────────────────────────────────────────────────────────                     │
│ Federal total                                       $ 26,591                     │
│ PA state tax                                         $ 2,782                     │
│   ══════════════════════════════════════════════════════════                     │
│ TOTAL TAX BURDEN                                    $ 29,373                     │
│                                                                                  │
│   Effective rate (of AGI)                               32.41%                   │
│   Effective rate (of gross income)                      22.59%                   │
│   Marginal rate on next dollar (combined)               20.67%                   │
│                                                                                  │
│ Withheld + paid (projected through year end)        $ 10,000                     │
│ ▸ PROJECTED BALANCE DUE                             $ 19,373                     │
│                                                                                  │
│   ⚠  Tax data for 2026 is unverified (projected)                                 │
│   ⚠  State tax data (PA 2026) is unverified                                      │
│   ⚠  PA has local income taxes but no locality is set — local tax computed as    │
│      zero, which is probably wrong                                               │
│   ⚠  Safe harbor NOT met — see `ouch withhold check`                             │
╰──────────────────────────────────────────────────────────────────────────────────╯
```

The single largest line is **self-employment tax, $18,368** — more than double
her income tax. That is the whole story of freelancing: nobody is paying the
employer half for you.

```bash
$ ouch explain fed.setax
```

```
fed.setax · $ 18,368 · Self-employment tax
├── Authority: IRC §1401 · Schedule SE
├── Rule: 92.35% of SE net income; SS portion limited to the wage base remaining
│   after the taxpayer's own W-2 social security wages (the wage base is per
│   person)
```

$130,000 × 92.35% = $120,055 of SE net earnings, then 12.4% Social Security
plus 2.9% Medicare on all of it. Compare vignette 2, where the Okonkwos' $28,000
of consulting owed **$750** — Ade's own W-2 had already used up Ade's Social
Security wage base, so only the Medicare portion applied. Same statute, opposite
outcomes, decided entirely by whether the business owner has wages elsewhere.

### The two effective rates disagree, and both are right

- **32.41% of AGI** — because AGI is only $90,616.
- **22.59% of gross income** — because gross is $130,000.

$39,384 of above-the-line adjustments sit between the two. For anyone
self-employed, the AGI-based rate flatters nothing and overstates the burden;
the gross-income rate is the one that answers "what fraction of what I billed
went to tax."

---

## 2. Sequencing: why QBI isn't 20% of $130,000

```bash
$ ouch estimate --breakdown
```

```
fed.setax · $ 18,368 · Self-employment tax
fed.adjustments · $ 39,384 · Above-the-line adjustments
  ½ SE tax + SE health (limited to SE income) + IRA/HSA/retirement and other adjustments
fed.income.total · $ 130,000 · Total income
fed.agi · $ 90,616 · Adjusted gross income
fed.deduction · $ 15,000 · Deduction (standard)
fed.qbi · $ 15,123 · QBI deduction
  20% of qualified business income after allocable adjustments, limited to 20%
  of taxable income less net capital gain; wage/UBIA limit above the threshold
fed.taxable · $ 60,493 · Taxable income
```

The $39,384 of adjustments is ½ SE tax ($9,184) + health premiums ($7,200) +
solo 401(k) ($23,000).

Now the QBI number. Naïvely, 20% of $130,000 = $26,000. What `ouch` computes is
**$15,123**, because §199A applies two reductions in sequence:

1. **Qualified business income is reduced by the deductions attributable to
   the business** — the same ½ SE tax, health premiums, and retirement
   contribution. $130,000 − $39,384 = **$90,616**. Tentative deduction:
   20% × $90,616 = $18,123.
2. **The overall limit**: 20% of taxable income before QBI, less net capital
   gain. Taxable before QBI is $90,616 − $15,000 = $75,616, so the ceiling is
   20% × $75,616 = **$15,123**.

The ceiling binds. Priya is below the §199A threshold, so no wage or UBIA
limitation applies and her business is not tested for SSTB status — those enter
only above the threshold.

Note the feedback loop this creates: the solo 401(k) contribution *reduces* her
QBI deduction, so its net value is less than her bracket suggests. That is the
kind of interaction a spreadsheet gets wrong and a pipeline gets right.

---

## 3. The marginal rate you are reading — and the one you want

The summary says **20.67%**. That is not the cost of Priya's next $1,000 of
billings, and understanding why matters.

`ouch` measures the marginal rate by adding **$1,000 of W-2 wages** and
re-running. That is the right question for most filers and a consistent
definition across profiles — but wages carry no self-employment tax. For
Priya, the number answers "what would $1,000 of salaried income cost?"

To price the next $1,000 of *business* income, sweep the field that actually
moves:

```bash
$ ouch scenario sweep --var income.business.schedule_c_net \
                      --range 125000:135000:5000 \
                      --metric marginal_rate_combined
```

```
income.business.schedule_c_net     Total tax   Δ tax/Δ var     marginal_rate_comb
──────────────────────────────────────────────────────────────
       125,000        27,706             —                 0.2067
       130,000        29,373        33.34%                 0.2067
       135,000        31,040        33.34%                 0.2067
```

**33.34%**, not 20.67%. The `Δ tax/Δ var` column — total tax divided by the
change you actually made — is the honest answer for the change you are actually
considering. The right-hand `marginal_rate_combined` column keeps reporting the
wage-based figure, unchanged across the range, which is exactly why the two
columns are shown side by side.

Rule of thumb: **`Δ tax/Δ var` prices the decision in front of you; the summary's
marginal rate prices a hypothetical extra dollar of wages.**

---

## 4. Where she stands on payments

```bash
$ ouch withhold check
```

```
Projected total tax                         $ 29,373
Withheld to date (all jurisdictions)             $ 0
Projected additional withholding                 $ 0     (10 periods × $ 0)
Estimated payments                          $ 10,000
Projected total payments                    $ 10,000
────────────────────────────────────────────────────────────
Projected balance due                       $ 19,373

Safe harbor analysis (federal):
  90% of current-year tax                   $ 23,932
  100% of prior-year tax                   $ 28,400
  Projected federal payments                $ 10,000
  Status: ✗ SHORT by $ 13,932
  Estimated underpayment penalty               $ 557   (Form 2210 approximation)
```

Two things to notice.

**The prior-year test is 100%, not 110%**, because her prior-year AGI of
$118,000 is under the high-income threshold. The Okonkwos in vignette 2 faced
110%. `ouch` picks the applicable variant from the data file rather than making
you remember which one you are.

**Here the current-year test is the cheaper one** — $23,932 versus $28,400 —
which is the opposite of the usual advice. It happens whenever this year's
income is *lower* than last year's. The safe harbor is the lesser of the
applicable tests, and `ouch` uses whichever that is.

---

## 5. The quarterly schedule

```bash
$ ouch withhold estimates
```

```
2026 quarterly estimated payments (federal)

  90% of current-year tax             $ 23,932
  100% of prior-year tax            $ 28,400
  Withholding (counted as even)            $ 0
  Required via estimates              $ 23,932   (target: safe-harbor)

  Q1  due 2026-04-15        $ 5,983   due  (paid $ 5,000)
  Q2  due 2026-06-15        $ 5,983   due  (paid $ 5,000)
  Q3  due 2026-09-15        $ 5,983   due
  Q4  due 2027-01-15        $ 5,983   due

  ℹ Income lumpy? `--annualized` with payments.annualized_income_fractions
    shifts the requirement toward the quarters that earn the income.
```

Statutory due dates, including the one everyone forgets: **Q4 is due in
January of the following year.**

Her $5,000 payments were each $983 short. The `(paid $ 5,000)` annotation
tracks what the profile records against what each quarter needed.

Note `Withholding (counted as even)`: $0 here, but if Priya also had a
part-time W-2 job, withholding from it would be credited **evenly across all
four quarters regardless of when it happened**. That asymmetry is why an
employed spouse's W-4 is often the cheapest fix for a freelancer's shortfall.

### Target the balance instead of the penalty

```bash
$ ouch withhold estimates --target zero
```

```
  Required via estimates              $ 26,591   (target: zero)

  Q1  due 2026-04-15        $ 6,648   due  (paid $ 5,000)
  Q2  due 2026-06-15        $ 6,648   due  (paid $ 5,000)
  Q3  due 2026-09-15        $ 6,648   due
  Q4  due 2027-01-15        $ 6,648   due
```

The default target is `safe-harbor` — the minimum that avoids a penalty. Pass
`--target zero` and `ouch` sizes the payments to leave nothing owing in April
instead: $26,591 rather than $23,932, or **$665 more per quarter**.

(The `zero` target covers her *federal* total of $26,591. `withhold estimates`
schedules federal payments only; PA's $2,782 is a separate remittance to the
state.)

That is a cash-flow decision, and again `ouch` prices both rather than picking.

---

## 6. When income is lumpy

Freelance income is rarely four equal quarters. Priya bills a fifth of her year
by June and half of it in the autumn. Paying 25% in April is lending money to
the IRS.

The **annualized income installment method** lets the requirement follow the
income. Declare when you actually earn it:

```toml
[payments]
annualized_income_fractions = ["0.10", "0.15", "0.25", "0.50"]
```

Four fractions, one per period, summing to 1.00 (± 0.01 — `ouch` validates it).

```bash
$ ouch withhold estimates --annualized
```

```
2026 quarterly estimated payments (federal)

  90% of current-year tax             $ 23,932
  100% of prior-year tax            $ 28,400
  Withholding (counted as even)            $ 0
  Required via estimates              $ 23,932   (target: safe-harbor)

  Q1  due 2026-04-15        $ 2,393   ✔ paid  (paid $ 5,000)
  Q2  due 2026-06-15        $ 3,590   ✔ paid  (paid $ 5,000)
  Q3  due 2026-09-15        $ 5,983   due
  Q4  due 2027-01-15       $ 11,966   due

  ℹ Annualized income installment method: payments follow your income fractions
    (approximate — the statutory Schedule AI factors are not applied).
```

Same annual total, redistributed. Q1 drops from $5,983 to $2,393, and her
existing $5,000 payments now **clear** the first two quarters instead of falling
short. The money moves to Q4, where the income actually is.

Read the fidelity note: this follows *your* declared fractions, not the
statutory Schedule AI factors. It is the right shape and an approximate
magnitude. Treat it as planning guidance and let your preparer compute the
actual Form 2210 Schedule AI.

Two guardrails:

```bash
$ ouch withhold estimates --annualized      # without the fractions in the profile
```

```
✖ --annualized needs payments.annualized_income_fractions in the profile
  → e.g. annualized_income_fractions = ["0.1","0.2","0.3","0.4"]
```

And the reverse: if the fractions *are* in the profile but you omit
`--annualized`, they are ignored for that run. The flag is the switch, not the
data.

---

## 7. The missing locality

```
⚠ PA has local income taxes but no locality is set — local tax computed as
  zero, which is probably wrong
```

Pennsylvania municipalities levy an earned income tax, and Philadelphia's is
substantial. `ouch` ships local data for NYC only, so Priya's local line is
silently zero — and `ouch` refuses to let that pass without saying so.

The fix is to write the data file yourself; it takes about ten lines. Vignette
10 walks through it, and the result is a real local line:

```
│ PA state tax                                         $ 2,782       │
│ PHL local tax                                        $ 3,398       │
│   ══════════════════════════════════════════════════════════       │
│ TOTAL TAX BURDEN                                    $ 32,771       │
```

$3,398 that was invisible a moment ago. This is the general lesson about
data-driven jurisdictions: a missing file is a missing tax, and `ouch` warns
rather than pretending.

---

## What Priya learned

- Self-employment tax is her biggest single line, because there is no W-2 wage
  base to share.
- Her QBI deduction is $15,123, not $26,000 — business-allocable adjustments
  reduce QBI first, then the taxable-income ceiling binds. Her solo 401(k)
  partly cannibalises it.
- The summary's marginal rate prices **wages**. For the next dollar of
  *business* income, read `Δ tax/Δ var` from a sweep: 33.34%, not 20.67%.
- Her safe harbor is the **current-year** test this year, because her income
  fell.
- `--annualized` moves the requirement to the quarters that earn the income —
  and turned two short payments into two paid ones.

## Try it yourself

```bash
ouch withhold estimates --target zero
ouch explain fed.qbi
ouch estimate --set adjustments.sep_solo401k=0        # what is the 401(k) worth?
ouch scenario sweep --var adjustments.sep_solo401k --range 0:30000:5000
ouch estimate --set income.business.sstb=true         # no effect below the §199A threshold
```

---

**Previous:** [Vignette 3 — Twelve PDFs and a coffee](03-importing-documents.md) ·
**Next:** [Vignette 5 — Should we convert to Roth?](05-scenarios-and-sweeps.md)
