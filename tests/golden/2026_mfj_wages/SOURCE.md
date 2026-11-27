# Married filing jointly, two earners

**Covers:** filing status MFJ; Tax Computation Worksheet

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
- Line 1a wages: 150,000.00 (taxpayer 95,000.00, spouse 55,000.00)
- **Line 9 total income: 150,000.00**
- **Line 11 AGI: 150,000.00**

### Deductions (lines 12–14)
- Standard deduction: 32,200
- **Line 12e: 32,200.00 (standard)**
- **Line 15 taxable income: 117,800.00**

### Tax (line 16)
  - tax on 117,800.00 (Tax Computation Worksheet, married_filing_jointly) = 15,340.00
- **Line 16: 15,340.00**

### Form 6251 (AMT)
- line 1b = taxable income 117,800.00 = 117,800.00
- line 2a (line 12e standard deduction): 32,200.00
- line 4 AMTI: 150,000.00
- line 5 exemption: 140,200.00
- line 6: 9,800.00
- line 7: 26% → 2,548.00
- line 9 TMT 2,548.00; line 10 regular tax 15,340.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 15,340.00 + 0.00 − 0.00 + 0.00 = 15,340.00
- ouch `federal_total_tax` (line 24 less refundable credits): **15,340.00**
- Payments (withholding): 16,000.00 → balance -660.00
