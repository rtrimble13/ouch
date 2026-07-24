# PR Review — rtrimble13/ouch#1: Implement ouch M1–M5

**Verdict: Approve with comments** (two High findings worth fixing before or
shortly after merge; no data-loss/security blockers found).

Reviewed the full diff (~15k added lines across engine, data, CLI, agent, and
tests) with emphasis on the pure calculation engine, since a planning tool's
failure mode is a *plausible wrong number*. The architecture holds up well:
the pure-core/imperative-shell split is real (no I/O or clock in `engine/`),
money is Decimal throughout with explicit rounding, every number lands in a
DAG-verified trace, and the 186 tests are largely hand-computed rather than
self-referential. The findings below are ordered by severity; the two High
items are silent-understatement paths that conflict with the spec's own P5
("fail loudly, never silently guess").

---

## High

### H1. Additional Medicare tax uses SS wages (box 3) as Medicare wages — silently understated above the wage base
`ouch/engine/pipeline.py:126-128, 320`

`ss_wages` (W-2 box 3, legally capped at the $176,100 wage base) is passed to
`setax.additional_medicare()` as the Medicare-wage base. Medicare wages
(box 5) are **uncapped**. Verified empirically: a single filer with $300,000
of box-1 wages and a correct box-3 value of $176,100 computes **$0** of
Additional Medicare tax instead of **$900**. The default path (`ss_wages =
wages` when box 3 is absent) is accidentally correct — but the PDF importer
*writes* box 3 (`pdf/maps/w2.yaml` box "3"), so precisely the users who
import real W-2s hit the wrong path. The spec (§9.7) even calls this tax out
as a common surprise; here the tool itself would miss it.

**Fix:** use box-1 wages as the Medicare-wage proxy in the Additional
Medicare computation (box 5 ≥ box 1 in almost all cases; a dedicated
`medicare_wages` profile field would be exact), keep box 3 only for the SS
wage-base coordination.

### H2. Schedule C losses are silently dropped from income
`ouch/engine/pipeline.py:193`

`income_ex_ss = wages + maxm(se_net, ZERO) + …` floors self-employment income
at zero, so a legitimate Schedule C **loss** never reduces total income or
AGI — overstating tax for anyone with a loss year. Flooring is correct for SE
*tax* and for QBI/earned-income purposes, but not for income aggregation
(Schedule 1 line 3 takes the loss). No warning or fidelity note discloses
this. **Fix:** include `se_net` unfloored in income aggregation (hobby-loss
and at-risk limits can stay out of scope with a disclosed warning), or at
minimum emit a loud warning when `schedule_c_net < 0`.

---

## Medium

### M1. Dependent care credit uses household earned income, not the lesser-earning spouse's
`ouch/engine/credits.py:220`

§21(d) limits qualifying expenses to the **lesser** of each spouse's earned
income; a one-earner MFJ household is statutorily entitled to $0, but this
computes the full credit. Unlike the neighboring EITC/saver's functions, the
docstring carries no approximation disclosure. **Fix:** per-spouse earned
income isn't currently in the profile, so either derive it (taxpayer vs
spouse W-2 fields exist) or disclose the approximation and warn when
`spouse_w2 == 0` for MFJ.

### M2. Saver's credit counts SEP/solo-401(k) employer contributions
`ouch/engine/credits.py:294`

`sep_solo401k` is included in the contribution base, but §25B covers elective
deferrals and IRA contributions — SEP *employer* contributions don't qualify.
The field name spans both employee deferrals and employer contributions, so
this can overstate the credit by up to $2,000 × rate. **Fix:** restrict the
base to `traditional_ira` (conservative), or split the profile field, and add
the approximation to the docstring's disclosure list.

### M3. Wash-sale check counts replacement lots that are themselves being sold
`ouch/harvest/washsale.py:69`

Only the sale lot itself is excluded from the conflict scan. In
`harvest simulate --sell A --sell B` where B *is* the recent repurchase of
A's security, B's purchase still flags A's loss as disallowed — but selling
the replacement shares in the same disposition means there is no wash. The
smoke-test scenario (selling VXUS L-0431 *and* L-0900 together) would show a
$626 disallowance that doesn't statutorily apply, potentially deterring a
legitimate harvest. **Fix:** in `simulate`, exclude lots in the sale set from
each other's conflict windows (a replacement that is fully disposed of in the
same transaction isn't a replacement).

---

## Low

### L1. No guard against `former_state == state`
`ouch/engine/pipeline.py:506`

A profile with `state = "PA"`, `former_state = "PA"` produces two trace lines
with the same id (`pa.tax`); `verify_dag` deduplicates ids so it passes
silently, and the state is double-counted in totals. One `ConsistencyError`
in `TaxInput._consistency` closes this.

### L2. `-o/--output` only honored for JSON
`ouch/cli/cmd_estimate.py:57`

Table/markdown output ignores `--output` and always writes to stdout. Either
support it or reject the combination (P5).

### L3. Agent `max_tokens` hardcoded at 4096
`ouch/agent/client.py:63`

`ouch agent --review` answers (multi-scenario reviews) can hit this and
truncate mid-answer. Everything else in `[ai]` is config-driven — this should
be too.

## Nit

### N1. Dead first computation in part-year test
`tests/test_pipeline.py:150-160`

`test_part_year_residency_allocates_by_ratio` computes `half` twice; the
first result (income-less input) is immediately overwritten.

---

## What's done well

- **The grounding guardrail is enforced, not aspirational** — the agent
  literally cannot emit a dollar figure that doesn't match a tool result
  (`agent/guardrails.py` + the retry-then-refuse loop), and the tests prove
  the fabrication path refuses.
- **SS wage-base coordination** (`engine/setax.py`) is exactly right and
  independently tested — the spec flags it as a common error and it isn't one
  here (ironically, its sibling Additional-Medicare path is the H1 finding).
- **Data honesty**: every placeholder file ships `verified: false`, results
  carry the warning, and the WA file documents the capital-gains excise tax
  it *doesn't* model rather than letting `regime: none` mislead.
- **Golden fixture discipline**: `tests/golden/.../SOURCE.md` documents an
  independent paper derivation, honoring the spec's "a fixture produced by
  ouch is not a fixture" rule.
- Property tests were *updated honestly* for EITC (monotonicity legitimately
  breaks in the phase-in) instead of being weakened blindly.

## Recommendation

**Approve with comments.** H1 and H2 are small, well-localized fixes with
clear tests to add; nothing blocks merge structurally, but both should land
before anyone trusts output for >$200k wage earners or loss-year filers.
