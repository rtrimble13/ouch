# Changelog

All notable changes to the `ouch` package, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow the rules in [docs/versioning-and-releases.md](docs/versioning-and-releases.md). Each version's section becomes the text of its GitHub release.

Changes that don't ship in the package (tests, CI, documentation) need no entry. Collect notes for the next version under **Unreleased** while a change is in progress.

## [Unreleased]

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
