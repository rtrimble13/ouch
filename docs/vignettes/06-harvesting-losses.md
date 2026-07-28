# Vignette 6 — December, and a losing position

**Sam, 44, married filing jointly, Massachusetts.** He realized $22,000 of
short-term gains in March from a position he now regrets, and his taxable
brokerage account holds several lots underwater. It is 12 December.

**Commands introduced:** `ouch harvest import / scan / simulate /
washsale-check`
**Concepts:** the lot CSV · wash sales including DRIP and IRA traps · benefit by
pipeline re-run, not multiplication · the statutory netting order · deferred
cost and NPV · gain harvesting in the 0% band

---

## First, the honesty

`ouch harvest` is **analysis, not execution**. It never connects to a
brokerage, never places a trade, and never sees a live price. You give it a
CSV; it tells you what selling would do to your tax. Everything after that is
your broker's job and your decision.

---

## 1. Get your lots in

`ouch` reads one canonical CSV. Export from your broker and map the columns
yourself:

```csv
account,symbol,lot_id,quantity,acquired_date,cost_basis,current_price,as_of,asset_class,is_ira
Taxable-Brokerage,ARKG,L-0217,400,2026-05-14,32800,46.50,2026-12-12,equity,false
Taxable-Brokerage,VXUS,L-0431,410,2026-08-02,24600,39.90,2026-12-12,equity,false
Taxable-Brokerage,VXUS,L-0498,3.114,2026-11-28,120.15,39.90,2026-12-12,equity,false
Taxable-Brokerage,BND,L-0388,300,2026-03-09,22800,66.15,2026-12-12,bond,false
Taxable-Brokerage,IEFA,L-0155,250,2024-09-18,18400,49.20,2026-12-12,equity,false
Taxable-Brokerage,VTI,L-0102,150,2026-01-20,38000,289.40,2026-12-12,equity,false
Taxable-Brokerage,NVDA,L-0501,60,2026-02-04,9600,214.00,2026-12-12,equity,false
Rollover-IRA,IEFA,L-9001,500,2026-12-01,24000,49.20,2026-12-12,equity,true
Rollover-IRA,ARKG,L-9002,200,2026-06-10,17000,46.50,2026-12-12,equity,true
```

Two column conventions to get right: **`cost_basis` is the total for the lot**,
not per share, while **`current_price` is per share**. And **include your IRA
lots** — `ouch` excludes them from harvesting, but it needs to see them to catch
the wash-sale trap in step 3.

Note `L-0498`: 3.114 shares of VXUS bought on 28 November. That is a dividend
reinvestment, and it is about to matter a great deal.

```bash
$ ouch harvest import ~/lots.csv
```

```
✔ 9 lots imported to ~/.local/share/ouch/portfolio/lots.csv
  ℹ 2 IRA lot(s) will be excluded from harvesting — a loss there has no tax value
```

Validation reports every bad row at once, with line numbers:

```
✖ lot file failed validation (2 errors) — bad.csv
  line 2: quantity must be positive
  line 3: quantity 'x' is not a number
```

Missing columns produce the canonical header so you can fix the export:

```
✖ bad2.csv: missing columns: lot_id, quantity, acquired_date, cost_basis, current_price, as_of
  → canonical header: account,symbol,lot_id,quantity,acquired_date,cost_basis,
    current_price,as_of,asset_class,is_ira
```

`--dry-run` validates without installing.

---

## 2. Scan

```bash
$ ouch harvest scan --as-of 2026-12-12
```

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
  ⚠ NVDA L-0501: gain lot crosses the long-term boundary in 55 days — waiting
    changes the rate from short-term to long-term.

  Substantially-identical analysis covers exact symbol matches only (fidelity: approximate).
