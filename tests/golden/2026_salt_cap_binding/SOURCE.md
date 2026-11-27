# SALT cap binding

**Covers:** SALT limited to $40,400 below the $505,000 threshold

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
- Line 1a wages: 300,000.00 (taxpayer 180,000.00, spouse 120,000.00)
- **Line 9 total income: 300,000.00**
- **Line 11 AGI: 300,000.00**

### Deductions (lines 12–14)
- Standard deduction: 32,200
- Schedule A line 5d SALT paid 45,000.00 → line 5e 40,400.00
- Schedule A line 8a mortgage interest 20,000.00
- Charity: cash 5,000.00 − 0.5% × AGI (1,500.00) = 3,500.00
- Schedule A line 17 total itemized: 63,900.00
- Itemized 63,900.00 beats standard 32,200.00 + line 12f → itemize
- **Line 12e: 63,900.00 (itemized)**
- **Line 15 taxable income: 236,100.00**

### Tax (line 16)
  - tax on 236,100.00 (Tax Computation Worksheet, married_filing_jointly) = 41,860.00
- **Line 16: 41,860.00**

### Form 6251 (AMT)
- line 1b = taxable income 236,100.00 = 236,100.00
- line 2a (Schedule A line 7 taxes): 40,400.00
- line 4 AMTI: 276,500.00
- line 5 exemption: 140,200.00
- line 6: 136,300.00
- line 7: 26% → 35,438.00
- line 9 TMT 35,438.00; line 10 regular tax 41,860.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (300,000.00 − 250,000.00) = 450.00 → **450.00**

### Totals
- Line 24 total tax = 41,860.00 + 0.00 − 0.00 + 450.00 = 42,310.00
- ouch `federal_total_tax` (line 24 less refundable credits): **42,310.00**
- Payments (withholding): 42,000.00 → balance 310.00
