# Enhanced deduction for seniors, full $6,000

**Covers:** Schedule 1-A Part V below the threshold; additional standard deduction for age

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
- Line 5b pensions: 30,025.00
- Line 4b IRA distributions: 20,000.00
- **Line 9 total income: 50,025.00**
- **Line 11 AGI: 50,025.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100 + 1 × 2,050 (65 or older) = 18,150.00
- **Line 12e: 18,150.00 (standard)**
- Schedule 1-A Part V: line 39 = 50,025.00 − 75,000.00 = 0.00; line 41 = 6,000 − 6% × 0.00 = 6,000.00; × 1 = **6,000.00** (line 13a)
- **Line 15 taxable income: 25,875.00**

### Tax (line 16)
  - tax on 25,875.00: 2026 Tax Table row 25,850–25,900, single column = 2,857
- **Line 16: 2,857.00**

### Form 6251 (AMT)
- line 1b = taxable income 25,875.00 + Schedule 1-A line 43 senior deduction 6,000.00 = 31,875.00
- line 2a (line 12e standard deduction): 18,150.00
- line 4 AMTI: 50,025.00
- line 5 exemption: 90,100.00
- line 6: 0.00
- line 7: 26% → 0.00
- line 9 TMT 0.00; line 10 regular tax 2,857.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 2,857.00 + 0.00 − 0.00 + 0.00 = 2,857.00
- ouch `federal_total_tax` (line 24 less refundable credits): **2,857.00**
- Payments (withholding): 3,000.00 → balance -143.00