```

### The rates in the header

**ST 32.80% / LT 23.80%** are not read from a table. `ouch` re-runs the whole
pipeline with $1,000 more short-term gain, then with $1,000 more long-term
gain, and measures. For Sam they decompose as 24% + 3.8% NIIT + 5% MA, and 15% +
3.8% + 5%.

The **9-point spread between the two** is the actual opportunity here, and step
4 comes back to it.

### The benefit column is a re-run, not a multiplication

`$4,658` on a `$14,200` loss is 32.8% — this time it happens to match the
marginal rate, because Sam has plenty of short-term gain to absorb it. It will
*not* match once the $3,000 ordinary-offset limit or a character mismatch binds.
`ouch` computes:

```
benefit = tax(baseline) − tax(baseline with the loss realized)
```

through the full pipeline, so the ordinary-offset cap, character matching,
NIIT, and state treatment are all accounted for automatically instead of being
approximated.

### The two wash-sale flags

**Lot 2, VXUS.** A dividend reinvestment bought 3.114 shares on 28 November,
inside the ±30-day window around a 12 December sale. Under §1091 the loss is
disallowed **pro rata by shares repurchased**: 3.114 of 410 shares, so $63 of
the $8,241 loss. The remaining $8,178 is harvestable. The fix is to turn off
automatic reinvestment for 31 days — DRIP is the single most common way people
accidentally trigger a wash sale, because nobody thinks of it as a purchase.

**Lot 3, IEFA.** Sam bought IEFA in his Rollover IRA on 1 December. This is the
one that hurts:

> When the replacement purchase happens inside an IRA, the loss is
> **permanently disallowed** — not merely deferred. In a taxable account, a
> wash sale moves the disallowed loss into the basis of the replacement shares,
> so you get it back eventually. Inside an IRA there is no basis to adjust. The
> deduction is gone.

`ouch` marks that case `✖ … PERMANENTLY` rather than the ordinary `⚠`, because
the two are not the same kind of problem.

**Lot L-9002** was excluded outright: it is an IRA lot, and a loss inside an IRA
has no tax value in the first place.

### Holding-period alerts

Two gain lots cross the one-year boundary within 60 days. Selling VTI on 12
December is a short-term gain at 32.80%; selling it on 21 January is long-term
at 23.80%. `ouch` flags them because "wait five weeks" is often worth more than
anything on the harvest list.

### Filter the noise

```bash
$ ouch harvest scan --as-of 2026-12-12 --min-benefit 1500
```

Hides candidates whose benefit doesn't justify the trade.

---

## 3. Check the windows explicitly

```bash
$ ouch harvest washsale-check --as-of 2026-12-12
```

```
  ⚠ VXUS L-0431: 3.114 sh purchased 2026-11-28 in Taxable-Brokerage — $63 of the
    loss disallowed if sold 2026-12-12
  ⚠ IEFA L-0155: 500 sh purchased 2026-12-01 in Rollover-IRA (IRA — permanent) —
    $6,100 of the loss disallowed if sold 2026-12-12
```

Every loss lot, every conflict, the account each replacement sits in, and
whether the disallowance is permanent. With no conflicts you get:

```
  ✔ no wash-sale conflicts for sales on 2026-12-12 (exact-symbol matches only)
```

Read that parenthetical. **`ouch` matches on exact symbol only.** Selling VTI
and buying ITOT the same day may well be "substantially identical" in the
Service's view; that is a legal judgment, and `ouch` declines to make it rather
than giving you false comfort. Cross-issuer equivalence is on you.

Also note what `ouch` cannot see: a purchase you make *after* today, inside the
forward half of the window. Hence the closing warning on every simulation.

---

## 4. Simulate the actual trade

Sam picks the two clean lots.

```bash
$ ouch harvest simulate --sell L-0217 --sell L-0388 --as-of 2026-12-12
```

```
Simulated sale of 2 lot(s) on 2026-12-12

  Short-term realized                     $ (17,155)
  Long-term realized                             $ 0

  Tax effect:
                                  Before       After           Δ
    Federal                     $ 68,532    $ 63,763   $ (4,769)
    State (MA)                  $ 18,490    $ 17,632     $ (858)
    Total tax                   $ 87,022    $ 81,396   $ (5,627)

  Deferred cost (harvesting is largely a deferral):
    Basis reduction                           $ 17,155
    Future tax at assumed 23.80%               $ 4,083
    Net present benefit @ 5% / 10 yr             $ 3,120

  ⚠ Do not repurchase these securities before 2027-01-12 (and turn off dividend
    reinvestment).
```

### The deferred-cost block is the honest part

$5,627 saved today looks like free money. It is not, and `ouch` says so on the
same screen rather than in a footnote.

Selling reduces the basis of what Sam will eventually own by $17,155. When those
gains are finally realized, they will be taxed. At an assumed 23.80% that is
$4,083 of future tax. Discounted at 5% over 10 years, the **net present
benefit** is $3,120 — a bit over half the headline number.

You control all three assumptions:

```bash
ouch harvest simulate --sell L-0431 --sell L-0155 --as-of 2026-12-12 \
                      --future-rate 0.15 --discount-rate 0.06 --horizon 20
```

```
    Basis reduction                           $ 14,341
    Future tax at assumed 15.00%               $ 2,151
    Net present benefit @ 6% / 20 yr             $ 3,754
