# Married filing separately, wages only

**Covers:** filing status MFS

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
- Line 1a wages: 85,025.00
- **Line 9 total income: 85,025.00**
- **Line 11 AGI: 85,025.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- **Line 15 taxable income: 68,925.00**

### Tax (line 16)
  - tax on 68,925.00: 2026 Tax Table row 68,900–68,950, married_filing_separately column = 9,876
- **Line 16: 9,876.00**

### Form 6251 (AMT)
- line 1b = taxable income 68,925.00 = 68,925.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 85,025.00
- line 5 exemption: 70,100.00
- line 6: 14,925.00
- line 7: 26% → 3,880.50
- line 9 TMT 3,880.50; line 10 regular tax 9,876.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 9,876.00 + 0.00 − 0.00 + 0.00 = 9,876.00
- ouch `federal_total_tax` (line 24 less refundable credits): **9,876.00**
- Payments (withholding): 9,000.00 → balance 876.00
