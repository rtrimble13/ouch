# Vignette 7 — The refund that isn't a refund

**Kim Nguyen, 36, head of household, California.** Two children — one in
primary school, one starting community college — $52,000 of wages, daycare
costs, and a small IRA contribution. She withheld $2,600 all year and is
bracing for a bill.

**Commands introduced:** none new — this vignette is about reading `estimate
--breakdown` properly
**Concepts:** the ordered credit cascade · nonrefundable vs refundable · the
liability limit · phase-outs and one genuine cliff · negative tax

---

## The profile

```toml
schema_version = 2
tax_year       = 2026

[taxpayer]
filing_status = "head_of_household"
birth_date    = "1990-08-12"
state         = "CA"

[[dependents]]
name         = "child 1"
birth_date   = "2019-03-08"
relationship = "child"

[[dependents]]
name         = "child 2"
birth_date   = "2007-10-02"
relationship = "child"
student      = true

[income.wages]
taxpayer_w2       = 52000
taxpayer_ss_wages = 52000

[income.investment]
interest = 300

[adjustments]
traditional_ira = 2500

[expenses]
dependent_care = 6000
education_aotc = 4000

[payments.withholding]
federal_ytd          = 2600
state_ytd            = 700
federal_per_period   = 110
pay_periods_per_year = 24

[payments.prior_year]
agi       = 49000
total_tax = 2100
```

Two things `ouch` needs and people routinely omit:

- **`birth_date` on every dependent.** Age drives everything here: the child tax
  credit tests age ≤ 16, the dependent-care credit tests age ≤ 12, the EITC
  tests under 19 (or under 24 with `student = true`). Without a birth date those
  tests cannot run.
- **`[expenses]`.** Credit-qualifying expenditure lives in its own section
  because it is not a deduction — `dependent_care`, `education_aotc`, and
  `education_llc` feed credits, not AGI.

---

## 1. The headline

```bash
$ ouch estimate
```

```
╭─ ouch · Tax Year 2026 · Head of Household · CA · fidelity: approximate ─╮
│ Total income                                        $ 52,300            │
│ Adjusted gross income                               $ 49,800            │
│ Deduction (standard)                              $ (22,500)            │
│ Taxable income                                      $ 27,300            │
│                                                                         │
│ Federal income tax                                   $ 2,936            │
│   ordinary                                             $ 2,936          │
│ Credits                                            $ (6,754)            │
│   ──────────────────────────────────────────────────────────            │
│ Federal total                                      $ (3,818)            │
│ CA state tax                                           $ 559            │
│   ══════════════════════════════════════════════════════════            │
│ TOTAL TAX BURDEN                                   $ (3,259)            │
│                                                                         │
│   Effective rate (of AGI)                               -6.54%          │
│   Effective rate (of gross income)                      -6.23%          │
│   Marginal rate on next dollar (combined)               23.06%          │
│                                                                         │
│ Withheld + paid (projected through year end)         $ 4,400            │
│ ▸ PROJECTED REFUND                                   $ 7,659            │
│                                                                         │
│   ⚠  $164 of child/dependent credit lost to the liability limit         │
│   ⚠  Tax data for 2026 is unverified (projected)                        │
│   ⚠  State tax data (CA 2026) is unverified                             │
╰─────────────────────────────────────────────────────────────────────────╯
```

A **negative** federal total and a **-6.54% effective rate**. That is not a
display bug: refundable credits can push liability below zero, and the federal
government pays Kim $3,818 on top of returning her withholding.

Her $7,659 refund is therefore two different things stacked together: $4,400 of
her own money coming back, and $3,259 of net transfer. Only one of those is
worth adjusting a W-4 over.

Note also the **23.06% marginal rate** on a $27,300 taxable income. She is
nominally in the 12% bracket. The extra 11 points are credits phasing out — the
most under-appreciated marginal rate in the code, and one a bracket table cannot
show you.

---

## 2. The cascade, line by line

```bash
$ ouch estimate --breakdown
```

