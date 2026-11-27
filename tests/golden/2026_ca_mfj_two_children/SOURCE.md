# California: joint return, two children

**Covers:** CA progressive brackets (Schedule Y), standard deduction, personal and dependent exemption credits

## Derivation basis

Worked line by line through the 2026 forms with figures from Rev. Proc.
2025-32 §4 and the 2026 IRS forms and draft instructions cited in
`tests/golden_derive/derive.py`, which does not import ouch. Tax on
taxable income below $100,000 is read from the 2026 Tax Table and the
earned income credit from the 2026 EIC Table (draft 2026 Instructions
for Form 1040), not computed by formula; the harness compares money
fields to the dollar (spec §19). **Not** produced by running `ouch`
(spec §16.2).

State figures: FTB 2026 Form 540-ES Instructions (2026 estimated tax worksheet, which uses the 2025 tax table and exemption credits) and the FTB 2025 Personal Income Tax Booklet. ouch's 2026 CA file carries these figures; the derivation types them from the source, not the file.

## Computation

### Income (Form 1040 lines 1–11)
- Line 1a wages: 250,000.00 (taxpayer 150,000.00, spouse 100,000.00)
- **Line 9 total income: 250,000.00**
- **Line 11 AGI: 250,000.00**

### Deductions (lines 12–14)
- Standard deduction: 32,200
- **Line 12e: 32,200.00 (standard)**
- **Line 15 taxable income: 217,800.00**

### Tax (line 16)
  - tax on 217,800.00 (Tax Computation Worksheet, married_filing_jointly) = 37,468.00
- **Line 16: 37,468.00**

### Form 6251 (AMT)
- line 1b = taxable income 217,800.00 = 217,800.00
- line 2a (line 12e standard deduction): 32,200.00
- line 4 AMTI: 250,000.00
- line 5 exemption: 140,200.00
- line 6: 109,800.00
- line 7: 26% → 28,548.00
- line 9 TMT 28,548.00; line 10 regular tax 37,468.00
- **line 11 AMT: 0.00**

### Credits
- Schedule 8812: line 8 = 2 × 2,200 = 4,400.00; line 11 = 0.00; line 12 = 4,400.00; line 13 (Credit Limit Worksheet A) = 37,468.00; **line 14 = 4,400.00**

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 37,468.00 + 0.00 − 4,400.00 + 0.00 = 33,068.00
- ouch `federal_total_tax` (line 24 less refundable credits): **33,068.00**
- Payments (withholding): 40,000.00 → balance -6,932.00

### California (Form 540)
- Line 17 California AGI = federal AGI 250,000.00; line 18 standard deduction 11,412.00; line 19 taxable 238,588.00
- Line 31 tax (Schedule Y): 15,065.96
- Line 32 exemption credits: 2 × 153 + 2 × 475 after the limitation = 1,256.00
- **Line 33 / 48 California tax: 13,809.96**
- **Total tax, all jurisdictions: 46,877.96**; balance 6,877.96
