# W-2 over the wage base; QBI in the phase-in

**Covers:** SE tax Medicare only; Additional Medicare Part II with a zero threshold; QBI inside the phase-in range with no W-2 wages paid

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
- Line 1a wages: 200,000.00
- Schedule SE (taxpayer): net earnings 92.35% × 30,000.00 = 27,705.00
  - Social Security part: room under the $184,500 wage base = 184,500 − taxpayer's W-2 200,000.00 = 0.00; 12.4% × 0.00 = 0.00
  - Medicare part: 2.9% × 27,705.00 = 803.45
  - SE tax 803.45; deductible half (Schedule 1 line 15) 401.72
- Schedule 1 line 3 business income: 30,000.00
- **Line 9 total income: 230,000.00**
- Line 10 adjustments: 401.72 (half of SE tax)
- **Line 11 AGI: 229,598.28**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- QBI: 30,000.00 − deductible SE tax 401.72 = 29,598.28; 20% = 5,919.66
  - taxable income before QBI = 229,598.28 − 16,100.00 = 213,498.28
  - Form 8995-A Part III: over the 201,750.00 threshold by 11,748.28 → 0.156644 of the 75,000.00 phase-in range; W-2 wages/UBIA limit 0 → reduction 927.28; component 4,992.38
  - income limit 20% × (213,498.28 − net capital gain 0.00) = 42,699.66 → **QBI deduction 4,992.38** (line 13b)
- **Line 15 taxable income: 208,505.90**

### Tax (line 16)
  - tax on 208,505.90 (Tax Computation Worksheet, single) = 43,177.89
- **Line 16: 43,177.89**

### Form 6251 (AMT)
- line 1b = taxable income 208,505.90 = 208,505.90
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 224,605.90
- line 5 exemption: 90,100.00
- line 6: 134,505.90
- line 7: 26% → 34,971.53
- line 9 TMT 34,971.53; line 10 regular tax 43,177.89
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (200,000.00 − 200,000.00) = 0.00; Part II 0.9% × (27,705.00 − max(0, 200,000.00 − 200,000.00)) = 249.35 → **249.35**
- Schedule SE tax: 803.45

### Totals
- Line 24 total tax = 43,177.89 + 0.00 − 0.00 + 1,052.79 = 44,230.68
- ouch `federal_total_tax` (line 24 less refundable credits): **44,230.68**
- Payments (withholding): 48,000.00 → balance -3,769.32
