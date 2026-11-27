# Qualifying surviving spouse, one child

**Covers:** filing status QSS (joint brackets and standard deduction)

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
- Line 1a wages: 120,025.00
- **Line 9 total income: 120,025.00**
- **Line 11 AGI: 120,025.00**

### Deductions (lines 12–14)
- Standard deduction: 32,200
- **Line 12e: 32,200.00 (standard)**
- **Line 15 taxable income: 87,825.00**

### Tax (line 16)
  - tax on 87,825.00: 2026 Tax Table row 87,800–87,850, qualifying_surviving_spouse column = 10,043
- **Line 16: 10,043.00**

### Form 6251 (AMT)
- line 1b = taxable income 87,825.00 = 87,825.00
- line 2a (line 12e standard deduction): 32,200.00
- line 4 AMTI: 120,025.00
- line 5 exemption: 140,200.00
- line 6: 0.00
- line 7: 26% → 0.00
- line 9 TMT 0.00; line 10 regular tax 10,043.00
- **line 11 AMT: 0.00**

### Credits
- Schedule 8812: line 8 = 1 × 2,200 = 2,200.00; line 11 = 0.00; line 12 = 2,200.00; line 13 (Credit Limit Worksheet A) = 10,043.00; **line 14 = 2,200.00**

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 10,043.00 + 0.00 − 2,200.00 + 0.00 = 7,843.00
- ouch `federal_total_tax` (line 24 less refundable credits): **7,843.00**
- Payments (withholding): 8,000.00 → balance -157.00