```

A longer horizon and a lower assumed future rate make deferral look better —
which is exactly the sensitivity worth knowing before you trade.

### Where the value actually is

Harvesting is *mostly* deferral. The part that is not deferral is **character
arbitrage**: Sam is converting short-term gain taxed at **32.80%** into future
long-term gain taxed at **23.80%**. That 9-point spread is a permanent saving,
not a timing one. It is why harvesting against short-term gains is worth much
more than harvesting against long-term gains, and why the header prints both
rates.

### The netting walk

Sell more and the statutory ordering (IRC §1211) becomes visible:

```bash
$ ouch harvest simulate --sell L-0217 --sell L-0431 --sell L-0388 --as-of 2026-12-12
```

```
  Short-term realized                     $ (25,396)
  Long-term realized                             $ 0
  Loss applied against ordinary income       $ (296)   (limited)

  Tax effect:
                                  Before       After           Δ
    Federal                     $ 68,532    $ 61,751   $ (6,781)
    State (MA)                  $ 18,490    $ 17,220   $ (1,270)
    Total tax                   $ 87,022    $ 78,972   $ (8,051)
```

$25,396 of short-term losses against $22,000 of short-term gains and $3,100 of
long-term gains leaves $296 with nowhere to go, so it offsets ordinary income.
The `(limited)` marker names the line: this is the ordinary-offset bucket, which
statute caps at $3,000 a year ($1,500 filing separately). It is printed whenever
any loss reaches ordinary income, not only when the cap binds — here $296 is
comfortably under it. Anything beyond the cap carries forward with its character
preserved, and `ouch` reports the carryforward when one exists.

That $296 saved tax at Sam's ordinary marginal rate, not at a capital rate. Push
further and the marginal value of each extra dollar of harvested loss collapses
once the gains are used up — which is precisely why the benefit column comes
from a pipeline re-run and not from `loss × rate`.

### Guardrails

```bash
$ ouch harvest simulate --sell L-9001
```

```
✖ lot(s) in IRA accounts cannot be harvested: L-9001
  → a loss inside an IRA has no tax value
```

```bash
$ ouch harvest simulate --sell NOPE
```

```
✖ unknown lot id(s): NOPE
  → see `ouch harvest scan` for lot ids
```

And when a lot with a live wash-sale conflict is in the sale, the simulation
tells you its own numbers are optimistic:

```
  ⚠ VXUS L-0431: 3.114 share(s) repurchased inside the window — $63 of the loss
    would be disallowed. The pipeline figures above assume the FULL loss; clear
    the window first.

  ✖ IEFA L-0155: an IRA purchase inside the ±30-day window PERMANENTLY
    disallows $6,100 of the loss — the basis adjustment has nowhere to go.
```

---

## 5. The other direction: harvesting gains

Losses are not the only thing worth realizing. Run `scan` against a low-income
profile and a different note appears:

```
  ℹ Gain harvesting: $ 37,450 of room remains in the 0% preferential band —
    long-term gains realized up to that amount are taxed at 0% federally.
```

That is the head-of-household 0% ceiling of $64,750 less $27,300 of taxable
income. This is vignette 1's lesson turned into a tool: the 0% preferential band
is measured **from the floor set by ordinary income**, so a low-income year leaves
room to realize long-term gains at zero federal tax and immediately repurchase —
stepping basis up for free. There is no wash-sale rule on *gains*; §1091 applies
only to losses.

A sabbatical, a gap between jobs, an early-retirement year before Social
Security starts: `ouch harvest scan` will quantify the room.

---

## What Sam learned

- His DRIP quietly created a wash sale. 3.114 reinvested shares disallowed $63,
  and turning off reinvestment for 31 days clears it.
- His IRA purchase of the same fund would **permanently** destroy a $6,100
  deduction — a different and worse problem than an ordinary wash sale.
- The benefit numbers come from re-running the whole return, so the
  ordinary-offset cap and character matching are already in them.
- Of $5,627 saved today, about **$3,120** survives as net present benefit. The
  durable part is the 32.80% → 23.80% character arbitrage, not the deferral.
- Two gain lots cross into long-term treatment within 60 days, and waiting is
  worth about 9 points on each.

## Try it yourself

```bash
ouch harvest scan --as-of 2026-06-30                  # mid-year view
ouch harvest simulate --sell L-0217 --horizon 30      # long deferral horizon
ouch harvest simulate --sell L-0217 --future-rate 0.238
ouch harvest washsale-check --as-of 2027-01-15        # after the window closes
ouch --dry-run harvest import lots.csv                # validate only
```

---

**Previous:** [Vignette 5 — Should we convert to Roth?](05-scenarios-and-sweeps.md) ·
**Next:** [Vignette 7 — The refund that isn't a refund](07-credits-and-dependents.md)
