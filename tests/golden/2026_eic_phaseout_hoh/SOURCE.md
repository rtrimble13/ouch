# EIC in the phase-out

**Covers:** EIC phase-out (1 child); CTC limited by tax with the rest refundable

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
- Line 1a wages: 40,025.00
- **Line 9 total income: 40,025.00**
- **Line 11 AGI: 40,025.00**

### Deductions (lines 12–14)
- Standard deduction: 24,150
- **Line 12e: 24,150.00 (standard)**
- **Line 15 taxable income: 15,875.00**

### Tax (line 16)
  - tax on 15,875.00: 2026 Tax Table row 15,850–15,900, head_of_household column = 1,588
- **Line 16: 1,588.00**

### Form 6251 (AMT)
- line 1b = taxable income 15,875.00 = 15,875.00
- line 2a (line 12e standard deduction): 24,150.00
- line 4 AMTI: 40,025.00
- line 5 exemption: 90,100.00
- line 6: 0.00
- line 7: 26% → 0.00
- line 9 TMT 0.00; line 10 regular tax 1,588.00
- **line 11 AMT: 0.00**

### Credits
- Schedule 8812: line 8 = 1 × 2,200 = 2,200.00; line 11 = 0.00; line 12 = 2,200.00; line 13 (Credit Limit Worksheet A) = 1,588.00; **line 14 = 1,588.00**
  - line 16a 612.00; 16b 1,700.00; 17 612.00; line 20 = 15% × (40,025.00 − 2,500) = 5,628.75
  - **line 27 ACTC: 612.00**
- EIC (EIC Table, 1 child, other column): earned income 40,025.00 → 1,849; AGI 40,025.00 → **1,849** (line 27a)

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 1,588.00 + 0.00 − 1,588.00 + 0.00 = 0.00
- Refundable credits (lines 27a + 28): 2,461.00
- ouch `federal_total_tax` (line 24 less refundable credits): **-2,461.00**
- Payments (withholding): 1,000.00 → balance -3,461.00
