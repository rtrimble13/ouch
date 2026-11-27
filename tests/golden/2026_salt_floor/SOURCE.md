# SALT cap at its $10,000 floor

**Covers:** SALT phase-down reaching the floor

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
- Line 1a wages: 700,000.00 (taxpayer 400,000.00, spouse 300,000.00)
- **Line 9 total income: 700,000.00**
- **Line 11 AGI: 700,000.00**

### Deductions (lines 12–14)
- Standard deduction: 32,200
- SALT cap: AGI 700,000.00 over $505,000 → max(10,000, 40,400 − 30% × 195,000.00) = 10,000.00
- Schedule A line 5d SALT paid 50,000.00 → line 5e 10,000.00
- Schedule A line 8a mortgage interest 30,000.00
- Charity: cash 20,000.00 − 0.5% × AGI (3,500.00) = 16,500.00
- Schedule A line 17 total itemized: 56,500.00
- Itemized 56,500.00 beats standard 32,200.00 + line 12f → itemize
- **Line 12e: 56,500.00 (itemized)**
- **Line 15 taxable income: 643,500.00**

### Tax (line 16)
  - tax on 643,500.00 (Tax Computation Worksheet, married_filing_jointly) = 162,763.50
- **Line 16: 162,763.50**

### Form 6251 (AMT)
- line 1b = taxable income 643,500.00 = 643,500.00
- line 2a (Schedule A line 7 taxes): 10,000.00
- line 4 AMTI: 653,500.00
- line 5 exemption: 140,200.00
- line 6: 513,300.00
- line 7: 28% − 4,890.00 → 138,834.00
- line 9 TMT 138,834.00; line 10 regular tax 162,763.50
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (700,000.00 − 250,000.00) = 4,050.00 → **4,050.00**

### Totals
- Line 24 total tax = 162,763.50 + 0.00 − 0.00 + 4,050.00 = 166,813.50
- ouch `federal_total_tax` (line 24 less refundable credits): **166,813.50**
- Payments (withholding): 165,000.00 → balance 1,813.50
