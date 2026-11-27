# California: exemption credit phase-out

**Covers:** CA exemption credit AGI limitation ($6 per $2,500 over $252,203)

## Derivation basis

Worked line by line through the 2026 forms with figures from Rev. Proc.
2025-32 §4 and the 2026 IRS forms and draft instructions cited in
`tests/golden_derive/derive.py`, which does not import ouch. Tax on
taxable income below $100,000 is read from the 2026 Tax Table and the
earned income credit from the 2026 EIC Table (draft 2026 Instructions
for Form 1040), not computed by formula; the harness compares money
fields to the dollar (spec §19). **Not** produced by running `ouch`
(spec §16.2).

State figures: FTB 2026 Form 540-ES Instructions and FTB 2025 Booklet (line 32 AGI Limitation Worksheet). ouch's 2026 CA file carries these figures; the derivation types them from the source, not the file.

## Computation

### Income (Form 1040 lines 1–11)
- Line 1a wages: 300,000.00
- **Line 9 total income: 300,000.00**
- **Line 11 AGI: 300,000.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- **Line 15 taxable income: 283,900.00**

### Tax (line 16)
  - tax on 283,900.00 (Tax Computation Worksheet, single) = 68,134.25
- **Line 16: 68,134.25**

### Form 6251 (AMT)
- line 1b = taxable income 283,900.00 = 283,900.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 300,000.00
- line 5 exemption: 90,100.00
- line 6: 209,900.00
- line 7: 26% → 54,574.00
- line 9 TMT 54,574.00; line 10 regular tax 68,134.25
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (300,000.00 − 200,000.00) = 900.00 → **900.00**

### Totals
- Line 24 total tax = 68,134.25 + 0.00 − 0.00 + 900.00 = 69,034.25
- ouch `federal_total_tax` (line 24 less refundable credits): **69,034.25**
- Payments (withholding): 70,000.00 → balance -965.75

### California (Form 540)
- Line 17 California AGI = federal AGI 300,000.00; line 18 standard deduction 5,706.00; line 19 taxable 294,294.00
- Line 31 tax (Schedule X): 23,807.98
- AGI Limitation Worksheet: 47,797.00 over 252,203 → 20 steps × $6 = 120.00 per credit
- Line 32 exemption credits: 1 × 153 + 0 × 475 after the limitation = 33.00
- **Line 33 / 48 California tax: 23,774.98**
- **Total tax, all jurisdictions: 92,809.23**; balance 22,809.23
