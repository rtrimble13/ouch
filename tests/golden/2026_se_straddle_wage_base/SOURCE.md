# W-2 plus Schedule C, straddling the wage base

**Covers:** SE Social Security part limited by the W-2 wages; Additional Medicare on SE income

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
- Line 1a wages: 160,000.00
- Schedule SE (taxpayer): net earnings 92.35% × 50,000.00 = 46,175.00
  - Social Security part: room under the $184,500 wage base = 184,500 − taxpayer's W-2 160,000.00 = 24,500.00; 12.4% × 24,500.00 = 3,038.00
  - Medicare part: 2.9% × 46,175.00 = 1,339.08
  - SE tax 4,377.08; deductible half (Schedule 1 line 15) 2,188.54
- Schedule 1 line 3 business income: 50,000.00
- **Line 9 total income: 210,000.00**
- Line 10 adjustments: 2,188.54 (half of SE tax)
- **Line 11 AGI: 207,811.46**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- QBI: 50,000.00 − deductible SE tax 2,188.54 = 47,811.46; 20% = 9,562.29
  - taxable income before QBI = 207,811.46 − 16,100.00 = 191,711.46
  - income limit 20% × (191,711.46 − net capital gain 0.00) = 38,342.29 → **QBI deduction 9,562.29** (line 13b)
- **Line 15 taxable income: 182,149.17**

### Tax (line 16)
  - tax on 182,149.17 (Tax Computation Worksheet, single) = 36,313.80
- **Line 16: 36,313.80**

### Form 6251 (AMT)
- line 1b = taxable income 182,149.17 = 182,149.17
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 198,249.17
- line 5 exemption: 90,100.00
- line 6: 108,149.17
- line 7: 26% → 28,118.78
- line 9 TMT 28,118.78; line 10 regular tax 36,313.80
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (160,000.00 − 200,000.00) = 0.00; Part II 0.9% × (46,175.00 − max(0, 200,000.00 − 160,000.00)) = 55.58 → **55.58**
- Schedule SE tax: 4,377.08

### Totals
- Line 24 total tax = 36,313.80 + 0.00 − 0.00 + 4,432.65 = 40,746.45
- ouch `federal_total_tax` (line 24 less refundable credits): **40,746.45**
- Payments (withholding): 35,000.00 → balance 5,746.45