```
fed.tax.ordinary · $ 2,936 · Ordinary income tax
  progressive brackets applied to ordinary taxable income, computed as if
  preferential income did not exist
fed.credits.care · $ 600 · Child and dependent care credit
  nonrefundable credit, clamped to remaining liability
fed.credits.aotc · $ 1,500 · American opportunity credit (nonrefundable 60%)
  nonrefundable credit, clamped to remaining liability
fed.credits.saver · $ 200 · Saver's credit
  nonrefundable credit, clamped to remaining liability
fed.credits.ctc · $ 636 · Child tax credit / odc
  nonrefundable credit, clamped to remaining liability
fed.credits.aotc_refundable · $ 1,000 · American opportunity credit (refundable 40%)
  refundable credit
fed.credits.actc · $ 1,700 · Additional child tax credit
  refundable credit
fed.credits.eitc · $ 1,118 · Earned income credit
  refundable credit
fed.tax.total · $ -3,818 · Federal total tax
  income tax + AMT + SE tax + Additional Medicare + NIIT − credits
```

**The order is the point.** Nonrefundable credits are applied in sequence, each
clamped to what is left of the liability:

| Step | Credit | Amount | Liability left |
|---|---|---|---|
| — | Ordinary income tax | | $2,936 |
| 1 | Child and dependent care | $600 | $2,336 |
| 2 | AOTC, nonrefundable 60% | $1,500 | $836 |
| 3 | Saver's credit | $200 | $636 |
| 4 | Child tax credit / ODC | **$636** | **$0** |

Then refundable credits are applied, and they may drive the total negative:

| | Credit | Amount |
|---|---|---|
| 5 | AOTC, refundable 40% | $1,000 |
| 6 | Additional child tax credit | $1,700 |
| 7 | Earned income credit | $1,118 |
| | **Refundable total** | **$3,818** |

CTC is applied **last** among the nonrefundable credits on purpose: its
refundable spill-over (the ACTC) is computed on whatever residue survives the
liability clamp, so putting it last maximises what can be recovered.

### Where the $164 warning comes from

```
⚠ $164 of child/dependent credit lost to the liability limit
```

Kim's gross child credit is $2,500 — $2,000 for the seven-year-old plus $500 of
other-dependent credit for the nineteen-year-old, who is over the CTC age limit
of 16 but still a dependent. Only $636 of liability remained when CTC's turn
came, leaving $1,864 of residue. The ACTC recovered $1,700 of that (the per-child
refundable cap). The last **$164 simply evaporates** — nonrefundable credit with
no liability to offset and no refundable route.

`ouch` says so rather than quietly netting it away, because it is exactly the
kind of thing worth planning around: another $164 of tax liability this year
would have cost her nothing.

---

## 3. Reading each credit

### Child and dependent care — $600 on $6,000 of expenses

Two limits bite. Only the **seven-year-old** counts (the age test is ≤ 12), so
the expense cap is the one-child figure of $3,000, not $6,000. Then the credit
rate slides from 35% down as AGI rises, one point per $2,000 above $15,000 —
which at $49,800 of AGI has long since hit the 20% floor.

$3,000 × 20% = **$600**. The other $3,000 of daycare spending earns nothing.

### AOTC — split 60/40 by statute

$4,000 of qualified education expenses gives 100% of the first $2,000 plus 25%
of the next $2,000 = **$2,500**. The American Opportunity credit is 40%
refundable by law, so `ouch` reports it as two lines: $1,500 nonrefundable
(entering the cascade at step 2) and $1,000 refundable (step 5). That split is
why the AOTC is worth having even with no liability left.

Its cousin, the Lifetime Learning credit (`expenses.education_llc`), is 20% of
up to $10,000 and entirely nonrefundable.

### Saver's credit — $200

$2,500 of IRA contribution, capped at the $2,000 contribution ceiling, times the
rate for her AGI tier. At $49,800 as head of household she is in the **10%**
band; below $38,250 it would be 20%, and below $35,625 it would be **50%**.

That is a genuine planning lever. Fidelity here is `approximate` — full-time
student and dependent exclusions and recent-distribution offsets are not
modeled.

### Child tax credit — one child, one other dependent

`qualifying_age_max` is 16, so the nineteen-year-old college student is an
"other dependent" worth $500, not a child worth $2,000. Phase-out starts at
$200,000 of AGI for head of household — irrelevant here, but it is why a
high-income household sees this line shrink by $50 per $1,000 of excess AGI.

You can override the engine's test per dependent with
`qualifies_ctc = true` / `false` when you know something it cannot see.

### EITC — a trapezoid, and one real cliff

The EITC phases **in** on earned income, **plateaus**, then phases **out** on
the greater of earned income and AGI. Kim is on the phase-out slope, which is a
large part of that 23.06% marginal rate.

