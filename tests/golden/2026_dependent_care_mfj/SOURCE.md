# Child and dependent care credit, 2026 schedule

**Covers:** Form 2441 2026 second-tier phase-down; CTC for two children

## Derivation basis

Worked line by line through the 2026 forms with figures from Rev. Proc.
2025-32 §4 and the 2026 IRS forms and draft instructions cited in
`tests/golden_derive/derive.py`, which does not import ouch. Tax on
taxable income below $100,000 is read from the 2026 Tax Table and the
earned income credit from the 2026 EIC Table (draft 2026 Instructions
for Form 1040), not computed by formula; the harness compares money
fields to the dollar (spec §19). **Not** produced by running `ouch`
(spec §16.2).

## Computation

### Income (Form 1040 lines 1–11)
- Line 1a wages: 160,000.00 (taxpayer 120,000.00, spouse 40,000.00)
- **Line 9 total income: 160,000.00**
- **Line 11 AGI: 160,000.00**

### Deductions (lines 12–14)
- Standard deduction: 32,200
- **Line 12e: 32,200.00 (standard)**
- **Line 15 taxable income: 127,800.00**

### Tax (line 16)
  - tax on 127,800.00 (Tax Computation Worksheet, married_filing_jointly) = 17,540.00
- **Line 16: 17,540.00**

### Form 6251 (AMT)
- line 1b = taxable income 127,800.00 = 127,800.00
- line 2a (line 12e standard deduction): 32,200.00
- line 4 AMTI: 160,000.00
- line 5 exemption: 140,200.00
- line 6: 19,800.00
- line 7: 26% → 5,148.00
- line 9 TMT 5,148.00; line 10 regular tax 17,540.00
- **line 11 AMT: 0.00**

### Credits
- Form 2441: expenses 8,000.00, limit 6,000.00 (2 children), lower earner 40,000.00 → 6,000.00; 2026 Phaseout Schedule rate at AGI 160,000.00: 0.32 → **1,920.00**
- Schedule 8812: line 8 = 2 × 2,200 = 4,400.00; line 11 = 0.00; line 12 = 4,400.00; line 13 (Credit Limit Worksheet A) = 15,620.00; **line 14 = 4,400.00**

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 17,540.00 + 0.00 − 6,320.00 + 0.00 = 11,220.00
- ouch `federal_total_tax` (line 24 less refundable credits): **11,220.00**
- Payments (withholding): 10,000.00 → balance 1,220.00
