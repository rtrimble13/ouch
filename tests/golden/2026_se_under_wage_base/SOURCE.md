# W-2 plus Schedule C, under the wage base

**Covers:** SE tax with full Social Security part; QBI below the threshold

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
- Line 1a wages: 90,000.00
- Schedule SE (taxpayer): net earnings 92.35% × 40,000.00 = 36,940.00
  - Social Security part: room under the $184,500 wage base = 184,500 − taxpayer's W-2 90,000.00 = 94,500.00; 12.4% × 36,940.00 = 4,580.56
  - Medicare part: 2.9% × 36,940.00 = 1,071.26
  - SE tax 5,651.82; deductible half (Schedule 1 line 15) 2,825.91
- Schedule 1 line 3 business income: 40,000.00
- **Line 9 total income: 130,000.00**
- Line 10 adjustments: 2,825.91 (half of SE tax)
- **Line 11 AGI: 127,174.09**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- QBI: 40,000.00 − deductible SE tax 2,825.91 = 37,174.09; 20% = 7,434.82
  - taxable income before QBI = 127,174.09 − 16,100.00 = 111,074.09
  - income limit 20% × (111,074.09 − net capital gain 0.00) = 22,214.82 → **QBI deduction 7,434.82** (line 13b)
- **Line 15 taxable income: 103,639.27**

### Tax (line 16)
  - tax on 103,639.27 (Tax Computation Worksheet, single) = 17,512.64
- **Line 16: 17,512.64**

### Form 6251 (AMT)
- line 1b = taxable income 103,639.27 = 103,639.27
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 119,739.27
- line 5 exemption: 90,100.00
- line 6: 29,639.27
- line 7: 26% → 7,706.21
- line 9 TMT 7,706.21; line 10 regular tax 17,512.64
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Schedule SE tax: 5,651.82

### Totals
- Line 24 total tax = 17,512.64 + 0.00 − 0.00 + 5,651.82 = 23,164.46
- ouch `federal_total_tax` (line 24 less refundable credits): **23,164.46**
- Payments (withholding): 15,000.00 → balance 8,164.46