It also carries the sharpest edge in the whole credit suite: an
**investment-income limit** that is a genuine cliff, not a phase-out. Below the
threshold you get the credit; one dollar over, you get nothing.

```bash
$ ouch estimate --set income.wages.taxpayer_w2=22000 --set income.investment.interest=11900
$ ouch estimate --set income.wages.taxpayer_w2=22000 --set income.investment.interest=12000
```

```
interest = 11,900  →  ▸ PROJECTED REFUND  $ 12,353
interest = 12,000  →  ▸ PROJECTED REFUND  $  6,896
```

**$100 of extra interest costs $5,457.** The trace shows the credit at $5,457
in the first run and gone entirely in the second, replaced by a warning:

```
⚠ EITC: investment income exceeds the $11,950 limit
```

An effective marginal rate of 5,457% on that hundred dollars. `ouch` computes
marginal rates numerically precisely so edges like this are visible instead of
theoretical.

(You may see that EITC warning on a high-income profile too, as the Okonkwos did
in vignette 2. It is stating why the credit is zero, not implying you were close
to qualifying.)

---

## 4. Mapping the phase-out region

Credits make the marginal rate curve strange. Sweep it:

```bash
$ ouch scenario sweep --var income.wages.taxpayer_w2 --range 20000:80000:10000 \
                      --metric marginal_rate_combined
```

```
income.wages.taxpayer_w2     Total tax   Δ tax/Δ var     marginal_rate_comb
──────────────────────────────────────────────────────────────
        20,000        -9,785             —                 0.0100
        30,000        -8,284        15.00%                 0.2206
        40,000        -6,026        22.58%                 0.2306   ⚠ cliff
        50,000        -3,720        23.06%                 0.2306
        60,000        -1,185        25.36%                 0.1400
        70,000           530        17.14%                 0.1600
        80,000         2,149        16.20%                 0.1800
```

Read the `Δ tax/Δ var` column top to bottom. The cost of each extra $10,000 of
wages **rises** from 15% to 25.36%, then **falls** to 17.14% and 16.20%. That is
not a bracket doing that — brackets only go up. It is the EITC and the
dependent-care rate phasing out through the middle of the range and finishing
around $60,000, after which the ordinary rate schedule takes over alone.

Total tax stays negative until somewhere between $60,000 and $70,000. A
household in this region can face a higher marginal cost on additional income
than one earning three times as much — which is the single most useful thing
`ouch` can show a family in it.

---

## 5. What to do with it

Kim's $7,659 refund is mostly her own over-withholding. `ouch withhold solve
--target zero` would move about $2,600 of it into her paychecks, where it is
useful in March rather than the following April.

The planning items the trace surfaces:

- **$164 of credit is being lost** to the liability limit.
- **$3,000 of daycare spending earns nothing**, because only one child passes
  the age-12 test.
- **The saver's credit rate is tiered at 10% / 20% / 50%** by AGI, and she is in
  the lowest band. An above-the-line deduction that lowers AGI could be worth
  far more than its bracket value by moving her a tier.
- **Investment income has a hard EITC cliff.** Worth knowing before moving cash
  into a taxable account.

---

## What Kim learned

- Nonrefundable credits apply **in order** and are clamped to remaining
  liability; refundable ones apply after and can go negative. `--breakdown`
  shows the exact sequence.
- The AOTC's 60/40 split is why it still pays when liability hits zero.
- Her marginal rate is **23.06%**, roughly double her bracket, because credits
  are phasing out.
- The EITC investment-income limit is a **cliff**: $100 of interest cost $5,457
  in the modelled case.
- Ages on dependents are load-bearing — 12 for care, 16 for CTC, 19/24 for
  EITC.

## Try it yourself

```bash
ouch estimate --breakdown
ouch explain fed.credits.eitc
ouch estimate --set expenses.dependent_care=3000        # identical result: the extra $3k earns nothing
ouch scenario sweep --var adjustments.traditional_ira --range 0:7000:500
ouch estimate --set expenses.education_llc=10000       # add a Lifetime Learning claim
```

> `--set` and scenario patches address **tables**, not list elements.
> `--set dependents.0.birth_date=...` fails with
> `'dependents' is not a table` — edit the dependent in the profile instead.

---

**Previous:** [Vignette 6 — December, and a losing position](06-harvesting-losses.md) ·
**Next:** [Vignette 8 — Half a year in two states](08-moving-states.md)
