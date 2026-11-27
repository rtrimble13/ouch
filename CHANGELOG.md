# Changelog

All notable changes to the `ouch` package, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow the rules in [docs/versioning-and-releases.md](docs/versioning-and-releases.md). Each version's section becomes the text of its GitHub release.

Changes that don't ship in the package (tests, CI, documentation) need no entry. Collect notes for the next version under **Unreleased** while a change is in progress.

## [Unreleased]

## [0.6.0] - 2026-11-27

Fixes found by the new independent golden fixtures (rtrimble13/ouch#23). Each was checked against the IRS form text. **Estimates change** for some returns with capital gains or qualified dividends, for AMT filers with them, for seniors carrying an AMT credit, and for anyone using an AMT credit carryforward alongside other credits. 2025 returns are corrected too.

### Fixed

- **Capital gains just above the 0% breakpoint:** the tax is now the smaller of the Qualified Dividends and Capital Gain Tax Worksheet result and the tax on all taxable income as ordinary income (worksheet line 25). Gains taxed at 15% while still inside the 12% bracket were taxed too much: in 2026 that's taxable income between $49,450 and $50,400 single ($98,900–$100,800 joint). Example: single, $49,525 ordinary income plus a $600 gain owed $5,785; it's $5,767.
- **AMT with capital gains:** Form 6251 Part III now measures the 0% and 15% breakpoints from regular-tax ordinary income (lines 20 and 27), not the AMT ordinary base. Example: single, $150,000 wages and $450,000 long-term gain in 2026: AMT is $3,840, not $2,640.
- **AMT and the senior deduction:** the Schedule 1-A deduction for seniors is added back to AMT income (Form 6251 line 1a). That raises the tentative minimum tax, which can lower an AMT credit used this year.
- **AMT credit carryforward:** the credit is now limited to regular tax *less other nonrefundable credits* (such as the child tax credit) over the tentative minimum tax (Form 8801 line 22). It was too large by up to the amount of those credits.

## [0.5.0] - 2026-11-27

2026 charitable changes and the overall limit on itemized deductions (rtrimble13/ouch#24). **2026 estimates change** for itemizers who give to charity, for non-itemizers who give cash, and for itemizers in the top bracket.

### Changed

- **Itemizers, 2026:** only charitable gifts above 0.5% of AGI are deductible. A warning notes that the excess carries forward, which ouch doesn't track. Example: AGI $200,000 and $5,000 of gifts gives $4,000.
- **Non-itemizers, 2026:** cash gifts up to $1,000 ($2,000 joint) are deductible on Form 1040 line 12f, shown as `nonitemizer_charitable_deduction`. A new `deductions.itemized.charitable_cash_daf` marks the part given to donor-advised funds or supporting organizations, which doesn't qualify. Choosing between the standard and itemized deductions now counts line 12f on the standard side, so a filer whose itemized total only just beats the standard deduction may now be better off not itemizing.
- **Top bracket, 2026 (§68):** itemized deductions are reduced by 5.4% of the lesser of the itemized total and income above $768,700 joint ($640,600 single or head of household, $384,350 separate). The reduction is added back for AMT. This is approximate until the IRS publishes the Schedule A worksheet.
- The Schedule 1-A trace line now says "Form 1040 line 13 (13b for 2025, 13a from 2026)": the 2026 Form 1040 swaps lines 13a and 13b.

## [0.4.0] - 2026-11-27

2026 credit and QBI changes from OBBBA (rtrimble13/ouch#25). **2026 estimates change** for anyone claiming the child and dependent care credit, and for small active businesses.

### Changed

- **Child and dependent care credit, 2026:** the rate starts at 50%, not 35%. It falls 1 point per $2,000 of AGI over $15,000 to 35%, then 1 point per $4,000 over $150,000 on a joint return (per $2,000 over $75,000 otherwise) to 20%. Expense limits stay $3,000 / $6,000. For example, a joint return with $160,000 AGI and two children now gets 32% of $6,000 = $1,920, up from $1,200. The schedule comes from the IRS's **draft** 2026 Form 2441 instructions, so it's re-checked when the final form is out.
- **QBI minimum deduction, 2026:** at least $400 when active qualified business income is at least $1,000. A new `income.business.material_participation` flag (default `true`) marks passive income, which doesn't qualify.

### Added

- Child tax credit returns now carry a warning that each qualifying child, and you (or one spouse on a joint return), are assumed to have a Social Security number valid for employment. ouch has no SSN inputs.

## [0.3.2] - 2026-11-27

Adds the remaining Schedule 1-A deductions for 2025–2028 (rtrimble13/ouch#26), and their import from 2026 W-2s. Existing profiles compute exactly as before: these take new, optional inputs. (0.3.1 was never released on its own; its changes are listed here.)

### Added

- **No tax on tips:** `income.wages.taxpayer_qualified_tips` / `spouse_qualified_tips`. Up to $25,000 per return, less $100 for each full $1,000 of MAGI above $150,000 ($300,000 joint). Married filers must file jointly.
- **No tax on overtime:** `income.wages.taxpayer_qualified_overtime` / `spouse_qualified_overtime`, the FLSA premium portion only. Up to $12,500 ($25,000 joint), with the same phase-out as tips. Married filers must file jointly.
- **No tax on car loan interest:** `deductions.car_loan_interest`. Up to $10,000, less $200 for each $1,000, or part of one, of MAGI above $100,000 ($200,000 joint). Any filing status.
- Each deduction has its own trace line under `fed.schedule_1a` (Form 1040 line 13b). Eligibility the profile can't express (the tipped occupation, the overtime premium, the vehicle, valid SSNs) is assumed and stated in a warning.
- A profile whose tips plus overtime exceed that person's W-2 box 1 wages is rejected, because both are already part of box 1.
- `ouch import pdf` reads W-2 box 12 codes **TP** (cash tips reported to the employer) and **TT** (qualified overtime, the premium portion only) into those fields. These are new on 2026 W-2s. Other box 12 codes are ignored.
- TP is every cash tip, so the import also reads box 14b, the Treasury Tipped Occupation Code(s). When box 14b includes `000` (some tips came from a nonqualifying occupation), or box 14b can't be found, the tips amount goes to review instead of being accepted. `--yes` skips it.
- PDF mapping tables accept `coded_fields` for code-keyed boxes such as W-2 box 12.

## [0.3.0] - 2026-11-25

**Every 2025 estimate changes.** The 2025 federal data reflected Rev. Proc. 2024-40 before OBBBA. It now has the law as enacted for 2025 (rtrimble13/ouch#27), and every other figure was re-checked against Rev. Proc. 2024-40 and the 2025 forms. Some typical 2025 federal totals:

| 2025 profile | Before | After | Change |
|---|---|---|---|
| Single, wages $100,000 | $13,614 | $13,449 | −$165 |
| MFJ, wages $200,000, two children | $23,228 | $22,498 | −$730 |
| MFJ, wages $400,000, $50,000 SALT, $30,000 mortgage interest | $73,444 | $66,244 | −$7,200 |

The file still ships `verified: false`, because the Schedule 1-A tips, overtime and car-loan interest deductions (2025–2028) aren't modelled yet.

### Changed

- 2025 standard deduction $15,750 single and MFS, $31,500 joint and surviving spouse, $23,625 head of household (Rev. Proc. 2025-32 §3.01).
- 2025 SALT cap $40,000 ($20,000 MFS), reduced by 30% of MAGI over $500,000 ($250,000 MFS), down to $10,000 ($5,000 MFS).
- 2025 child tax credit $2,200 per child.
- 2025 underpayment interest rate 7% in every quarter (was 8%), and the second estimated payment is due June 16, 2025 (June 15 was a Sunday).

### Fixed

- 2025 data for a qualifying surviving spouse: the Additional Medicare threshold is $200,000 (not $250,000), the CTC phase-out $200,000 (not $400,000), and the QBI threshold $197,300 with a $50,000 phase-in range (not the joint amounts).
- Married filing separately reaches the 28% AMT rate at $119,550 in 2025, half the joint breakpoint.

## [0.2.0] - 2026-11-25

**Every 2026 estimate changes.** The 2026 federal tax data was a copy of the pre-OBBBA 2025 file. It's now rebuilt from Rev. Proc. 2025-32 and current law (rtrimble13/ouch#22). Some typical 2026 federal totals:

| 2026 profile | Before | After | Change |
|---|---|---|---|
| Single, wages $100,000 | $13,614 | $13,170 | −$444 |
| MFJ, wages $200,000, two children | $23,228 | $21,940 | −$1,288 |
| MFJ, wages $400,000, $50,000 SALT, $30,000 mortgage interest | $73,444 | $65,650 | −$7,794 |
| Single, Schedule C profit $200,000 | $61,177 | $61,580 | +$404 (higher wage base) |

The file still ships `verified: false`. These 2026 provisions aren't modelled yet: the dependent care credit's new 50% rate schedule (the credit is understated for lower-income filers), the charitable 0.5% floor and non-itemizer deduction, the 5.4% limit on itemized deductions in the top bracket, the QBI minimum deduction, and the tips, overtime and car-loan interest deductions.

### Changed

- 2026 brackets, 0%/15% capital-gain breakpoints, standard deduction ($16,100 single, $32,200 joint, $24,150 head of household) and age-65/blind amounts ($2,050 unmarried, $1,650 married).
- 2026 SALT cap $40,400 ($20,200 MFS), reduced by 30% of MAGI over $505,000 ($252,500 MFS), down to $10,000 ($5,000 MFS).
- 2026 Social Security wage base $184,500; child tax credit $2,200 per child; the EITC table; saver's credit income limits; 2026 IRS underpayment interest rates.
- 2026 AMT exemption ($90,100 unmarried, $140,200 joint) phases out at **50%** above $500,000 ($1,000,000 joint), up from 25% above $626,350. More high earners will owe AMT.
- 2026 QBI thresholds ($201,750; $403,500 joint) and the wider phase-in range ($75,000; $150,000 joint).
- The unverified-data warning reads "Federal tax data for 2026 is unverified", without "(projected)".

### Fixed

- A qualifying surviving spouse no longer gets amounts the law reserves for joint returns: the EITC phase-out start, the education credit income range, and the saver's credit limits (all years). In the 2026 data, also the Additional Medicare threshold ($200,000, not $250,000) and the CTC phase-out ($200,000, not $400,000). Affected surviving spouses see a smaller credit or higher tax.
- Married filing separately reaches the 28% AMT rate at half the joint breakpoint ($122,250 in 2026) when the data file gives one.
- The EITC at exactly the earned income amount is the published maximum (e.g. $4,427 in 2026, not $4,426.80).

## [0.1.0] - 2026-11-25

The first tagged release. It covers the work merged before versioning began: specification milestones M1 to M5, the defect fixes that followed review, the SALT cap phase-down engine (rtrimble13/ouch#20), and the 2025–2028 senior deduction (rtrimble13/ouch#21).

Tax data for 2025 and 2026 predates the One Big Beautiful Bill Act (P.L. 119-21) and ships `verified: false`. Estimates computed from it are under superseded law; rtrimble13/ouch#19 tracks the update.

### Added

- **Core estimator (M1):** profile and config system; pure federal engine with preferential rate stacking, SE tax coordinated against the W-2 wage base, NIIT, Additional Medicare, standard/itemized and QBI deductions, CTC/ODC and a simplified AMT; data-driven state and local modules; the withholding solver; full computation traceability (`ouch explain`).
- **Scenarios and ingestion (M2):** scenario patches with `run`, `compare` and `sweep`, cliff detection and `[assert]` guardrails; PDF import for W-2, 1099-INT, 1099-DIV and prior-year 1040, with interactive review and provenance.
- **Tax-loss harvesting (M3):** lot-CSV import, §1091 wash-sale analysis, benefit quantification through the full pipeline, gain-harvesting room and holding-period alerts.
- **AI CPA agent (M4):** `ouch ask` and `ouch agent [--review]`, grounded in tool results with dollar-figure verification; off by default.
- **Depth (M5):** the full credit suite (EITC, child and dependent care, AOTC, LLC, saver's), part-year residency, the AMT credit carryforward, `ouch withhold estimates [--annualized]`, and CA, CO, MA, FL and WA data.
- `estimate --compare-filing-status`.
- The SALT cap phase-down for high-income itemizers (IRC §164(b)(7)): a typed `salt_cap.phasedown` section in the tax-data schema, and an engine that reduces the cap by the phase-down rate above the MAGI threshold, down to the floor. No shipped data file uses it yet, so no estimate changes.
- The 2025–2028 enhanced deduction for seniors (Schedule 1-A Part V): $6,000 per person aged 65 or older, less 6% of MAGI over $75,000 ($150,000 joint), claimed on top of the standard or itemized deduction. Married filers must file jointly. Shown as `schedule_1a_deduction` in the summary, JSON output and `--compare-filing-status`.

### Fixed

- A filer born on January 1 now counts as 65 at the end of the year before their 65th birthday, matching Form 1040's "born before January 2" test, so they get the additional age-65 standard deduction that calendar age denied them.
- Additional Medicare tax uses uncapped Medicare wages, not Social Security wages.
- Schedule C losses reduce total income and AGI.
- SE tax is coordinated against the business owner's own Social Security wage base.
- `periods_remaining` is derived from the year being computed.
- Scenario patches that change jurisdiction load that jurisdiction's tax data.
- `taxdata.path` in `config.toml` is honoured.
- `--output` is honoured for every command and format.
- The `withhold check` payment walk adds up; harvest output annotates the ordinary-income offset only when the cap binds; scenario tags and bracketed text render literally.
