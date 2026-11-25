# Changelog

All notable changes to the `ouch` package, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow the rules in [docs/versioning-and-releases.md](docs/versioning-and-releases.md). Each version's section becomes the text of its GitHub release.

Changes that don't ship in the package (tests, CI, documentation) need no entry. Collect notes for the next version under **Unreleased** while a change is in progress.

## [Unreleased]

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

The first tagged release. It covers the work merged before versioning began: specification milestones M1 to M5, the defect fixes that followed review, and the SALT cap phase-down engine (rtrimble13/ouch#20).

Tax data for 2025 and 2026 predates the One Big Beautiful Bill Act (P.L. 119-21) and ships `verified: false`. Estimates computed from it are under superseded law; rtrimble13/ouch#19 tracks the update.

### Added

- **Core estimator (M1):** profile and config system; pure federal engine with preferential rate stacking, SE tax coordinated against the W-2 wage base, NIIT, Additional Medicare, standard/itemized and QBI deductions, CTC/ODC and a simplified AMT; data-driven state and local modules; the withholding solver; full computation traceability (`ouch explain`).
- **Scenarios and ingestion (M2):** scenario patches with `run`, `compare` and `sweep`, cliff detection and `[assert]` guardrails; PDF import for W-2, 1099-INT, 1099-DIV and prior-year 1040, with interactive review and provenance.
- **Tax-loss harvesting (M3):** lot-CSV import, §1091 wash-sale analysis, benefit quantification through the full pipeline, gain-harvesting room and holding-period alerts.
- **AI CPA agent (M4):** `ouch ask` and `ouch agent [--review]`, grounded in tool results with dollar-figure verification; off by default.
- **Depth (M5):** the full credit suite (EITC, child and dependent care, AOTC, LLC, saver's), part-year residency, the AMT credit carryforward, `ouch withhold estimates [--annualized]`, and CA, CO, MA, FL and WA data.
- `estimate --compare-filing-status`.
- The SALT cap phase-down for high-income itemizers (IRC §164(b)(7)): a typed `salt_cap.phasedown` section in the tax-data schema, and an engine that reduces the cap by the phase-down rate above the MAGI threshold, down to the floor. No shipped data file uses it yet, so no estimate changes.

### Fixed

- Additional Medicare tax uses uncapped Medicare wages, not Social Security wages.
- Schedule C losses reduce total income and AGI.
- SE tax is coordinated against the business owner's own Social Security wage base.
- `periods_remaining` is derived from the year being computed.
- Scenario patches that change jurisdiction load that jurisdiction's tax data.
- `taxdata.path` in `config.toml` is honoured.
- `--output` is honoured for every command and format.
- The `withhold check` payment walk adds up; harvest output annotates the ordinary-income offset only when the cap binds; scenario tags and bracketed text render literally.
