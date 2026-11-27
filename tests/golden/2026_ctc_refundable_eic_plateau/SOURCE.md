# CTC refundable portion; EIC plateau

**Covers:** additional child tax credit; EIC at the plateau (3 children)

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
- Line 1a wages: 30,000.00 (taxpayer 18,000.00, spouse 12,000.00)
- **Line 9 total income: 30,000.00**
- **Line 11 AGI: 30,000.00**

### Deductions (lines 12–14)
- Standard deduction: 32,200
- **Line 12e: 32,200.00 (standard)**
- **Line 15 taxable income: 0.00**

### Tax (line 16)
- **Line 16: 0.00**

### Form 6251 (AMT)
- line 1b = taxable income 0.00 = 0.00
- line 2a (line 12e standard deduction): 32,200.00
- line 4 AMTI: 32,200.00
- line 5 exemption: 140,200.00
- line 6: 0.00
- line 7: 26% → 0.00
- line 9 TMT 0.00; line 10 regular tax 0.00
- **line 11 AMT: 0.00**

### Credits
- Schedule 8812: line 8 = 3 × 2,200 = 6,600.00; line 11 = 0.00; line 12 = 6,600.00; line 13 (Credit Limit Worksheet A) = 0.00; **line 14 = 0.00**
  - line 16a 6,600.00; 16b 5,100.00; 17 5,100.00; line 20 = 15% × (30,000.00 − 2,500) = 4,125.00
  - Part II-B: withheld SS + Medicare 2,295.00 less EIC → line 25 0.00
  - **line 27 ACTC: 4,125.00**
- EIC (EIC Table, 3 children, MFJ column): earned income 30,000.00 → 8,231; AGI 30,000.00 → **8,231** (line 27a)

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 0.00 + 0.00 − 0.00 + 0.00 = 0.00
- Refundable credits (lines 27a + 28): 12,356.00
- ouch `federal_total_tax` (line 24 less refundable credits): **-12,356.00**
- Payments (withholding): 500.00 → balance -12,856.00
