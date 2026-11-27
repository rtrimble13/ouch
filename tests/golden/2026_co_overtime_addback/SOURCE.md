# Colorado: overtime addback

**Covers:** CO flat rate on federal taxable income; 2026 overtime deduction addback

## Derivation basis

Worked line by line through the 2026 forms with figures from Rev. Proc.
2025-32 §4 and the 2026 IRS forms and draft instructions cited in
`tests/golden_derive/derive.py`, which does not import ouch. Tax on
taxable income below $100,000 is read from the 2026 Tax Table and the
earned income credit from the 2026 EIC Table (draft 2026 Instructions
for Form 1040), not computed by formula; the harness compares money
fields to the dollar (spec §19). **Not** produced by running `ouch`
(spec §16.2).

State figures: CO DOR Individual Income Tax Guide (rev. January 2026), Part 3; the 4.4% rate is 2025's, carried to 2026. ouch's 2026 CO file carries these figures; the derivation types them from the source, not the file.

## Computation

### Income (Form 1040 lines 1–11)
- Line 1a wages: 120,025.00
- **Line 9 total income: 120,025.00**
- **Line 11 AGI: 120,025.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- Schedule 1-A Part IV: line 33 = 120,025.00 − 100,000 = 20,025.00; line 34 rounded up = 21; line 36 = 0.00 − 21 × 200 = 0.00
- Schedule 1-A: tips 0.00 (Part II, MAGI under 150,000); overtime 6,000.00 (Part III); car-loan interest 0.00
- **Schedule 1-A line 44 (Form 1040 line 13a): 6,000.00**
- **Line 15 taxable income: 97,925.00**

### Tax (line 16)
  - tax on 97,925.00: 2026 Tax Table row 97,900–97,950, single column = 16,256
- **Line 16: 16,256.00**

### Form 6251 (AMT)
- line 1b = taxable income 97,925.00 = 97,925.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 114,025.00
- line 5 exemption: 90,100.00
- line 6: 23,925.00
- line 7: 26% → 6,220.50
- line 9 TMT 6,220.50; line 10 regular tax 16,256.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 16,256.00 + 0.00 − 0.00 + 0.00 = 16,256.00
- ouch `federal_total_tax` (line 24 less refundable credits): **16,256.00**
- Payments (withholding): 17,000.00 → balance -744.00

### Colorado (DR 0104, 2026 rules)
- Federal taxable income 97,925.00
- Addition: overtime deduction addback: 6,000.00
- Colorado taxable income 103,925.00 × 4.4% = **4,572.70**
- **Total tax, all jurisdictions: 20,828.70**; balance 3,828.70
