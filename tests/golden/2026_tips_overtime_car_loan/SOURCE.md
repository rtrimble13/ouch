# Tips, overtime and car-loan interest

**Covers:** Schedule 1-A Parts II–IV, car-loan interest in its phase-out

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
- Line 1a wages: 105,025.00
- **Line 9 total income: 105,025.00**
- **Line 11 AGI: 105,025.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- Schedule 1-A Part IV: line 33 = 105,025.00 − 100,000 = 5,025.00; line 34 rounded up = 6; line 36 = 3,000.00 − 6 × 200 = 1,800.00
- Schedule 1-A: tips 6,000.00 (Part II, MAGI under 150,000); overtime 4,000.00 (Part III); car-loan interest 1,800.00
- **Schedule 1-A line 44 (Form 1040 line 13a): 11,800.00**
- **Line 15 taxable income: 77,125.00**

### Tax (line 16)
  - tax on 77,125.00: 2026 Tax Table row 77,100–77,150, single column = 11,680
- **Line 16: 11,680.00**

### Form 6251 (AMT)
- line 1b = taxable income 77,125.00 = 77,125.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 93,225.00
- line 5 exemption: 90,100.00
- line 6: 3,125.00
- line 7: 26% → 812.50
- line 9 TMT 812.50; line 10 regular tax 11,680.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 11,680.00 + 0.00 − 0.00 + 0.00 = 11,680.00
- ouch `federal_total_tax` (line 24 less refundable credits): **11,680.00**
- Payments (withholding): 9,000.00 → balance 2,680.00
