# Colorado: deduction addback over $300,000 AGI

**Covers:** CO addback of the federal standard deduction above $1,000 (2026) for AGI over $300,000

## Derivation basis

Worked line by line through the 2026 forms with figures from Rev. Proc.
2025-32 §4 and the 2026 IRS forms and draft instructions cited in
`tests/golden_derive/derive.py`, which does not import ouch. Tax on
taxable income below $100,000 is read from the 2026 Tax Table and the
earned income credit from the 2026 EIC Table (draft 2026 Instructions
for Form 1040), not computed by formula; the harness compares money
fields to the dollar (spec §19). **Not** produced by running `ouch`
(spec §16.2).

State figures: CO DOR Individual Income Tax Guide (rev. January 2026), Part 3. ouch's 2026 CO file carries these figures; the derivation types them from the source, not the file.

## Computation

### Income (Form 1040 lines 1–11)
- Line 1a wages: 400,000.00
- **Line 9 total income: 400,000.00**
- **Line 11 AGI: 400,000.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- **Line 15 taxable income: 383,900.00**

### Tax (line 16)
  - tax on 383,900.00 (Tax Computation Worksheet, single) = 103,134.25
- **Line 16: 103,134.25**

### Form 6251 (AMT)
- line 1b = taxable income 383,900.00 = 383,900.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 400,000.00
- line 5 exemption: 90,100.00
- line 6: 309,900.00
- line 7: 28% − 4,890.00 → 81,882.00
- line 9 TMT 81,882.00; line 10 regular tax 103,134.25
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (400,000.00 − 200,000.00) = 1,800.00 → **1,800.00**

### Totals
- Line 24 total tax = 103,134.25 + 0.00 − 0.00 + 1,800.00 = 104,934.25
- ouch `federal_total_tax` (line 24 less refundable credits): **104,934.25**
- Payments (withholding): 120,000.00 → balance -15,065.75

### Colorado (DR 0104, 2026 rules)
- Federal taxable income 383,900.00
- Addition: deduction above the 1,000.00 limit (AGI over $300,000): 15,100.00
- Colorado taxable income 399,000.00 × 4.4% = **17,556.00**
- **Total tax, all jurisdictions: 122,490.25**; balance 2,490.25
