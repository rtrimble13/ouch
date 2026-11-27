# Additional Medicare: joint over $250,000

**Covers:** two earners each under $200,000, joint wages over $250,000

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
- Line 1a wages: 290,000.00 (taxpayer 150,000.00, spouse 140,000.00)
- **Line 9 total income: 290,000.00**
- **Line 11 AGI: 290,000.00**

### Deductions (lines 12–14)
- Standard deduction: 32,200
- **Line 12e: 32,200.00 (standard)**
- **Line 15 taxable income: 257,800.00**

### Tax (line 16)
  - tax on 257,800.00 (Tax Computation Worksheet, married_filing_jointly) = 47,068.00
- **Line 16: 47,068.00**

### Form 6251 (AMT)
- line 1b = taxable income 257,800.00 = 257,800.00
- line 2a (line 12e standard deduction): 32,200.00
- line 4 AMTI: 290,000.00
- line 5 exemption: 140,200.00
- line 6: 149,800.00
- line 7: 26% → 38,948.00
- line 9 TMT 38,948.00; line 10 regular tax 47,068.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (290,000.00 − 250,000.00) = 360.00 → **360.00**

### Totals
- Line 24 total tax = 47,068.00 + 0.00 − 0.00 + 360.00 = 47,428.00
- ouch `federal_total_tax` (line 24 less refundable credits): **47,428.00**
- Payments (withholding): 45,000.00 → balance 2,428.00
