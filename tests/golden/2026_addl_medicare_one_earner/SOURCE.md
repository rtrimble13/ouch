# Additional Medicare: single over $200,000

**Covers:** one earner over the $200,000 threshold

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
- Line 1a wages: 260,000.00
- **Line 9 total income: 260,000.00**
- **Line 11 AGI: 260,000.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- **Line 15 taxable income: 243,900.00**

### Tax (line 16)
  - tax on 243,900.00 (Tax Computation Worksheet, single) = 54,504.00
- **Line 16: 54,504.00**

### Form 6251 (AMT)
- line 1b = taxable income 243,900.00 = 243,900.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 260,000.00
- line 5 exemption: 90,100.00
- line 6: 169,900.00
- line 7: 26% → 44,174.00
- line 9 TMT 44,174.00; line 10 regular tax 54,504.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (260,000.00 − 200,000.00) = 540.00 → **540.00**

### Totals
- Line 24 total tax = 54,504.00 + 0.00 − 0.00 + 540.00 = 55,044.00
- ouch `federal_total_tax` (line 24 less refundable credits): **55,044.00**
- Payments (withholding): 60,000.00 → balance -4,956.00
