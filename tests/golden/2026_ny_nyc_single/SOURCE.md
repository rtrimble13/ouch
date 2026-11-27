# New York State and New York City resident

**Covers:** NY progressive (2026 rates), NYC tax on NY taxable income, NYC school tax credits

## Derivation basis

Worked line by line through the 2026 forms with figures from Rev. Proc.
2025-32 §4 and the 2026 IRS forms and draft instructions cited in
`tests/golden_derive/derive.py`, which does not import ouch. Tax on
taxable income below $100,000 is read from the 2026 Tax Table and the
earned income credit from the 2026 EIC Table (draft 2026 Instructions
for Form 1040), not computed by formula; the harness compares money
fields to the dollar (spec §19). **Not** produced by running `ouch`
(spec §16.2).

State figures: NY DTF Instructions for Form IT-2105 (2026). ouch's 2026 NY and NYC file carries these figures; the derivation types them from the source, not the file.

## Computation

### Income (Form 1040 lines 1–11)
- Line 1a wages: 100,025.00
- **Line 9 total income: 100,025.00**
- **Line 11 AGI: 100,025.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- **Line 15 taxable income: 83,925.00**

### Tax (line 16)
  - tax on 83,925.00: 2026 Tax Table row 83,900–83,950, single column = 13,176
- **Line 16: 13,176.00**

### Form 6251 (AMT)
- line 1b = taxable income 83,925.00 = 83,925.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 100,025.00
- line 5 exemption: 90,100.00
- line 6: 9,925.00
- line 7: 26% → 2,580.50
- line 9 TMT 2,580.50; line 10 regular tax 13,176.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 13,176.00 + 0.00 − 0.00 + 0.00 = 13,176.00
- ouch `federal_total_tax` (line 24 less refundable credits): **13,176.00**
- Payments (withholding): 14,000.00 → balance -824.00

### New York State (IT-2105 worksheet, 2026)
- New York AGI = federal AGI 100,025.00 (≤ $107,650, so the rate schedule applies directly); standard deduction 8,000.00; taxable 92,025.00
- 2026 New York State tax rates, single: **4,862.13**
- New York City tax on 92,025.00 (2026 NYC tax rates, single): 3,441.89
- School tax credit, fixed amount (income ≤ $250,000): 63.00; rate reduction amount 21 + 0.228% × (92,025.00 − 12,000) = 203.46
- **New York City tax after the school tax credits: 3,175.43**
- **Total tax, all jurisdictions: 21,213.56**; balance 7,213.56
